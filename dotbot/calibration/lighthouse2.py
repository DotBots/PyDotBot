# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing the API to convert LH2 raw data to relative positions."""

# pylint: disable=invalid-name,unspecified-encoding,no-member

import dataclasses
import datetime
import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

# cv2 is imported lazily inside `compute_homography_matrix` (the only
# function that uses it). This keeps `dotbot calibrate export` usable
# without opencv-python installed — the exporter only reads / writes
# bytes and does no homography math itself.

CALIBRATION_DIR = Path.home() / ".dotbot"
CALIBRATION_DISTANCE_DEFAULT = 500  # in millimeters
CALIBRATION_SCHEMA_VERSION = 1
# Legacy binary file. Kept as a back-compat byproduct of save_calibration()
# so external consumers (swarmit OTA `calibrate-lh2 <path>`,
# dotbot-provision `flash --calibration <path>`) keep working until they
# learn to read the new TOML format. Once they do, drop the .out write.
CALIBRATION_LEGACY_OUT = "calibration.out"
CALIBRATION_TOML_GLOB = "calibration-*.toml"
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
        cam_y = -math.sin(a2 / 2 - a1 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)
    else:
        cam_y = -math.sin(a1 / 2 - a2 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)

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
    import cv2  # lazy: opencv-python is only required for the capture path

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
        ground_plane_coordinates = np.vstack((ground_plane_coordinates, projected[:2]))

    return ground_plane_coordinates


def homography_as_bytes(matrix: np.ndarray) -> bytes:
    """Convert homography matrix to bytes."""
    matrix_bytes = bytearray()
    try:
        for bytes_block in [
            int(n * 1e3).to_bytes(4, "little", signed=True) for n in matrix.ravel()
        ]:
            matrix_bytes += bytes_block
    except Exception:  # noqa: BLE001 - defensive fallback for overflow
        matrix_bytes = bytearray(36)
    return matrix_bytes


def _build_calibration_payload(
    homographies: list[LH2Homography], extra_lh_num: int
) -> bytes:
    """Pack homographies as 1-byte count + N × 36-byte matrices.

    Same wire shape the legacy `calibration.out` carried; the TOML
    payload also stores this byte-for-byte (hex-encoded) so external
    consumers can decode it without ambiguity.
    """
    payload = bytearray()
    payload.append(1 + extra_lh_num)
    for homography in homographies:
        payload += homography_as_bytes(homography.matrix)
    return bytes(payload)


def _parse_calibration_payload(payload: bytes) -> list[bytes]:
    """Inverse of `_build_calibration_payload`: yields the per-LH 36-byte
    matrix chunks. Used when loading from either TOML or legacy .out."""
    if not payload:
        return []
    count = payload[0]
    matrices = []
    for i in range(count):
        start = 1 + i * 36
        matrices.append(payload[start : start + 36])
    return matrices


def _read_toml_payload(path: Path) -> bytes:
    """Read a calibration-*.toml file and return the raw byte payload.

    Validates `schema_version` so future writers can break compatibility
    explicitly instead of silently corrupting reads.
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)
    schema = data.get("schema_version", 0)
    if schema != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported calibration schema_version {schema} "
            f"(this build supports {CALIBRATION_SCHEMA_VERSION})"
        )
    hex_data = data["calibration"]["data_hex"]
    return bytes.fromhex(hex_data)


class LighthouseManager:
    """Class to manage the LightHouse positionning state and workflow."""

    def __init__(
        self,
        calibration_distance: float = CALIBRATION_DISTANCE_DEFAULT,
        extra_lh_num: int = 0,
    ):
        Path.mkdir(CALIBRATION_DIR, exist_ok=True)
        # Legacy path, kept for back-compat with external consumers.
        # The primary record is now timestamped TOML files in CALIBRATION_DIR.
        self.calibration_output_path = CALIBRATION_DIR / CALIBRATION_LEGACY_OUT
        self.calibration_distance = calibration_distance
        self.extra_lh_num = extra_lh_num
        self.homographies: list[LH2Homography] = [LH2Homography()] * (
            1 + self.extra_lh_num
        )
        self.last_saved_toml_path: Optional[Path] = None

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

        print(f"ref: {samples[0].ref_lh_index}, homographies: {self.homographies}")

        # Convert reference counts to camera points
        ref_camera_points = camera_points_from_counts(
            [LH2Counts(s.ref_lh_index, s.ref_count1, s.ref_count2) for s in samples]
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
        self.homographies[0] = self._compute_reference_homography(reference_counts)

        print(f"Computing {self.extra_lh_num} extra lighthouse calibrations...")
        if self.extra_lh_num > 0:
            for lh_index in range(self.extra_lh_num):
                print(f"Computing calibration for LH{lh_index + 1}")
                samples = [s for s in calibration_samples if s.lh_index == lh_index + 1]
                self.homographies[lh_index + 1] = self._compute_extra_calibration(
                    samples
                )

    def has_calibration(self, lh_index) -> bool:
        """Check if calibration is available for a given lighthouse index."""
        return len(self.homographies) > lh_index and not np.all(
            self.homographies[lh_index].matrix == 0
        )

    def load_calibration(self) -> list[bytes]:
        """Load the most recent calibration as a flat list of matrix bytes.

        Prefers the newest timestamped `calibration-*.toml`; falls back
        to the legacy binary `calibration.out` if no TOML files exist
        (so setups predating the format change keep working).
        """
        toml_files = sorted(
            CALIBRATION_DIR.glob(CALIBRATION_TOML_GLOB),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if toml_files:
            return _parse_calibration_payload(_read_toml_payload(toml_files[0]))
        if os.path.exists(self.calibration_output_path):
            return _parse_calibration_payload(self.calibration_output_path.read_bytes())
        return []

    def save_calibration(self) -> Path:
        """Save the calibration as a timestamped TOML file (+ legacy .out).

        The TOML file is the new primary record: versioned, metadata-
        bearing, human-inspectable. The legacy `.out` file is also
        written so external consumers (swarmit OTA, dotbot-provision)
        keep working until they learn to read TOML.

        Returns the path of the TOML file just written, and also stores
        it on `self.last_saved_toml_path` so a caller that lost the
        return value (e.g. the TUI handler) can still surface it after
        the fact.
        """
        payload = _build_calibration_payload(self.homographies, self.extra_lh_num)

        now = datetime.datetime.now(datetime.timezone.utc)
        # Filename-safe variant of ISO 8601: `:` is rejected on Windows
        # and a footgun on some Unix tools.
        ts_for_filename = now.strftime("%Y-%m-%dT%H-%M-%SZ")
        toml_path = CALIBRATION_DIR / f"calibration-{ts_for_filename}.toml"
        toml_path.write_text(
            f"schema_version = {CALIBRATION_SCHEMA_VERSION}\n"
            "\n"
            "[metadata]\n"
            f'created_at = "{now.strftime("%Y-%m-%dT%H:%M:%SZ")}"\n'
            f"calibration_distance_mm = {int(self.calibration_distance)}\n"
            f"num_lh_stations = {1 + self.extra_lh_num}\n"
            "\n"
            "[calibration]\n"
            "# 1-byte homography count + N × 36-byte int32 LE matrices,\n"
            "# hex-encoded. Same bytes as the legacy calibration.out.\n"
            f'data_hex = "{payload.hex()}"\n'
        )

        # Legacy back-compat write — drop once swarmit OTA + provision
        # read TOML.
        self.calibration_output_path.write_bytes(payload)
        self.last_saved_toml_path = toml_path
        return toml_path

    def ground_coordinate_from_counts(self, counts: LH2Counts) -> np.ndarray:
        """Convert counts to ground plane coordinates using homography."""
        # Convert counts to camera points
        camera_points = np.zeros((1, 2), dtype=np.float64)
        camera_points[0] = calculate_camera_point(counts)

        # Apply homography to get ground plane coordinates
        return apply_homography(
            self.homographies[counts.lh_index].matrix, camera_points
        )[0]
