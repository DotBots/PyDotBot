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
        wall_segments = _segments(
            [np.asarray(w, dtype=float) for w in walls], closed=False
        )
        polygon_segments = [_segments([p], closed=True) for p in self.polygons]
        self.segments = np.vstack([wall_segments, *polygon_segments])
        # The obstacle each segment bounds, -1 for a wall
        self.owner = np.concatenate(
            [np.full(len(wall_segments), -1)]
            + [np.full(len(seg), k) for k, seg in enumerate(polygon_segments)]
        ).astype(int)
        self._lo = np.minimum(self.segments[:, :2], self.segments[:, 2:])
        self._hi = np.maximum(self.segments[:, :2], self.segments[:, 2:])
        self._boxes = [(p.min(axis=0), p.max(axis=0)) for p in self.polygons]

    def __bool__(self) -> bool:
        return len(self.segments) > 0

    @classmethod
    def from_site(cls, site) -> Barriers | None:
        """The site's barriers, or None when it has none."""
        if site is None or not (site.walls or site.obstacles):
            return None
        return cls([w.points for w in site.walls], [o.points for o in site.obstacles])

    def centres(self, x, y, heading_deg) -> tuple[np.ndarray, np.ndarray]:
        """Each body's disc centre for a pose (axle midpoint and heading)."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        y = np.atleast_1d(np.asarray(y, dtype=float))
        fx, fy = forward(np.atleast_1d(np.asarray(heading_deg, dtype=float)))
        return x + self.centre_ahead_mm * fx, y + self.centre_ahead_mm * fy

    def blocked(self, x, y, heading_deg) -> np.ndarray:
        """Whether each pose meets a barrier."""
        cx, cy = self.centres(x, y, heading_deg)
        hit = np.zeros(len(cx), dtype=bool)
        for i, j, gap2, _, _ in self._near(cx, cy):
            hit[i[gap2 < self.radius_mm**2]] = True
        for k in range(len(self.polygons)):
            hit |= self._inside(k, cx, cy)
        return hit

    def refused(self, before, after) -> np.ndarray:
        """Which moves from the poses `before` to `after`, each (x, y,
        heading_deg), the barriers stop: one bringing the body closer to a
        barrier it touches, carrying its centre across one, or into an
        obstacle. A body already touching may move off or along it."""
        x0, y0 = self.centres(*before)
        x1, y1 = self.centres(*after)
        stop = np.zeros(len(x1), dtype=bool)
        r2 = self.radius_mm**2
        inside0 = [self._inside(k, x0, y0) for k in range(len(self.polygons))]
        for k, was_in in enumerate(inside0):
            stop |= ~was_in & self._inside(k, x1, y1)
        for i, j, gap2, _, _ in self._near(x1, y1, x0, y0):
            owner = self.owner[j]
            # An edge of the obstacle a body starts inside never holds it in
            exempt = np.zeros(len(i), dtype=bool)
            for k, was_in in enumerate(inside0):
                exempt |= (owner == k) & was_in[i]
            seg = self.segments[j]
            before2 = _gap2(x0[i], y0[i], seg)
            closer = (gap2 < r2) & (gap2 < before2 - 1e-9)
            crosses = _crosses(x0[i], y0[i], x1[i], y1[i], seg)
            stop[i[(closer | crosses) & ~exempt]] = True
        return stop

    def _near(self, x, y, x0=None, y0=None):
        """The (body, segment) pairs whose boxes, grown by the disc, overlap
        the body's path; yields (bodies, segments, new gap squared, ...)."""
        if not len(self.segments) or not len(x):
            return
        x0 = x if x0 is None else x0
        y0 = y if y0 is None else y0
        r = self.radius_mm
        lo_x, hi_x = np.minimum(x, x0) - r, np.maximum(x, x0) + r
        lo_y, hi_y = np.minimum(y, y0) - r, np.maximum(y, y0) + r
        near = (
            (lo_x[:, None] <= self._hi[None, :, 0])
            & (hi_x[:, None] >= self._lo[None, :, 0])
            & (lo_y[:, None] <= self._hi[None, :, 1])
            & (hi_y[:, None] >= self._lo[None, :, 1])
        )
        i, j = np.nonzero(near)
        if len(i):
            yield i, j, _gap2(x[i], y[i], self.segments[j]), x0[i], y0[i]

    def _inside(self, k: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Even-odd rule for each point against obstacle `k`."""
        lo, hi = self._boxes[k]
        inside = np.zeros(len(x), dtype=bool)
        candidate = (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
        if not candidate.any():
            return inside
        px, py = x[candidate][:, None], y[candidate][:, None]
        polygon = self.polygons[k]
        x0, y0 = polygon[:, 0][None, :], polygon[:, 1][None, :]
        x1, y1 = (
            np.roll(polygon[:, 0], -1)[None, :],
            np.roll(polygon[:, 1], -1)[None, :],
        )
        crosses = (y0 > py) != (y1 > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
        inside[candidate] = (np.count_nonzero(crosses & (px < at), axis=1) % 2) == 1
        return inside


def _gap2(x: np.ndarray, y: np.ndarray, seg: np.ndarray) -> np.ndarray:
    """Squared distance from each point to its segment, row for row."""
    ax, ay, bx, by = seg[:, 0], seg[:, 1], seg[:, 2], seg[:, 3]
    dx, dy = bx - ax, by - ay
    length2 = np.maximum(dx * dx + dy * dy, 1e-12)
    t = np.clip(((x - ax) * dx + (y - ay) * dy) / length2, 0, 1)
    return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2


def _crosses(x0, y0, x1, y1, seg: np.ndarray) -> np.ndarray:
    """Whether each path (x0, y0) -> (x1, y1) properly crosses its segment."""
    ax, ay, bx, by = seg[:, 0], seg[:, 1], seg[:, 2], seg[:, 3]

    def side(px, py, qx, qy, rx, ry):
        return np.sign((qx - px) * (ry - py) - (qy - py) * (rx - px))

    return (side(ax, ay, bx, by, x0, y0) * side(ax, ay, bx, by, x1, y1) < 0) & (
        side(x0, y0, x1, y1, ax, ay) * side(x0, y0, x1, y1, bx, by) < 0
    )
