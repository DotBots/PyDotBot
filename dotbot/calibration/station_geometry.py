# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Where each LH2 station stands, estimated from its homography alone.

Each station's homography is decomposed as a unit pinhole: the floor's two
axes and its origin, seen from the station, give its position above the
floor. The decomposed axes come out a few degrees off square, so the numbers
explain the room and never decide a position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from dotbot.calibration.lighthouse2 import Calibration


@dataclass(frozen=True)
class StationPose:
    index: int
    # On the floor below the station, frame mm (it may lie outside the floor)
    x_mm: float
    y_mm: float
    height_mm: float
    # How far the decomposed floor axes are from square, degrees
    off_square_deg: float


def station_pose(index: int, homography) -> StationPose | None:
    """The station's estimated pose; None when its homography does not
    decompose (a degenerate or non-perspective matrix)."""
    try:
        g = np.linalg.inv(np.asarray(homography, dtype=float))
    except np.linalg.LinAlgError:
        return None
    g1, g2, g3 = g[:, 0], g[:, 1], g[:, 2]
    norm = np.linalg.norm(g1) + np.linalg.norm(g2)
    if not np.isfinite(norm) or norm == 0:
        return None
    scale = 2.0 / norm
    r1, r2, t = scale * g1, scale * g2, scale * g3
    if t[2] < 0:
        r1, r2, t = -r1, -r2, -t
    r3 = np.cross(r1, r2)
    centre = -np.c_[r1, r2, r3].T @ t
    cos = float(r1 @ r2 / (np.linalg.norm(r1) * np.linalg.norm(r2)))
    off = math.degrees(math.acos(max(-1.0, min(1.0, cos)))) - 90.0
    if not np.all(np.isfinite(centre)):
        return None
    return StationPose(
        index=index,
        x_mm=float(centre[0]),
        y_mm=float(centre[1]),
        height_mm=float(abs(centre[2])),
        off_square_deg=float(off),
    )


def station_poses(calibration: Calibration) -> dict[int, StationPose]:
    poses = {}
    for st in calibration.stations:
        pose = station_pose(st.index, st.matrix)
        if pose is not None:
            poses[st.index] = pose
    return poses


def geometry(calibration: Calibration) -> dict:
    """The frame-invariant shape of the stations, for comparing two spins:
    each station's height and the distance between every pair, mm."""
    poses = station_poses(calibration)
    apart = {}
    for a, b in combinations(sorted(poses), 2):
        pa, pb = poses[a], poses[b]
        apart[f"{a}-{b}"] = round(
            math.dist(
                (pa.x_mm, pa.y_mm, pa.height_mm), (pb.x_mm, pb.y_mm, pb.height_mm)
            )
        )
    return {
        "stations": {
            str(i): {
                "x_mm": round(p.x_mm),
                "y_mm": round(p.y_mm),
                "height_mm": round(p.height_mm),
                "off_square_deg": round(p.off_square_deg, 1),
            }
            for i, p in poses.items()
        },
        "apart_mm": apart,
    }
