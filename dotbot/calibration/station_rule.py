# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Which station's solve a robot keeps for one fix, as its bootloader picks it.

Every station with a fresh pulse pair and a homography offers its own solve,
in index order. A non-finite solve, or one outside its own station's box, is
dropped; of the rest, the one nearest its own box's centre is kept, and an
exact tie keeps the station offered first, the lower index.

This mirrors swarmit's `lh2_select.c` and `localization_get_position()`;
`station_rule.json` beside this file holds cases every copy of the rule runs
(`python -m dotbot.calibration.station_rule` rewrites it).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping, Sequence

Rect = tuple[int, int, int, int]

STATIONS = 16
# lh2_select.h: an all-0xFF stored box reads as (0, 0, this, this), mm
RECT_MAX_DEFAULT = 100_000
STORED_ABSENT = 0xFFFFFFFF
FIXTURES_PATH = Path(__file__).with_name("station_rule.json")


def resolve_rect(stored: Sequence[int]) -> Rect:
    """The box a stored one stands for."""
    if all(int(v) == STORED_ABSENT for v in stored):
        return (0, 0, RECT_MAX_DEFAULT, RECT_MAX_DEFAULT)
    x0, y0, x1, y1 = (int(v) for v in stored)
    return (x0, y0, x1, y1)


def contains(rect: Sequence[int], x: float, y: float) -> bool:
    """Whether (x, y) is inside `rect`, edges included; NaN is outside."""
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def centre(rect: Sequence[int]) -> tuple[float, float]:
    return (0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3]))


def _d2(rect: Sequence[int], x: float, y: float) -> float:
    cx, cy = centre(rect)
    return (x - cx) ** 2 + (y - cy) ** 2


def select(
    solves: Mapping[int, tuple[float, float]], rects: Mapping[int, Sequence[int]]
) -> int | None:
    """The station whose solve is kept, or None when no solve is.

    `solves` holds the stations offered (a fresh pair and a homography),
    `rects` each station's stored box.
    """
    best: tuple[int, float] | None = None
    for station in sorted(solves):
        x, y = solves[station]
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        rect = resolve_rect(rects[station])
        if not contains(rect, x, y):
            continue
        d2 = _d2(rect, x, y)
        if best is not None and not d2 < best[1]:
            continue
        best = (station, d2)
    return None if best is None else best[0]


def candidates(rects: Mapping[int, Sequence[int]], x: float, y: float) -> tuple[int, ...]:
    """The stations that can give the fix at (x, y) when every station sees
    the robot and solves it there.

    One station: the boxes decide. Several: their boxes hold the point at
    the same distance from their centres, so the boxes do not decide and the
    stations' own disagreement does. None: no box holds the point.
    """
    inside = {
        s: _d2(resolve_rect(r), x, y)
        for s, r in sorted(rects.items())
        if contains(resolve_rect(r), x, y)
    }
    if not inside:
        return ()
    least = min(inside.values())
    return tuple(s for s, d2 in inside.items() if d2 == least)


def shared_centres(rects: Mapping[int, Sequence[int]]) -> list[tuple[int, ...]]:
    """Groups of two or more stations whose boxes have one centre, so the
    boxes decide nothing between them wherever they overlap."""
    groups: dict[tuple[float, float], list[int]] = {}
    for s, r in sorted(rects.items()):
        groups.setdefault(centre(resolve_rect(r)), []).append(s)
    return [tuple(g) for g in groups.values() if len(g) > 1]


def _span(lo: int, hi: int) -> str:
    return f"{lo}-{hi}"


def reading(rects: Mapping[int, Sequence[int]]) -> str:
    """The boxes in one line: each box, then who gives the fix where they meet."""
    rects = {s: resolve_rect(r) for s, r in sorted(rects.items())}
    if not rects:
        return "no station"
    parts = []
    shared = {s for g in shared_centres(rects) for s in g}
    for group in shared_centres(rects):
        same = len({rects[s] for s in group}) == 1
        names = " and ".join(f"S{s}" for s in group)
        parts.append(
            f"{names} share {'one box' if same else 'a centre'}: the boxes do not decide"
        )
    for s, (x0, y0, x1, y1) in rects.items():
        if s in shared:
            continue
        if x1 - x0 <= 1 or y1 - y0 <= 1:
            parts.append(f"S{s} only in a {max(min(x1 - x0, y1 - y0), 0)} mm strip")
        else:
            parts.append(f"S{s} x {_span(x0, x1)}, y {_span(y0, y1)}")
    stations = list(rects)
    for i, a in enumerate(stations):
        for b in stations[i + 1 :]:
            ra, rb = rects[a], rects[b]
            if a in shared and b in shared:
                continue
            if ra[0] > rb[2] or rb[0] > ra[2] or ra[1] > rb[3] or rb[1] > ra[3]:
                continue
            (ax, ay), (bx, by) = centre(ra), centre(rb)
            if ay == by and ax != bx:
                parts.append(f"S{a}/S{b} handover x {0.5 * (ax + bx):g}")
            elif ax == bx and ay != by:
                parts.append(f"S{a}/S{b} handover y {0.5 * (ay + by):g}")
            elif (ax, ay) != (bx, by):
                parts.append(f"S{a}/S{b} handover halfway between their centres")
    return " · ".join(parts)


# --- Fixtures ---------------------------------------------------------------


def _number(v: float) -> float | str:
    return v if math.isfinite(v) else str(v)


def fixture_cases() -> list[dict]:
    """Cases with the station each one keeps, for every copy of the rule."""
    whole = [0, 0, 1060, 1220]
    left, right = [0, 0, 630, 1220], [430, 0, 1060, 1220]
    tie = {0: [0, 0, 541, 1220], 1: [141, 0, 1060, 1220]}
    absent = [STORED_ABSENT] * 4
    nan = float("nan")
    cases: list[dict] = []

    def add(name: str, rects: dict, solves: list, note: str) -> None:
        cases.append(
            {
                "name": name,
                "rects": {str(k): v for k, v in rects.items()},
                "solves": [[s, _number(x), _number(y)] for s, x, y in solves],
                "expect": select({s: (x, y) for s, x, y in solves}, rects),
                "note": note,
            }
        )

    add(
        "equal boxes, S1 solve nearer the shared centre",
        {0: whole, 1: whole},
        [(0, 300.0, 500.0), (1, 300.4, 500.3)],
        "the boxes decide nothing; 0.5 mm decides",
    )
    add(
        "equal boxes, S0 solve nearer the shared centre",
        {0: whole, 1: whole},
        [(0, 300.4, 500.3), (1, 300.0, 500.0)],
        "the same point, the other way round",
    )
    add(
        "equal boxes, solves identical",
        {0: whole, 1: whole},
        [(0, 300.0, 500.0), (1, 300.0, 500.0)],
        "an exact tie keeps the lower index",
    )
    add(
        "split boxes, left of the handover",
        {0: left, 1: right},
        [(0, 500.0, 600.0), (1, 500.2, 600.1)],
        "S0's centre is x 315, S1's x 745",
    )
    add(
        "split boxes, right of the handover",
        {0: left, 1: right},
        [(0, 560.0, 600.0), (1, 560.1, 600.0)],
        "handover at x 530",
    )
    add(
        "split boxes, on the handover line",
        {0: left, 1: right},
        [(0, 530.0, 610.0), (1, 530.0, 610.0)],
        "equidistant: the lower index",
    )
    add(
        "split boxes, S0 only",
        {0: left, 1: right},
        [(0, 200.0, 600.0), (1, 200.0, 600.0)],
        "outside S1's own box",
    )
    add(
        "split boxes, S1 only",
        {0: left, 1: right},
        [(0, 900.0, 600.0), (1, 900.0, 600.0)],
        "outside S0's own box",
    )
    add(
        "outside every box",
        {0: left, 1: right},
        [(0, 1100.0, 600.0), (1, 1100.0, 600.0)],
        "no fix",
    )
    add(
        "box edge is inside",
        {0: [0, 0, 630, 1220]},
        [(0, 630.0, 1220.0)],
        "edges included",
    )
    add(
        "just outside the edge",
        {0: [0, 0, 630, 1220]},
        [(0, 630.001, 600.0)],
        "dropped",
    )
    add(
        "not finite",
        {0: whole, 1: whole},
        [(0, nan, 500.0), (1, 300.0, 500.0)],
        "a NaN solve is dropped",
    )
    add(
        "all 0xFF reads as the default",
        {0: absent},
        [(0, 50000.0, 99999.0)],
        "0 to 100000 mm",
    )
    add(
        "only one station sees the robot",
        {0: whole, 1: whole},
        [(1, 300.0, 500.0)],
        "a station without a fresh pair is not offered",
    )
    add(
        "strip box",
        {0: [1059, 0, 1060, 1220], 1: whole},
        [(0, 300.0, 500.0), (1, 300.2, 500.0)],
        "S0 only inside its 1 mm strip",
    )
    add(
        "boxes tied at x 435.5, near the line",
        tie,
        [(0, 436.0, 600.0), (1, 436.0, 600.0)],
        "handover at x 435.5",
    )
    add(
        "boxes tied at x 435.5, other side",
        tie,
        [(0, 435.0, 600.0), (1, 435.0, 600.0)],
        "handover at x 435.5",
    )
    return cases


def fixture_points() -> list[dict]:
    """Points with the stations that can give the fix there, for the map."""
    whole = [0, 0, 1060, 1220]
    left, right = [0, 0, 630, 1220], [430, 0, 1060, 1220]
    points: list[dict] = []

    def add(name: str, rects: dict, x: float, y: float) -> None:
        points.append(
            {
                "name": name,
                "rects": {str(k): v for k, v in rects.items()},
                "point": [x, y],
                "expect": list(candidates(rects, x, y)),
            }
        )

    add("equal boxes: the boxes do not decide", {0: whole, 1: whole}, 300.0, 500.0)
    add("split boxes, left of the handover", {0: left, 1: right}, 500.0, 600.0)
    add("split boxes, right of the handover", {0: left, 1: right}, 560.0, 600.0)
    add("split boxes, on the handover line", {0: left, 1: right}, 530.0, 600.0)
    add("split boxes, S1 only", {0: left, 1: right}, 900.0, 100.0)
    add("outside every box", {0: left, 1: right}, 1100.0, 600.0)
    add("all 0xFF reads as the default", {0: [STORED_ABSENT] * 4}, 5000.0, 5000.0)
    return points


def fixture_document() -> dict:
    return {
        "source": "dotbot/calibration/station_rule.py",
        "rule": (
            "offered in index order; a non-finite solve or one outside its own "
            "station's box is dropped; the one nearest its own box's centre is "
            "kept; an exact tie keeps the lower index"
        ),
        "cases": fixture_cases(),
        "points": fixture_points(),
    }


def fixture_text() -> str:
    return json.dumps(fixture_document(), indent=1) + "\n"


def write_fixtures(path: Path = FIXTURES_PATH) -> None:
    path.write_text(fixture_text(), encoding="utf-8")


if __name__ == "__main__":
    write_fixtures()
