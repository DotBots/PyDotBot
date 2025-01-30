# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing the API to convert LH2 raw data to relative positions."""

# pylint: disable=invalid-name,unspecified-encoding,no-member

import math
import os
import pickle
import sys
from ctypes import CDLL
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from dotbot.logger import LOGGER
from dotbot.models import DotBotCalibrationStateModel, DotBotLH2Position
from dotbot.protocol import PayloadLh2RawData

if sys.platform == "win32":
    LIB_EXT = "dll"
elif sys.platform == "darwin":
    LIB_EXT = "dylib"
else:
    LIB_EXT = "so"

LH2_LIB_PATH = os.path.join(os.path.dirname(__file__), "lib", f"lh2.{LIB_EXT}")
LH2_LIB = CDLL(LH2_LIB_PATH)
REFERENCE_POINTS_DEFAULT = [
    [-0.1, 0.1],
    [0.1, 0.1],
    [-0.1, -0.1],
    [0.1, -0.1],
]
CALIBRATION_DIR = Path.home() / ".pydotbot"


def _lh2_raw_data_to_counts(raw_data: PayloadLh2RawData, func: callable) -> List[int]:
    counts = [0] * 2
    pos_A = 0
    pos_B = 0
    for i in range(2):
        index = 0
        if raw_data.locations[i].polynomial_index in [0, 1]:
            index = pos_A
            pos_A += 1
        elif raw_data.locations[i].polynomial_index in [0, 1]:
            index = 2 + pos_B
            pos_B += 1
        if index > 1:
            continue
        counts[index] = func(
            raw_data.locations[i].polynomial_index,
            raw_data.locations[i].bits >> (47 - raw_data.locations[i].offset),
        )
    return counts


def lh2_raw_data_to_counts(raw_data: PayloadLh2RawData) -> List[int]:
    """Convert bits sequence to an array of counts."""
    return _lh2_raw_data_to_counts(raw_data, LH2_LIB.reverse_count_p)


def calculate_camera_point(count1, count2, poly_in):
    """Calculate camera points from counts."""
    if poly_in < 2:
        period = 959000
    if poly_in > 1:
        period = 957000

    a1 = (count1 * 8 / period) * 2 * math.pi
    a2 = (count2 * 8 / period) * 2 * math.pi

    cam_x = -math.tan(0.5 * (a1 + a2))
    if count1 < count2:
        cam_y = -math.sin(a2 / 2 - a1 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)
    else:
        cam_y = -math.sin(a1 / 2 - a2 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)

    return cam_x, cam_y


def _unitize(x_in, y_in):
    magnitude = np.sqrt(x_in**2 + y_in**2)
    return x_in / magnitude, y_in / magnitude


@dataclass
class CalibrationData:
    """Class that stores calibration data."""

    zeta: float
    random_rodriguez: np.array
    normal: np.array
    m: np.array


class LighthouseManagerState(Enum):
    """Enum for lighthouse manager internal state."""

    NotCalibrated = 0
    CalibrationInProgress = 1
    Ready = 2
    Calibrated = 3


class LighthouseManager:
    """Class to manage the LightHouse positionning state and workflow."""

    def __init__(self):
        self.state = LighthouseManagerState.NotCalibrated
        self.reference_points = REFERENCE_POINTS_DEFAULT
        Path.mkdir(CALIBRATION_DIR, exist_ok=True)
        self.calibration_output_path = CALIBRATION_DIR / "calibration.out"
        self.calibration_data = self._load_calibration()
        self.calibration_points = np.zeros(
            (2, len(self.reference_points), 2), dtype=np.float64
        )
        self.calibration_points_available = [False] * len(self.reference_points)
        self.last_raw_data = None
        self.logger = LOGGER.bind(context=__name__)
        self.logger.info("Lighthouse initialized")

    @property
    def state_model(self) -> DotBotCalibrationStateModel:
        """Return the state as pydantic model."""
        if self.state == LighthouseManagerState.CalibrationInProgress:
            return DotBotCalibrationStateModel(state="running")
        if self.state == LighthouseManagerState.Ready:
            return DotBotCalibrationStateModel(state="ready")
        if self.state == LighthouseManagerState.Calibrated:
            return DotBotCalibrationStateModel(state="done")
        return DotBotCalibrationStateModel(state="unknown")

    def _load_calibration(self) -> Optional[CalibrationData]:
        if not os.path.exists(self.calibration_output_path):
            return None
        with open(self.calibration_output_path, "rb") as calibration_file:
            calibration = pickle.load(calibration_file)
        self.state = LighthouseManagerState.Calibrated
        return calibration

    def add_calibration_point(self, index):
        """Register a new camera points for calibration."""
        if self.last_raw_data is None:
            self.logger.warning("Missing raw data", index=index)
            return

        self.calibration_points_available[index] = True

        counts = lh2_raw_data_to_counts(self.last_raw_data)
        self.calibration_points[0][index] = np.asarray(
            calculate_camera_point(
                counts[0],
                counts[1],
                self.last_raw_data.locations[0].polynomial_index,
            ),
            dtype=np.float64,
        )
        self.calibration_points[1][index] = np.asarray(
            calculate_camera_point(
                counts[0],
                counts[1],
                self.last_raw_data.locations[1].polynomial_index,
            ),
            dtype=np.float64,
        )

        if all(self.calibration_points_available) is False:
            self.state = LighthouseManagerState.CalibrationInProgress
        if all(self.calibration_points_available) is True:
            self.state = LighthouseManagerState.Ready
        self.logger.info("Calibration point added", index=index, state=self.state)

    def compute_calibration(self):  # pylint: disable=too-many-locals
        """Compute the calibration values and matrices."""
        if self.state != LighthouseManagerState.Ready:
            self.logger.warning("Not ready, skipping calibration")
            return

        self.logger.info("Calibrating", points=self.calibration_points)

        camera_points = [[], []]
        for data in self.calibration_points[0]:
            camera_points[0].append(data)
        for data in self.calibration_points[1]:
            camera_points[1].append(data)
        camera_points_arr = np.asarray(camera_points, dtype=np.float64)
        homography_mat = cv2.findHomography(
            camera_points_arr[0][0 : len(camera_points[0])][:],
            camera_points_arr[1][0 : len(camera_points[1])][:],
            method=cv2.RANSAC,
            ransacReprojThreshold=0.001,
        )[0]

        _, S, V = np.linalg.svd(homography_mat)
        V = V.T

        s1 = S[0] / S[1]
        s3 = S[2] / S[1]
        zeta = s1 - s3
        a1 = np.sqrt(1 - s3**2)
        b1 = np.sqrt(s1**2 - 1)
        a, b = _unitize(a1, b1)
        v1 = np.array(V[:, 0])
        v3 = np.array(V[:, 2])
        n = b * v1 + a * v3

        if n[2] < 0:
            n = -n

        random_rodriguez = np.array(
            [
                [
                    -n[1] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                    n[0] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                    0,
                ],
                [
                    n[0] * n[2] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                    n[1] * n[2] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                    -np.sqrt(n[0] * n[0] + n[1] * n[1]),
                ],
                [-n[0], -n[1], -n[2]],
            ]
        )

        pts_cam_new = np.hstack(
            (camera_points_arr[1], np.ones((len(camera_points_arr[1]), 1)))
        )
        scales = (1 / zeta) / np.matmul(n, pts_cam_new.T)
        scales_matrix = np.vstack((scales, scales, scales))
        final_points = scales_matrix * pts_cam_new.T
        final_points = final_points.T

        M, _ = cv2.findHomography(
            final_points.dot(random_rodriguez.T)[:, 0:2],
            np.array([self.reference_points], dtype=np.float64) + 0.5,
            cv2.RANSAC,
            5.0,
        )

        self.calibration_data = CalibrationData(zeta, random_rodriguez, n, M)

        with open(self.calibration_output_path, "wb") as output_file:
            pickle.dump(self.calibration_data, output_file)

        self.state = LighthouseManagerState.Calibrated
        self.logger.info("Calibration done", data=self.calibration_data)

    def compute_position(
        self, raw_data: PayloadLh2RawData
    ) -> Optional[DotBotLH2Position]:
        """Compute the position coordinates from LH2 raw data and available calibration."""
        if self.state != LighthouseManagerState.Calibrated:
            return None

        if any(raw_data.locations[index].bits == 0 for index in range(2)):
            return None

        counts = lh2_raw_data_to_counts(raw_data)
        camera_points = np.asarray(
            [
                calculate_camera_point(
                    counts[0], counts[1], raw_data.locations[0].polynomial_index
                ),
                calculate_camera_point(
                    counts[0], counts[1], raw_data.locations[1].polynomial_index
                ),
            ],
            dtype=np.float64,
        )

        pts_cam_new = np.hstack((camera_points, np.ones((len(camera_points), 1))))
        scales = (1 / self.calibration_data.zeta) / np.matmul(
            self.calibration_data.normal, pts_cam_new.T
        )
        scales_matrix = np.vstack((scales, scales, scales))
        final_points = scales_matrix * pts_cam_new.T
        final_points = final_points.T
        corners_planar = final_points.dot(self.calibration_data.random_rodriguez.T)[
            :, 0:2
        ][1].reshape(1, 1, 2)
        pts_meter_corners = cv2.perspectiveTransform(
            corners_planar, self.calibration_data.m
        ).reshape(-1, 2)
        return DotBotLH2Position(
            x=pts_meter_corners[0][0], y=1 - pts_meter_corners[0][1], z=0.0
        )
