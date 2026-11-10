# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A station's pose, decomposed from a homography built from a known pinhole."""

import numpy as np
import pytest

from dotbot.calibration.station_geometry import station_pose


def _rotation(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return rx @ rz


@pytest.mark.parametrize(
    "centre", [(-540.0, 1270.0, -2420.0), (1390.0, -245.0, -1600.0), (500, 500, -900)]
)
def test_a_pinhole_station_is_found_where_it_stands(centre):
    rotation = _rotation(0.4, 2.7)
    t = -rotation @ np.array(centre)
    floor_to_image = np.c_[rotation[:, 0], rotation[:, 1], t] * 3.7
    pose = station_pose(0, np.linalg.inv(floor_to_image))
    assert pose.x_mm == pytest.approx(centre[0], abs=1e-6)
    assert pose.y_mm == pytest.approx(centre[1], abs=1e-6)
    assert pose.height_mm == pytest.approx(abs(centre[2]), abs=1e-6)
    assert pose.off_square_deg == pytest.approx(0.0, abs=1e-9)


def test_a_singular_matrix_has_no_pose():
    assert station_pose(0, np.zeros((3, 3))) is None
