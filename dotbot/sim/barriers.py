# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A site's walls and obstacles, as the simulated bodies meet them.

A robot's body is taken as a disc round its outline's centre, which sits
ahead of the axle midpoint; a pose whose disc crosses a wall or an
obstacle's edge, or lies inside an obstacle, is blocked.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from dotbot.kinematics import forward
from dotbot.robots import RobotGeometry, robot_geometry


def _segments(polylines: Sequence[np.ndarray], closed: bool) -> np.ndarray:
    out = []
    for points in polylines:
        ends = np.roll(points, -1, axis=0) if closed else points[1:]
        starts = points if closed else points[:-1]
        out.append(np.hstack([starts, ends]))
    return np.vstack(out) if out else np.zeros((0, 4))


class Barriers:
    """Walls (polylines) and obstacles (polygons) in frame mm."""

    def __init__(
        self,
        walls: Sequence[Sequence[Sequence[float]]] = (),
        obstacles: Sequence[Sequence[Sequence[float]]] = (),
        geometry: RobotGeometry | None = None,
    ):
        geometry = geometry or robot_geometry()
        self.radius_mm = geometry.envelope_mm / 2
        # The outline's centre, ahead of the axle along the body (board frame
        # nose toward low y)
        self.centre_ahead_mm = geometry.axle_midpoint.y - geometry.outline_centre.y
        self.polygons = [np.asarray(o, dtype=float) for o in obstacles]
        self.segments = np.vstack(
            [
                _segments([np.asarray(w, dtype=float) for w in walls], closed=False),
                _segments(self.polygons, closed=True),
            ]
        )

    def __bool__(self) -> bool:
        return len(self.segments) > 0

    @classmethod
    def from_site(cls, site) -> Barriers | None:
        """The site's barriers, or None when it has none."""
        if site is None or not (site.walls or site.obstacles):
            return None
        return cls([w.points for w in site.walls], [o.points for o in site.obstacles])

    def blocked(self, x, y, heading_deg) -> np.ndarray:
        """Whether each pose (axle midpoint and heading) meets a barrier."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        y = np.atleast_1d(np.asarray(y, dtype=float))
        fx, fy = forward(np.atleast_1d(np.asarray(heading_deg, dtype=float)))
        cx = x + self.centre_ahead_mm * fx
        cy = y + self.centre_ahead_mm * fy
        hit = np.zeros(len(cx), dtype=bool)
        if len(self.segments):
            ax, ay, bx, by = (self.segments[:, i][None, :] for i in range(4))
            dx, dy = bx - ax, by - ay
            length2 = np.maximum(dx * dx + dy * dy, 1e-12)
            t = np.clip(
                ((cx[:, None] - ax) * dx + (cy[:, None] - ay) * dy) / length2, 0, 1
            )
            gap2 = (cx[:, None] - ax - t * dx) ** 2 + (cy[:, None] - ay - t * dy) ** 2
            hit |= (gap2 < self.radius_mm**2).any(axis=1)
        for polygon in self.polygons:
            hit |= _inside(polygon, cx, cy)
        return hit


def _inside(polygon: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Even-odd rule for each point against one polygon."""
    inside = np.zeros(len(x), dtype=bool)
    px, py = polygon[:, 0], polygon[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    for x0, y0, x1, y1 in zip(px, py, qx, qy):
        crosses = (y0 > y) != (y1 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        inside ^= crosses & (x < at)
    return inside
