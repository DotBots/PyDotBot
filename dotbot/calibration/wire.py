# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Pack a solved calibration into the bytes a bot receives.

The wire format is built at send time from `[[station]].homography`, never
stored: a packed blob in the file would be undiffable and would freeze the
encoding into storage. swarmit carries the mirror of this packer, and a
fixture test in each repo pins the same bytes for the same file.
"""

from __future__ import annotations

import struct
from typing import Sequence

from dotbot.calibration.lighthouse2 import LH2_BASESTATION_COUNT_MAX, StationSolution

# 1-byte station count, then one 36-byte record per station: nine IEEE 754
# float32, little-endian, row-major.
MATRIX_BYTES = 9 * 4
_MATRIX = struct.Struct("<9f")


def homography_as_float32(matrix: Sequence[Sequence[float]]) -> bytes:
    """One 3x3 matrix as nine little-endian float32."""
    flat = [float(v) for row in matrix for v in row]
    if len(flat) != 9:
        raise ValueError(f"a homography is 3x3, got {len(flat)} elements")
    return _MATRIX.pack(*flat)


def calibration_payload(stations: Sequence[StationSolution]) -> bytes:
    """The push payload for a whole calibration, stations in index order."""
    ordered = sorted(stations, key=lambda s: s.index)
    if not ordered:
        raise ValueError("calibration carries no solved station")
    if len(ordered) > LH2_BASESTATION_COUNT_MAX:
        raise ValueError(
            f"{len(ordered)} stations exceeds the LH2 limit "
            f"({LH2_BASESTATION_COUNT_MAX})"
        )
    payload = bytearray([len(ordered)])
    for station in ordered:
        payload += homography_as_float32(station.homography)
    return bytes(payload)


def unpack_payload(payload: bytes) -> list[list[list[float]]]:
    """Inverse of `calibration_payload`, for tests and diagnostics."""
    if not payload:
        return []
    count = payload[0]
    matrices = []
    for i in range(count):
        start = 1 + i * MATRIX_BYTES
        flat = _MATRIX.unpack(payload[start : start + MATRIX_BYTES])
        matrices.append([list(flat[0:3]), list(flat[3:6]), list(flat[6:9])])
    return matrices
