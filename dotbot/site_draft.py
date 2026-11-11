# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's draft, composed for one Save: site.toml and at most one
new calibration.

A calibration edit starts from one file and takes, in order, a placement
into the room or a move of the room's origin, then new station rectangles.
A move of the origin keeps everything physical where it is on the floor:
areas, walls, obstacles, objects, coverage and spin circles get new numbers,
and the extent grows to hold them.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence

import numpy as np
from pydantic import BaseModel

from dotbot.calibration import site_frame, site_turn
from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.placement import (
    PlacementRefused,
    Rigid2D,
    place_calibration,
    solved_in_own_frame,
    spin_centres,
    suffixed_tag,
)
from dotbot.calibration.station_boxes import (
    BoxesRefused,
    coverage_warnings,
    reboxed,
)
from dotbot.site import Site

Rect = tuple[int, int, int, int]


class ComposeRefused(ValueError):
    """A draft that cannot be saved as one calibration; `offer` is the
    largest legal shift along the one asked, when there is one."""

    def __init__(self, message: str, offer: tuple[int, int] | None = None):
        super().__init__(message)
        self.offer = offer


class Move(BaseModel):
    """A move of the room's origin, in the saved frame's mm: a turn by
    `theta_deg` about `pivot`, then zero shifted by (`dx_mm`, `dy_mm`)."""

    theta_deg: float = 0.0
    pivot: tuple[float, float] = (0.0, 0.0)
    dx_mm: float = 0.0
    dy_mm: float = 0.0

    @property
    def turns(self) -> bool:
        return abs(((self.theta_deg + 180) % 360) - 180) > 1e-9

    @property
    def moves(self) -> bool:
        return self.turns or abs(self.dx_mm) > 1e-9 or abs(self.dy_mm) > 1e-9

    @property
    def shift(self) -> tuple[float, float]:
        return (self.dx_mm, self.dy_mm)

    def floor(self) -> Rigid2D:
        """Where a point fixed on the floor lands in the moved frame."""
        return site_turn.floor_move(self.theta_deg, self.pivot, self.shift)


class Place(BaseModel):
    """A spin calibration put into the room: turned about its zero, then
    shifted, mm."""

    theta_deg: float = 0.0
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    # Move a corner-collected calibration anyway: the anchor itself moved
    reanchor: bool = False


class CalibrationEdit(BaseModel):
    """Every pending edit of one calibration."""

    # The file the edit starts from: an id, a tag or a path
    source: str
    frame: Move | None = None
    place: Place | None = None
    # Station index to `[x_min, y_min, x_max, y_max]`, in the saved result's mm
    stations: dict[int, Rect] | None = None
    # The new file's tag; None derives it from what changed
    tag: str | None = None


def _rigid(matrix: np.ndarray) -> Rigid2D:
    return Rigid2D(
        float(matrix[0, 2]),
        float(matrix[1, 2]),
        math.degrees(math.atan2(matrix[1, 0], matrix[0, 0])),
    )


def between(start: Move | None, end: Move) -> Rigid2D:
    """Where a floor point given in the frame `start` leaves lands in the
    frame `end` leaves; both moves start from the saved frame."""
    back = np.linalg.inv(start.floor().matrix()) if start else np.eye(3)
    return _rigid(end.floor().matrix() @ back)


def _cut(v: float) -> int:
    return max(0, int(round(v)))


def _heading(deg: float, turn: float) -> float:
    out = round(((deg + turn + 180) % 360) - 180, 2)
    return 180.0 if out == -180.0 else out


def moved_site(
    model: dict,
    move: Rigid2D,
    keep_rects: Iterable[Sequence[int]] = (),
    keep_points: Iterable[Sequence[float]] = (),
) -> dict:
    """`model` (the editor's site model) renumbered by `move`, every area,
    wall, obstacle and object kept where it is on the floor and cut at zero,
    with the extent grown to hold them, the floor's own far edges, and
    `keep_rects` and `keep_points` given in the moved frame."""
    turn = abs(((move.theta_deg + 180) % 360) - 180) > 1e-9
    out = dict(model)
    far_x, far_y = [], []

    def point(p: Sequence[float]) -> list[int]:
        (x, y) = move.apply([(float(p[0]), float(p[1]))])[0]
        q = [_cut(x), _cut(y)]
        far_x.append(q[0])
        far_y.append(q[1])
        return q

    areas = []
    for area in model.get("areas") or []:
        x0, y0, x1, y1 = move.box(
            (area["x"], area["y"], area["x"] + area["w"], area["y"] + area["h"])
        )
        x0, y0 = max(0, x0), max(0, y0)
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        far_x.append(x0 + w)
        far_y.append(y0 + h)
        areas.append({**area, "x": x0, "y": y0, "w": w, "h": h})
    out["areas"] = areas
    for key in ("walls", "obstacles"):
        if model.get(key) is not None:
            out[key] = [
                {**entry, "points": [point(p) for p in entry["points"]]}
                for entry in model[key]
            ]
    if model.get("objects") is not None:
        objects = []
        for obj in model["objects"]:
            x, y = point((obj["x"], obj["y"]))
            heading = obj.get("heading_deg", 0.0)
            if turn:
                heading = _heading(heading, move.theta_deg)
            objects.append({**obj, "x": x, "y": y, "heading_deg": heading})
        out["objects"] = objects
    extent = model.get("extent_mm")
    if extent is not None:
        _, _, x1, y1 = move.box((0, 0, extent[0], extent[1]))
        far_x.append(x1)
        far_y.append(y1)
        for rect in keep_rects:
            far_x.append(int(rect[2]))
            far_y.append(int(rect[3]))
        for p in keep_points:
            far_x.append(math.ceil(p[0]))
            far_y.append(math.ceil(p[1]))
        out["extent_mm"] = [max(1, max(far_x)), max(1, max(far_y))]
    return out


def taken_tag(tag: str, taken: Iterable[str]) -> bool:
    return tag.lower() in {t.lower() for t in taken}


def composed(
    source: Calibration,
    site: Site,
    new_site: Site,
    edit: CalibrationEdit,
    taken_tags: Iterable[str] = (),
) -> tuple[Calibration, list[str]]:
    """`source` with every edit of `edit` applied, for `new_site` (the site
    as the save leaves it), and the warnings to show; `source` itself when
    nothing changes it. ComposeRefused when a robot could not take it."""
    taken = list(taken_tags)
    warnings: list[str] = []
    parts: list[str] = []
    result = source
    frame = edit.frame if edit.frame is not None and edit.frame.moves else None
    if edit.place is not None and frame is not None:
        raise ComposeRefused(
            "a placement and a move of the origin cannot be saved as one: "
            "save the placement first"
        )
    if edit.place is not None:
        move = Rigid2D(edit.place.dx_mm, edit.place.dy_mm, edit.place.theta_deg)
        try:
            result = place_calibration(
                source, new_site, move, reanchor=edit.place.reanchor
            )
        except PlacementRefused as exc:
            raise ComposeRefused(str(exc)) from exc
        parts.append(new_site.name)
        warnings += site_turn.outside_warnings(result, new_site)
        if not solved_in_own_frame(source):
            warnings.append(
                f"{source.id8} was collected at points of the room and has been "
                "re-anchored; check the note on where zero is"
            )
    elif frame is not None:
        try:
            result = site_frame.moved(
                source,
                site,
                frame.theta_deg,
                frame.pivot,
                frame.shift,
                new_site.anchor,
                new_site.frame_id,
            )
        except site_turn.TurnRefused as exc:
            raise ComposeRefused(
                str(exc),
                site_frame.largest_shift(
                    source, site, frame.theta_deg, frame.pivot, frame.shift
                ),
            ) from exc
        parts.append(site_turn.TAG_SUFFIX if frame.turns else site_turn.SHIFT_SUFFIX)
        warnings += site_turn.outside_warnings(result, new_site)
        warnings += site_turn.widened_note(frame.theta_deg)
    if edit.stations:
        now = {st.index: st.coverage_mm for st in result.stations}
        rects = {int(k): tuple(int(v) for v in r) for k, r in edit.stations.items()}
        if any(now.get(k) != r for k, r in rects.items()):
            try:
                result = reboxed(result, new_site, rects, tag="")
            except BoxesRefused as exc:
                raise ComposeRefused(str(exc)) from exc
            parts.append("split")
            warnings += coverage_warnings(result)
    if result is source:
        return source, warnings
    typed = (edit.tag or "").strip()
    if typed and taken_tag(typed, taken):
        raise ComposeRefused(f"tag {typed!r} is taken by another calibration")
    tag = typed or suffixed_tag(source.tag, "-".join(parts), taken)
    lineage = (
        {"placed_from": source.id, "edited_from": ""}
        if edit.place is not None
        else {"placed_from": source.placed_from, "edited_from": source.id}
    )
    result = dataclasses.replace(
        result,
        tag=tag,
        path=None,
        stored_id="",
        created_at=source.created_at,
        **lineage,
    )
    return result, warnings


def kept_rects(calibration: Calibration) -> list[Rect]:
    """Each station's coverage, to grow an extent round."""
    return [tuple(int(v) for v in st.coverage_mm) for st in calibration.stations]


def kept_points(calibration: Calibration) -> list[tuple[float, float]]:
    """Every spin circle's centre, to grow an extent round."""
    return [
        (c["x"], c["y"])
        for circles in spin_centres(calibration).values()
        for c in circles
    ]
