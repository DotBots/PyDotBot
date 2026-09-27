# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Planar kinematics of a DotBot v3 on the floor.

The frame is the firmware's: x right, y down, mm, headings in degrees with 0
facing +y and positive clockwise, so body-forward is (-sin, +cos). Every
function takes floats or numpy arrays.
"""

import numpy as np

# The effective track and lever arm of DotBot-libs drv/geometry.h (v3), what
# the robot's odometry and estimator use; dotbot/tests/test_sim_geometry.py
# pins them to it.
TRACK_EFFECTIVE_MM = 81.0
TRACK_EFFECTIVE_ARC_MM = 85.0
TRACK_EFFECTIVE_ARC_RATIO = 2.35
LEVER_ARM_EFFECTIVE_MM = 51.5


def track_effective_mm(left, right):
    """The track a pair of wheel travels turns the body with, as
    db_track_effective_mm(): the arc track on wide arcs, blending down to the
    spin track as the turn tightens."""
    diff = np.abs(right - left)
    total = np.abs(right + left)
    limit = TRACK_EFFECTIVE_ARC_RATIO * diff
    blend = TRACK_EFFECTIVE_MM + (
        TRACK_EFFECTIVE_ARC_MM - TRACK_EFFECTIVE_MM
    ) * total / np.maximum(limit, 1e-9)
    return np.where(total >= limit, TRACK_EFFECTIVE_ARC_MM, blend)


def forward(heading_deg):
    """Body-forward unit vector for a heading."""
    rad = np.radians(heading_deg)
    return -np.sin(rad), np.cos(rad)


def wrap180(deg):
    """An angle in [-180, 180)."""
    return (deg + 180.0) % 360.0 - 180.0


def move(x, y, heading_deg, left_mm, right_mm):
    """The pose after each wheel travels the given distance, along the arc's
    mid-heading."""
    distance = (left_mm + right_mm) / 2.0
    turn = np.degrees((left_mm - right_mm) / track_effective_mm(left_mm, right_mm))
    fx, fy = forward(heading_deg + turn / 2.0)
    return x + distance * fx, y + distance * fy, wrap180(heading_deg + turn)
