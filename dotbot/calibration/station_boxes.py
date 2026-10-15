# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Changing where each station of a calibration is trusted.

A station's `valid_mm` is the rectangle its fixes are believed in. `rebox`
makes a new calibration with some of those rectangles changed and everything
else, homographies included, as it was; the calibration it came from is
never written.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence

from dotbot.calibration import lighthouse2
from dotbot.calibration.conics import FREE_FRAME_ANCHOR
from dotbot.calibration.lighthouse2 import Calibration, station_label, union_rect
from dotbot.calibration.placement import spin_centres, suffixed_tag
from dotbot.site import Site

TAG_SUFFIX = "boxes"

Rect = tuple[int, int, int, int]


class BoxesRefused(ValueError):
    """A calibration whose rectangles may not be changed here, or a rectangle
    a robot cannot take."""


def frame_refusal(file_site: Site, site: Site) -> str | None:
    """Why a calibration recorded in `file_site` is not in `site`'s frame,
    or None when it is."""
    if file_site.anchor == FREE_FRAME_ANCHOR:
        return (
            "it is a free-mode spin calibration, in its own frame: place it on "
            "the site first"
        )
    try:
        lighthouse2.check_calibration_site(file_site, site, None)
    except ValueError as exc:
        return str(exc)
    return None


def rect_refusal(rect: Sequence[int], site: Site) -> str | None:
    """Why `[x_min, y_min, x_max, y_max]` cannot be a station's rectangle on
    `site`, or None when it can."""
    x0, y0, x1, y1 = (int(v) for v in rect)
    if x1 <= x0 or y1 <= y0:
        return "is empty"
    if x0 < 0 or y0 < 0:
        return "reaches below zero, where a robot cannot report a position"
    if site.extent_mm is not None:
        width, height = site.extent_mm
        if x1 > width or y1 > height:
            return f"reaches outside the site's extent {width} x {height} mm"
    try:
        lighthouse2.valid_mm_as_bytes((x0, y0, x1, y1))
    except ValueError as exc:
        return str(exc)
    return None


def reboxed(
    source: Calibration,
    site: Site,
    rects: Mapping[int, Sequence[int]],
    *,
    tag: str | None = None,
    taken_tags: Iterable[str] = (),
) -> Calibration:
    """`source` with the stations named in `rects` given those rectangles,
    as a new calibration; the fence becomes their union.

    `tag` defaults to the source's, suffixed `-boxes` and numbered when
    taken. Refused when `source` is not in `site`'s frame, was edited by
    hand, or leaves every rectangle as it was, and for a rectangle
    `rect_refusal` names.
    """
    why = frame_refusal(source.site, site)
    if why is not None:
        raise BoxesRefused(f"calibration {source.id8} is not in site {site.name}'s frame: {why}")
    try:
        lighthouse2.pushed_id(source)
    except ValueError as exc:
        raise BoxesRefused(str(exc)) from exc
    indices = {st.index for st in source.stations}
    unknown = sorted(set(rects) - indices)
    if unknown:
        raise BoxesRefused(
            f"calibration {source.id8} has no station {', '.join(map(str, unknown))}; "
            f"it has {', '.join(map(str, sorted(indices)))}"
        )
    refused = []
    for index, rect in sorted(rects.items()):
        why = rect_refusal(rect, site)
        if why is not None:
            refused.append(f"{station_label(index)}'s rectangle {list(rect)} {why}")
    if refused:
        raise BoxesRefused("; ".join(refused))
    stations = [
        (
            dataclasses.replace(st, valid_mm=tuple(int(v) for v in rects[st.index]))
            if st.index in rects
            else st
        )
        for st in source.stations
    ]
    if all(a.valid_mm == b.valid_mm for a, b in zip(stations, source.stations)):
        raise BoxesRefused(
            f"every rectangle of {source.id8} is as it was; nothing to write"
        )
    taken = list(taken_tags)
    if tag is None:
        tag = suffixed_tag(source.tag, TAG_SUFFIX, taken)
    elif tag and tag.lower() in {t.lower() for t in taken}:
        raise BoxesRefused(f"tag {tag!r} is taken by another calibration of {site.name}")
    return dataclasses.replace(
        source,
        valid_mm=union_rect(st.valid_mm for st in stations),
        stations=stations,
        tag=tag,
        edited_from=source.id,
        path=None,
        stored_id="",
    )


def _inside(rect: Sequence[int], x: float, y: float) -> bool:
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def coverage_warnings(calibration: Calibration) -> list[str]:
    """One line per station whose rectangle leaves out spin circles or
    placement points that station saw."""
    out = []
    circles = spin_centres(calibration)
    for st in sorted(calibration.stations, key=lambda s: s.index):
        names = sorted(
            {
                c["name"]
                for c in circles.get(st.index, [])
                if not _inside(st.valid_mm, c["x"], c["y"])
            }
        )
        points = sum(
            1
            for placement in calibration.placements
            for sample in placement.samples
            if sample.station == st.index
            and not _inside(st.valid_mm, *placement.points_mm[sample.point])
        )
        left_out = []
        if names:
            left_out.append(
                f"{len(names)} spin circle(s) ({', '.join(names[:3])}"
                + (f" and {len(names) - 3} more" if len(names) > 3 else "")
                + ")"
            )
        if points:
            left_out.append(f"{points} placement point(s)")
        if left_out:
            out.append(
                f"{station_label(st.index)}'s rectangle {list(st.valid_mm)} leaves "
                f"out {' and '.join(left_out)} it was calibrated on"
            )
    return out


def push_line(calibration: Calibration) -> str:
    return (
        f"dotbot swarm calibrate-lh2 push {calibration.id8} "
        f"--site {calibration.site.name}"
    )
