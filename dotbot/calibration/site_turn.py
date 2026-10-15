# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Turning a whole site on the floor.

The site's frame turns with everything in it, so no number in `site.toml`
changes; a point fixed on the floor gets new site coordinates instead. Each
calibration of the site maps the stations' sweeps to those coordinates, so
each is re-expressed by the floor's move, `floor_move`, as a new calibration.
The anchor names where zero is, and zero has moved, so the turn takes a new
anchor text too.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from dotbot.calibration import lighthouse2
from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.placement import (
    PlacementRefused,
    Rigid2D,
    is_free_mode,
    place_calibration,
    spin_centres,
    suffixed_tag,
)
from dotbot.calibration.station_boxes import frame_refusal
from dotbot.site import Site

TAG_SUFFIX = "turned"
# How an anchor made by `site init` starts: no mark in the room is its zero
SELF_DEFINED = "self-defined"


class TurnRefused(ValueError):
    """A turn that cannot be made: nothing to turn, or a calibration a robot
    could not take once turned."""


def floor_move(theta_deg: float, pivot: Sequence[float]) -> Rigid2D:
    """Where a point fixed on the floor lands in the site's frame once the
    site turns by `theta_deg` about `pivot`: the opposite turn about it."""
    return Rigid2D.about((float(pivot[0]), float(pivot[1])), -float(theta_deg))


def default_pivot(site: Site) -> tuple[float, float]:
    """The middle of the site's extent, else its zero."""
    if site.extent_mm is None:
        return (0.0, 0.0)
    return (site.extent_mm[0] / 2, site.extent_mm[1] / 2)


def turn_note(theta_deg: float, pivot: Sequence[float], date: str) -> str:
    return (
        f"Turned {theta_deg:g} deg about ({pivot[0]:g}, {pivot[1]:g}) mm on "
        f"{date}: zero turned with the site."
    )


def noted_anchor(anchor: str, note: str) -> str:
    return f"{anchor.rstrip()} {note}" if anchor.strip() else note


def anchor_marks(site: Site, calibrations: Iterable[Calibration]) -> list[str]:
    """Why turning `site` moves zero off something measured on the floor;
    empty when its zero is self-defined and no calibration was measured
    from it."""
    out = []
    if not site.anchor.strip().lower().startswith(SELF_DEFINED):
        out.append(
            f"the anchor ({site.anchor or 'none'!s}) is not self-defined: it "
            "names a mark in the room, and the turn takes zero and the axes "
            "off it"
        )
    for cal in calibrations:
        if cal.placements and not is_free_mode(cal):
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
) -> Calibration:
    """`source` re-expressed for `site` turned by `theta_deg` about `pivot`,
    recording `anchor`, as a new calibration.

    Every homography becomes `floor_move . H` and every placement point
    moves with it. The stations' rectangles and the fence are site
    numbers, and stay as they are. Refused when `source` is not in `site`'s
    frame, was edited by hand, or when a spin centre or placement point
    would land below zero.
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
    try:
        moved = place_calibration(
            source, site, floor_move(theta_deg, pivot), reanchor=True
        )
    except PlacementRefused as exc:
        raise TurnRefused(f"calibration {source.id8}: {exc}") from exc
    rects = {st.index: st.valid_mm for st in source.stations}
    return dataclasses.replace(
        moved,
        site=Site(name=site.name, anchor=anchor),
        valid_mm=source.valid_mm,
        stations=[
            dataclasses.replace(st, valid_mm=rects[st.index]) for st in moved.stations
        ],
        tag=suffixed_tag(source.tag, TAG_SUFFIX, taken_tags),
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
) -> list[tuple[Calibration, Path]]:
    """Write every planned calibration, then `site_text` with its anchor
    changed through `write_site`: a failure part way leaves the site's
    anchor, and so its frame, as it was."""
    from dotbot import site_toml
    from dotbot.calibration.placement import save_new

    text = site_toml.anchored_text(site_text, anchor)
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
) -> list[Calibration]:
    """Every source turned, or TurnRefused naming the first that cannot be;
    nothing is written."""
    if not sources:
        raise TurnRefused("no calibration of the site to turn")
    if abs(((theta_deg + 180) % 360) - 180) < 1e-9:
        raise TurnRefused("a turn of 0 degrees leaves every calibration as it is")
    if anchor.strip() == site.anchor.strip():
        raise TurnRefused(
            "the anchor still reads as before the turn: say where zero is now, "
            "or append a note"
        )
    taken = list(taken_tags)
    out = []
    for source in sources:
        result = turned(source, site, theta_deg, pivot, anchor, taken_tags=taken)
        if result.tag:
            taken.append(result.tag)
        out.append(result)
    return out
