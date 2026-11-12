# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Turning a whole site on the floor, and shifting its zero.

The site's frame moves, so a point fixed on the floor gets new site
coordinates. Each calibration of the site maps the stations' sweeps to those
coordinates, so each is re-expressed by the floor's move as a new
calibration, recording the new frame's id. The extent moves with the frame
and keeps its size. The coverage stays where it is on the floor: the
stations' boxes and the fence get new numbers by the same move, as the box
round each turned rectangle, cut to the extent.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from dotbot.calibration import lighthouse2
from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.placement import (
    PlacementRefused,
    Rigid2D,
    place_calibration,
    solved_in_own_frame,
    spin_centres,
    suffixed_tag,
)
from dotbot.calibration.station_boxes import frame_refusal
from dotbot.site import Site

TAG_SUFFIX = "turned"
SHIFT_SUFFIX = "moved"
# How an anchor made by `site init` starts: no mark in the room is its zero
SELF_DEFINED = "self-defined"


class TurnRefused(ValueError):
    """A turn that cannot be made: nothing to turn, or a calibration a robot
    could not take once turned."""


def floor_move(
    theta_deg: float, pivot: Sequence[float], shift: Sequence[float] = (0.0, 0.0)
) -> Rigid2D:
    """Where a point fixed on the floor lands in the site's frame once the
    site turns by `theta_deg` about `pivot` and its zero moves by `shift`:
    the opposite turn about the pivot, then the opposite shift."""
    return Rigid2D.about(
        (float(pivot[0]), float(pivot[1])),
        -float(theta_deg),
        (-float(shift[0]), -float(shift[1])),
    )


def new_frame_id(
    old: str, theta_deg: float, pivot: Sequence[float], shift: Sequence[float]
) -> str:
    """8 hex digits naming the frame `old` becomes after the move."""
    text = (
        f"{old}\nturn {float(theta_deg):g} about {float(pivot[0]):g},{float(pivot[1]):g}"
        f"\nshift {float(shift[0]):g},{float(shift[1]):g}"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def square_turn(theta_deg: float) -> bool:
    """Whether a turn by `theta_deg` keeps a rectangle a rectangle."""
    return abs(((float(theta_deg) + 45) % 90) - 45) < 1e-9


def widened_note(theta_deg: float) -> list[str]:
    """One line when the turn widens each coverage to stay a rectangle."""
    if square_turn(theta_deg):
        return []
    return [
        "each station's coverage and their union are widened to the rectangles "
        "round them once turned"
    ]


def kept(
    move: Rigid2D, rect: Sequence[float] | None, extent: Sequence[int] | None
) -> tuple[int, int, int, int] | None:
    """`rect`, fixed on the floor, in the moved frame's numbers, cut to
    `extent`; only at zero when nothing of it lies in the extent, and None
    when nothing of it is left right of and below zero."""
    if rect is None:
        return None
    x0, y0, x1, y1 = move.box(rect)
    at_zero = (max(0, x0), max(0, y0), x1, y1)
    if at_zero[0] >= at_zero[2] or at_zero[1] >= at_zero[3]:
        return None
    if extent is None:
        return at_zero
    cut = (*at_zero[:2], min(extent[0], x1), min(extent[1], y1))
    return cut if cut[0] < cut[2] and cut[1] < cut[3] else at_zero


def cut_notes(
    source: Calibration, move: Rigid2D, extent: Sequence[int] | None
) -> list[str]:
    """One line per station whose coverage reaches outside `extent` once
    moved, saying whether `kept` cut it to the extent."""
    if extent is None:
        return []
    out = []
    for st in source.stations:
        if st.coverage_mm is None:
            continue
        box = move.box(st.coverage_mm)
        if box[0] >= 0 and box[1] >= 0 and box[2] <= extent[0] and box[3] <= extent[1]:
            continue
        inside = kept(move, st.coverage_mm, extent)
        cut = inside is not None and inside[2] <= extent[0] and inside[3] <= extent[1]
        out.append(
            f"{lighthouse2.station_label(st.index)}'s coverage reaches outside the "
            + ("extent once moved, and is cut to it" if cut else "extent once moved")
        )
    return out


def default_pivot(site: Site) -> tuple[float, float]:
    """The middle of the site's extent, else its zero."""
    if site.extent_mm is None:
        return (0.0, 0.0)
    return (site.extent_mm[0] / 2, site.extent_mm[1] / 2)


def anchor_marks(site: Site, calibrations: Iterable[Calibration]) -> list[str]:
    """Why turning `site` moves zero off something measured on the floor;
    empty when its zero is self-defined and no calibration was measured
    from it."""
    out = []
    if not site.anchor.strip().lower().startswith(SELF_DEFINED):
        out.append(
            f"the anchor ({site.anchor or 'none'!s}) is not self-defined: it "
            "names a mark on the floor, and the turn takes zero and the axes "
            "off it"
        )
    for cal in calibrations:
        if cal.placements and not solved_in_own_frame(cal):
            out.append(
                f"calibration {cal.id8} was collected at points measured from "
                "the anchor"
            )
    return out


def in_frame(site: Site, paths: Iterable[Path]) -> list[Calibration]:
    """The calibrations among `paths` in `site`'s frame, one per id."""
    out, seen = [], set()
    for path in paths:
        try:
            cal = lighthouse2.read_calibration_file(path)
        except (OSError, ValueError, KeyError):
            continue
        if cal.id in seen or frame_refusal(cal.site, site) is not None:
            continue
        seen.add(cal.id)
        out.append(cal)
    return out


def turned(
    source: Calibration,
    site: Site,
    theta_deg: float,
    pivot: Sequence[float],
    anchor: str,
    *,
    taken_tags: Iterable[str] = (),
    move: Rigid2D | None = None,
    frame: str | None = None,
    extent: Sequence[int] | None = None,
) -> Calibration:
    """`source` re-expressed for `site` turned by `theta_deg` about `pivot`,
    or moved by `move` when given, recording `anchor` and the frame id
    `frame`, as a new calibration.

    Every homography becomes `floor_move . H` and every placement point
    moves with it. The stations' boxes and the fence stay where they are on
    the floor, so they get new numbers by the same move (`widened_note`),
    cut to `extent` (the site's when None). The tag takes `-turned` for a
    turn, else `-moved`. Refused when `source` is not in `site`'s frame,
    was edited by hand, or when a spin centre, a placement point or a
    whole coverage would land below zero.
    """
    why = frame_refusal(source.site, site)
    if why is not None:
        raise TurnRefused(
            f"calibration {source.id8} is not in site {site.name}'s frame: {why}"
        )
    try:
        lighthouse2.pushed_id(source)
    except ValueError as exc:
        raise TurnRefused(str(exc)) from exc
    if site.extent_mm is None:
        raise TurnRefused(f"site {site.name} has no extent to turn")
    move = move or floor_move(theta_deg, pivot)
    try:
        moved = place_calibration(source, site, move, reanchor=True)
    except PlacementRefused as exc:
        raise TurnRefused(f"calibration {source.id8}: {exc}") from exc
    extent = extent if extent is not None else site.extent_mm
    rects = {st.index: kept(move, st.coverage_mm, extent) for st in source.stations}
    lost = [
        lighthouse2.station_label(st.index)
        for st in source.stations
        if st.coverage_mm is not None and rects[st.index] is None
    ]
    if lost:
        raise TurnRefused(
            f"calibration {source.id8}: {' and '.join(lost)}'s coverage would "
            "land wholly below zero, where a robot cannot report a position"
        )
    turns = abs(((move.theta_deg + 180) % 360) - 180) > 1e-9
    suffix = TAG_SUFFIX if turns else SHIFT_SUFFIX
    return dataclasses.replace(
        moved,
        site=Site(name=site.name, anchor=anchor, frame=frame),
        stations=[
            dataclasses.replace(st, coverage_mm=rects[st.index])
            for st in moved.stations
        ],
        tag=suffixed_tag(source.tag, suffix, taken_tags),
        placed_from=source.placed_from,
        edited_from=source.id,
    )


def outside_warnings(calibration: Calibration, site: Site) -> list[str]:
    """One line when spin centres or placement points land outside the
    site's extent once turned, where robots drop their positions."""
    if site.extent_mm is None:
        return []
    width, height = site.extent_mm
    names = sorted(
        {
            c["name"]
            for circles in spin_centres(calibration).values()
            for c in circles
            if c["x"] > width or c["y"] > height
        }
    )
    points = sum(
        1
        for p in calibration.placements
        for x, y in p.points_mm
        if x > width or y > height
    )
    out = []
    if names:
        out.append(
            f"{calibration.id8}: {len(names)} spin circle(s) ({', '.join(names[:3])}) "
            "land outside the site's extent, where robots drop their positions"
        )
    if points:
        out.append(
            f"{calibration.id8}: {points} placement point(s) land outside the "
            "site's extent"
        )
    return out


def save_turn(
    planned: Sequence[Calibration],
    site_text: str,
    anchor: str,
    write_site: Callable[[str], None],
    move: Rigid2D,
) -> list[tuple[Calibration, Path]]:
    """Write every planned calibration, then `site_text` with its anchor and
    frame id changed and its areas, walls, obstacles and objects renumbered
    by the floor's `move`, the extent keeping its size, through
    `write_site`: a failure part way leaves the site's frame as it was."""
    from dotbot import site_draft, site_toml
    from dotbot.calibration.placement import save_new

    model = site_toml.site_model(site_toml.parse(site_text))
    for key in ("areas", "objects"):
        for entry in model.get(key) or []:
            entry["was"] = entry["name"]
    for key in ("walls", "obstacles"):
        for i, entry in enumerate(model.get(key) or []):
            entry["was"] = i
    model = site_draft.moved_site(model, move)
    model["anchor"] = anchor or None
    model["frame"] = planned[0].site.frame if planned else model.get("frame")
    text = site_toml.patched_text(site_text, model)
    saved = [save_new(cal) for cal in planned]
    write_site(text)
    return saved


def plan_turn(
    sources: Sequence[Calibration],
    site: Site,
    theta_deg: float,
    pivot: Sequence[float],
    anchor: str,
    taken_tags: Iterable[str] = (),
    shift: Sequence[float] = (0.0, 0.0),
) -> list[Calibration]:
    """Every source moved into the new frame, or TurnRefused naming the
    first that cannot be; nothing is written."""
    if not sources:
        raise TurnRefused("no calibration of the site to turn")
    turn = abs(((theta_deg + 180) % 360) - 180) >= 1e-9
    if not turn and abs(shift[0]) < 1e-9 and abs(shift[1]) < 1e-9:
        raise TurnRefused("nothing moves: give a turn or a shift of zero")
    frame = new_frame_id(site.frame_id, theta_deg, pivot, shift)
    move = floor_move(theta_deg, pivot, shift)
    taken = list(taken_tags)
    out = []
    for source in sources:
        result = turned(
            source,
            site,
            theta_deg,
            pivot,
            anchor,
            taken_tags=taken,
            move=move,
            frame=frame,
        )
        if result.tag:
            taken.append(result.tag)
        out.append(result)
    return out
