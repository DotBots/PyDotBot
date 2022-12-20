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

from dotbot.models import DotBotLH2Position, DotBotCalibrationStateModel
from dotbot.protocol import Lh2RawData


if sys.platform == "win32":
    LIB_EXT = "dll"
elif sys.platform == "darwin":
    LIB_EXT = "dylib"
else:
    LIB_EXT = "so"

LH2_LIB_PATH = os.path.join(os.path.dirname(__file__), "lib", f"lh2.{LIB_EXT}")
POLYNOMIALS = [
    0x0001D258,
    0x00017E04,
    0x0001FF6B,
    0x00013F67,
]
END_BUFFERS = [
    [
        0x00000000000000001,
        0b10101010110011101,
        0b10001010101011010,
        0b11001100100000010,
        0b01100101100011111,
        0b10010001101011110,
        0b10100011001011111,
        0b11110001010110001,
        0b10111000110011011,
        0b10100110100011110,
        0b11001101100010000,
        0b01000101110011111,
        0b11100101011110101,
        0b01001001110110111,
        0b11011100110011101,
        0b10000110101101011,
    ],
    [
        0x00000000000000001,
        0b11010000110111110,
        0b10110111100111100,
        0b11000010101101111,
        0b00101110001101110,
        0b01000011000110100,
        0b00010001010011110,
        0b10100101111010001,
        0b10011000000100001,
        0b01110011011010110,
        0b00100011101000011,
        0b10111011010000101,
        0b00110010100110110,
        0b01000111111100110,
        0b10001101000111011,
        0b00111100110011100,
    ],
    [
        0x00000000000000001,
        0b00011011011000100,
        0b01011101010010110,
        0b11001011001101010,
        0b01110001111011010,
        0b10110110011111010,
        0b10110001110000001,
        0b10001001011101001,
        0b00000010011101011,
        0b01100010101111011,
        0b00111000001101111,
        0b10101011100111000,
        0b01111110101111111,
        0b01000011110101010,
        0b01001011100000011,
        0b00010110111101110,
    ],
    [
        0x00000000000000001,
        0b11011011110010110,
        0b11000100000001101,
        0b11100011000010110,
        0b00011111010001100,
        0b11000001011110011,
        0b10011101110001010,
        0b00001011001111000,
        0b00111100010000101,
        0b01001111001010100,
        0b01011010010110011,
        0b11111101010001100,
        0b00110101011011111,
        0b01110110010101011,
        0b00010000110100010,
        0b00010111110101110,
    ],
]
REFERENCE_POINTS_DEFAULT = [
    [-0.1, 0.1],
    [0.1, 0.1],
    [-0.1, -0.1],
    [0.1, -0.1],
]
CALIBRATION_DIR = Path.home() / ".pydotbot"


def _lh2_raw_data_to_counts(raw_data: Lh2RawData, func: callable) -> List[int]:
    counts = [0] * 4
    pos_A = 0
    pos_B = 0
    for i in range(4):
        index = 0
        if raw_data.locations[i].polynomial_index in [0, 1]:
            index = pos_A
            pos_A += 1
        elif raw_data.locations[i].polynomial_index in [2, 3]:
            index = 2 + pos_B
            pos_B += 1
        if index > 3:
            continue
        counts[index] = func(
            raw_data.locations[i].polynomial_index,
            raw_data.locations[i].bits >> (47 - raw_data.locations[i].offset),
        )
    return counts


def _lh2_raw_data_to_counts_lib(raw_data: Lh2RawData) -> List[int]:
    lh2_lib = CDLL(LH2_LIB_PATH)
    return _lh2_raw_data_to_counts(raw_data, lh2_lib.reverse_count_p)


def _reverse_count_py(index, bit_seq):
    poly = POLYNOMIALS[index]

    count = 0
    match = False
    buffer = bit_seq

    while match is False:
        for idx in range(16):
            if buffer == END_BUFFERS[index][idx]:
                count = count + 8192 * idx - 1
                match = True
                return count

        b17 = buffer & 0b1
        buffer = buffer & 0x1FFFE
        buffer = buffer >> 1
        masked_buffer = buffer & poly
        result = bin(masked_buffer).count("1") % 2
        result = result ^ b17
        result = result << 16
        buffer = buffer | result
        result = 0
        count = count + 1


def _lh2_raw_data_to_counts_py(raw_data: Lh2RawData) -> List[int]:
    return _lh2_raw_data_to_counts(raw_data, _reverse_count_py)


def lh2_raw_data_to_counts(raw_data: Lh2RawData) -> List[int]:
    """Convert bits sequence to an array of counts."""
    if os.path.exists(LH2_LIB_PATH):
        return _lh2_raw_data_to_counts_lib(raw_data)
    return _lh2_raw_data_to_counts_py(raw_data)


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


class LighthouseManager:  # pylint: disable=too-many-instance-attributes
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
                counts[2],
                counts[3],
                self.last_raw_data.locations[2].polynomial_index,
            ),
            dtype=np.float64,
        )

        if all(self.calibration_points_available) is False:
            self.state = LighthouseManagerState.CalibrationInProgress
        if all(self.calibration_points_available):
            self.state = LighthouseManagerState.Ready

    def compute_calibration(self):  # pylint: disable=too-many-locals
        """Compute the calibration values and matrices."""
        if self.state != LighthouseManagerState.Ready:
            print("Calibration points are not ready, cannot compute calibration")
            return

        print("Calibration points:", self.calibration_points)

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

        print("Calibration data:", self.calibration_data)

        with open(self.calibration_output_path, "wb") as output_file:
            pickle.dump(self.calibration_data, output_file)

        self.state = LighthouseManagerState.Calibrated

    def compute_position(self, raw_data: Lh2RawData) -> Optional[DotBotLH2Position]:
        """Compute the position coordinates from LH2 raw data and available calibration."""
        if self.state != LighthouseManagerState.Calibrated:
            return None

        if any(raw_data.locations[index].bits == 0 for index in range(4)):
            return None

        counts = lh2_raw_data_to_counts(raw_data)
        camera_points = np.asarray(
            [
                calculate_camera_point(
                    counts[0], counts[1], raw_data.locations[0].polynomial_index
                ),
                calculate_camera_point(
                    counts[2], counts[3], raw_data.locations[2].polynomial_index
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
