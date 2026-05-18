# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing the API to convert LH2 raw data to relative positions."""

# pylint: disable=invalid-name,unspecified-encoding,no-member

import dataclasses
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

CALIBRATION_DIR = Path.home() / ".dotbot"
CALIBRATION_DISTANCE_DEFAULT = 500  # in millimeters
REFERENCE_POINTS_DEFAULT = [
    [0.4, 0.4],  # Top-left
    [0.6, 0.4],  # Top-right
    [0.4, 0.6],  # Bottom-left
    [0.6, 0.6],  # Bottom-right
]
LH_PERIODS = [
    959000,  # mode 1
    957000,  # mode 2
    953000,  # mode 3
    949000,  # mode 4
    947000,  # mode 5
    943000,  # mode 6
    941000,  # mode 7
    939000,  # mode 8
    937000,  # mode 9
    929000,  # mode 10
    919000,  # mode 11
    911000,  # mode 12
    907000,  # mode 13
    901900,  # mode 14
    893000,  # mode 15
    887000,  # mode 16
]


@dataclass
class LH2Homography:
    """Dataclass that holds computed LH2 homography for a basestation indicated by index."""

    matrix: np.ndarray = dataclasses.field(
        default_factory=lambda: np.zeros((3, 3), dtype=np.float64)
    )


@dataclass
class LH2Counts:
    """Class that stores LH2 counts."""

    lh_index: int
    count1: int
    count2: int

    def __repr__(self):
        return f"{dataclasses.asdict(self)}"


@dataclass
class LH2CalibrationSample:
    """Class that stores LH2 calibration data."""

    lh_index: int
    count1: int
    count2: int
    ref_lh_index: Optional[int] = None
    ref_count1: Optional[int] = None
    ref_count2: Optional[int] = None

    def __post_init__(self):
        self.lh_index = int(self.lh_index)
        self.count1 = int(self.count1)
        self.count2 = int(self.count2)
        if self.ref_lh_index is not None:
            self.ref_lh_index = int(self.ref_lh_index)
        if self.ref_count1 is not None:
            self.ref_count1 = int(self.ref_count1)
        if self.ref_count2 is not None:
            self.ref_count2 = int(self.ref_count2)


def calculate_camera_point(counts: LH2Counts) -> np.ndarray:
    """Calculate camera points from counts."""
    period = LH_PERIODS[counts.lh_index]

    a1 = (counts.count1 * 8 / period) * 2 * math.pi
    a2 = (counts.count2 * 8 / period) * 2 * math.pi

    cam_x = -math.tan(0.5 * (a1 + a2))
    if counts.count1 < counts.count2:
        cam_y = -math.sin(a2 / 2 - a1 / 2 - 60 * math.pi / 180) / math.tan(
            math.pi / 6
        )
    else:
        cam_y = -math.sin(a1 / 2 - a2 / 2 - 60 * math.pi / 180) / math.tan(
            math.pi / 6
        )

    return np.asarray([cam_x, cam_y], dtype=np.float64)


def camera_points_from_counts(counts: list[LH2Counts]) -> np.ndarray:
    """Convert counts to camera points."""
    camera_points = np.zeros((len(counts), 2), dtype=np.float64)
    for index, count in enumerate(counts):
        camera_points[index] = calculate_camera_point(count)
    return camera_points


def compute_homography_matrix(
    camera_points: np.ndarray,
    reference_points: np.ndarray,
) -> np.ndarray:
    """Compute homography matrix from camera points to reference points."""
    M, _ = cv2.findHomography(
        camera_points,
        reference_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=0.001,
    )

    if M is None:
        raise ValueError("Cannot find a valid homography matrix.")

    return M


def apply_homography(
    homography: np.ndarray, camera_view_points: np.ndarray
) -> np.ndarray:
    """Apply homography to camera points."""
    ground_plane_coordinates = np.zeros((0, 2), dtype=np.float64)
    for row in camera_view_points:
        projected = np.dot(homography, np.array([row[0], row[1], 1.0]))
        projected /= projected[2]
        ground_plane_coordinates = np.vstack(
            (ground_plane_coordinates, projected[:2])
        )

    return ground_plane_coordinates


def homography_as_bytes(matrix: np.ndarray) -> bytes:
    """Convert homography matrix to bytes."""
    matrix_bytes = bytearray()
    try:
        for bytes_block in [
            int(n * 1e3).to_bytes(4, "little", signed=True)
            for n in matrix.ravel()
        ]:
            matrix_bytes += bytes_block
    except:
        matrix_bytes = bytearray(36)
    return matrix_bytes


class LighthouseManager:
    """Class to manage the LightHouse positionning state and workflow."""

    def __init__(
        self,
        calibration_distance: float = CALIBRATION_DISTANCE_DEFAULT,
        extra_lh_num: int = 0,
    ):
        Path.mkdir(CALIBRATION_DIR, exist_ok=True)
        self.calibration_output_path = CALIBRATION_DIR / "calibration.out"
        self.calibration_distance = calibration_distance
        self.extra_lh_num = extra_lh_num
        self.homographies: list[LH2Homography] = [LH2Homography()] * (
            1 + self.extra_lh_num
        )

    def _compute_reference_homography(
        self, calibration_counts: list[LH2Counts]
    ) -> LH2Homography:
        """Compute the reference calibration values and matrices."""
        # Convert reference counts to camera view points
        camera_points = camera_points_from_counts(calibration_counts)

        reference_points = np.array(REFERENCE_POINTS_DEFAULT, dtype=np.float64)
        # Scale reference points according to calibration distance
        reference_points *= self.calibration_distance * 5

        # Compute homography from camera points to ground plane coordinates
        homography = compute_homography_matrix(
            camera_points,
            reference_points,
        )

        print(f"reference homography: {homography}")

        # Project camera points using computed homography for verification
        ref_coordinates = apply_homography(homography, camera_points)

        # compare with reference points
        for i, ref_point in enumerate(reference_points):
            if not np.allclose(ref_coordinates[i], ref_point, atol=1e-3):
                raise ValueError(
                    f"Projected point {ref_coordinates[i]} does not match reference point {ref_point}"
                )

        return LH2Homography(matrix=homography)

    def _compute_extra_calibration(
        self, samples: list[LH2CalibrationSample]
    ) -> LH2Homography:
        """Compute the extra lighthouse calibration values and matrices."""

        print(
            f"ref: {samples[0].ref_lh_index}, homographies: {self.homographies}"
        )

        # Convert reference counts to camera points
        ref_camera_points = camera_points_from_counts(
            [
                LH2Counts(s.ref_lh_index, s.ref_count1, s.ref_count2)
                for s in samples
            ]
        )

        print(f"ref_camera_points: {ref_camera_points}")

        # Convert reference camera points to ground plane coordinates using reference homography
        ref_coordinates = apply_homography(
            self.homographies[samples[0].ref_lh_index].matrix,
            ref_camera_points,
        )

        print(f"ref_coordinates: {ref_coordinates}")

        # Convert new LH counts to new camera points
        new_camera_points = camera_points_from_counts(
            [LH2Counts(s.lh_index, s.count1, s.count2) for s in samples]
        )

        print(f"new_camera_points: {new_camera_points}")

        # Compute homography from new camera points to ground plane coordinates
        homography = compute_homography_matrix(
            new_camera_points,
            ref_coordinates,
        )

        # Project camera points using computed homography for verification
        ref_coordinates = apply_homography(homography, new_camera_points)

        # compare with reference points
        for i, ref_point in enumerate(ref_coordinates):
            if not np.allclose(ref_coordinates[i], ref_point, atol=1e-3):
                raise ValueError(
                    f"Projected point {ref_coordinates[i]} does not match reference point {ref_point}"
                )

        print(f"Computed homography: {homography}")

        return LH2Homography(matrix=homography)

    def compute_calibration(
        self,
        calibration_samples: list[LH2CalibrationSample],
    ) -> list[LH2Homography]:
        """Compute the calibration values and matrices."""
        reference_counts = [
            LH2Counts(s.lh_index, s.count1, s.count2)
            for s in calibration_samples
            if s.lh_index == 0
        ]
        self.homographies[0] = self._compute_reference_homography(
            reference_counts
        )

        print(
            f"Computing {self.extra_lh_num} extra lighthouse calibrations..."
        )
        if self.extra_lh_num > 0:
            for lh_index in range(self.extra_lh_num):
                print(f"Computing calibration for LH{lh_index + 1}")
                samples = [
                    s
                    for s in calibration_samples
                    if s.lh_index == lh_index + 1
                ]
                self.homographies[lh_index + 1] = (
                    self._compute_extra_calibration(samples)
                )

    def has_calibration(self, lh_index) -> bool:
        """Check if calibration is available for a given lighthouse index."""
        return len(self.homographies) > lh_index and not np.all(
            self.homographies[lh_index].matrix == 0
        )

    def load_calibration(self) -> list[bytes]:
        if not os.path.exists(self.calibration_output_path):
            return []
        homographies_bytes = []
        with open(self.calibration_output_path, "rb") as calibration_file:
            homographies_num = int.from_bytes(
                calibration_file.read(1), "little", signed=False
            )
            for _ in range(homographies_num):
                homography_matrix = calibration_file.read(36)
                homographies_bytes.append(homography_matrix)
        return homographies_bytes

    def save_calibration(self) -> None:
        """Save the calibration to a file."""
        with open(self.calibration_output_path, "wb") as calibration_file:
            calibration_file.write(
                int(1 + self.extra_lh_num).to_bytes(1, "little", signed=False)
            )
            for homography in self.homographies:
                calibration_file.write(homography_as_bytes(homography.matrix))

    def ground_coordinate_from_counts(self, counts: LH2Counts) -> np.ndarray:
        """Convert counts to ground plane coordinates using homography."""
        # Convert counts to camera points
        camera_points = np.zeros((1, 2), dtype=np.float64)
        camera_points[0] = calculate_camera_point(counts)

        # Apply homography to get ground plane coordinates
        return apply_homography(
            self.homographies[counts.lh_index].matrix, camera_points
        )[0]
