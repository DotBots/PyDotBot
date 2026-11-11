# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Moving a site's frame on the floor: turning it about a point, shifting
its zero, or both, as one change with a new frame id.

A point fixed on the floor gets new coordinates, so the served calibration
is re-expressed by the floor's move as a new file recording the new frame
id; its coverage stays where it is on the floor, with new numbers. Data
logged before the change stays in the old frame.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.site_turn import TurnRefused, floor_move, new_frame_id, turned
from dotbot.site import Site

__all__ = [
    "SpotFit",
    "fit_spots",
    "floor_move",
    "largest_shift",
    "moved",
    "new_frame_id",
]


def moved(
    source: Calibration,
    site: Site,
    theta_deg: float,
    pivot: Sequence[float],
    shift: Sequence[float],
    note: str,
    frame: str,
    taken_tags: Iterable[str] = (),
) -> Calibration:
    """`source` re-expressed in the moved frame `frame`, recording `note` as
    where zero is; TurnRefused when a measured point would fall below zero."""
    if abs(theta_deg) < 1e-9 and abs(shift[0]) < 1e-9 and abs(shift[1]) < 1e-9:
        raise TurnRefused("nothing moves: give a turn or a shift")
    return turned(
        source,
        site,
        theta_deg,
        pivot,
        note,
        taken_tags=taken_tags,
        move=floor_move(theta_deg, pivot, shift),
        frame=frame,
    )


def largest_shift(
    source: Calibration,
    site: Site,
    theta_deg: float,
    pivot: Sequence[float],
    shift: Sequence[float],
    steps: int = 24,
) -> tuple[int, int] | None:
    """The largest whole-mm shift along `shift`'s direction that keeps every
    measured point at or above zero with this turn; None when even no shift
    is legal."""

    def legal(scale: float) -> bool:
        try:
            moved(
                source,
                site,
                theta_deg,
                pivot,
                (shift[0] * scale, shift[1] * scale),
                "",
                "00000000",
            )
        except TurnRefused:
            return False
        return True

    if theta_deg and not legal(0.0):
        return None
    lo, hi = 0.0, 1.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        if legal(mid):
            lo = mid
        else:
            hi = mid
    best = (int(shift[0] * lo), int(shift[1] * lo))
    return best if best != (0, 0) or theta_deg else None


@dataclass(frozen=True)
class SpotFit:
    """A move of the origin, as `moved` takes it, and each spot's distance
    from its read under it, mm."""

    theta_deg: float
    pivot: tuple[float, float]
    shift: tuple[float, float]
    residuals_mm: list[float]


def fit_spots(
    spots: Sequence[Sequence[float]], reads: Sequence[Sequence[float]]
) -> SpotFit:
    """The rigid move (a turn and a shift, no scale) that lays `spots`, in
    the frame to anchor, onto `reads`, where robots on them read themselves
    in the current frame, by least squares. One spot shifts only."""
    if not spots or len(spots) != len(reads):
        raise ValueError("give one read for each spot, at least one")
    n = len(spots)
    cs = (sum(p[0] for p in spots) / n, sum(p[1] for p in spots) / n)
    cr = (sum(p[0] for p in reads) / n, sum(p[1] for p in reads) / n)
    theta = 0.0
    if n > 1:
        dot = cross = 0.0
        for s, r in zip(spots, reads):
            sx, sy = s[0] - cs[0], s[1] - cs[1]
            rx, ry = r[0] - cr[0], r[1] - cr[1]
            dot += sx * rx + sy * ry
            cross += sx * ry - sy * rx
        theta = math.degrees(math.atan2(cross, dot))
    theta = round(theta, 2)
    pivot = (round(cr[0], 1), round(cr[1], 1))
    shift = (round(cr[0] - cs[0], 1), round(cr[1] - cs[1], 1))
    c, s_ = math.cos(math.radians(theta)), math.sin(math.radians(theta))
    residuals = []
    for p, r in zip(spots, reads):
        x, y = p[0] + shift[0] - pivot[0], p[1] + shift[1] - pivot[1]
        ox, oy = pivot[0] + c * x - s_ * y, pivot[1] + s_ * x + c * y
        residuals.append(round(math.hypot(ox - r[0], oy - r[1]), 1))
    return SpotFit(theta, pivot, shift, residuals)
