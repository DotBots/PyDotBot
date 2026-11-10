# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Moving a site's frame on the floor: turning it about a point, shifting
its zero, or both, as one change with a new frame id.

The site's numbers stay as they are, since the floor rectangle moves with
the frame; a point fixed on the floor gets new coordinates instead, so the
served calibration is re-expressed by the floor's move as a new file
recording the new frame id. Data logged before the change stays in the old
frame.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.site_turn import TurnRefused, floor_move, new_frame_id, turned
from dotbot.site import Site

__all__ = ["floor_move", "largest_shift", "moved", "new_frame_id"]


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
            moved(source, site, theta_deg, pivot, (shift[0] * scale, shift[1] * scale), "", "00000000")
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
