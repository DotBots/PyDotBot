# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Moving a spin calibration onto a site as one rigid body.

A free-mode calibration (`collect --spin`) defines its own frame, metric
through the spin radius. `place_calibration` turns and shifts every station
of it by one `Rigid2D`, so the stations keep their geometry relative to one
another and the scale is never touched. The site editor's placement and
`calibrate-lh2 reframe` of a spin calibration both go through it.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from dotbot.calibration.conics import Track, fit_tracks
from dotbot.calibration.lighthouse2 import Calibration, StationSolution
from dotbot.site import Site

# The solvers whose frame is the calibration's own, set by the spinning
# robots rather than by marks in the room: only those may be moved.
FREE_SOLVERS = frozenset({"conics-free", "conics-joint"})


class PlacementRefused(ValueError):
    """A calibration that must not be moved, or a move the robots cannot take."""


@dataclass(frozen=True)
class Rigid2D:
    """Turn by `theta_deg` about the frame origin, then shift by
    (`dx_mm`, `dy_mm`): `p' = R p + d`.

    Positive angles turn +x toward +y, which with y pointing down is
    clockwise as drawn.
    """

    dx_mm: float = 0.0
    dy_mm: float = 0.0
    theta_deg: float = 0.0

    @classmethod
    def about(
        cls,
        pivot: tuple[float, float],
        theta_deg: float,
        shift: tuple[float, float] = (0.0, 0.0),
    ) -> Rigid2D:
        """Turn about `pivot` by `theta_deg`, then translate by `shift`."""
        theta = math.radians(theta_deg)
        c, s = math.cos(theta), math.sin(theta)
        px, py = pivot
        return cls(
            px - c * px + s * py + shift[0],
            py - s * px - c * py + shift[1],
            theta_deg,
        )

    def matrix(self) -> np.ndarray:
        theta = math.radians(self.theta_deg)
        c, s = math.cos(theta), math.sin(theta)
        return np.array([[c, -s, self.dx_mm], [s, c, self.dy_mm], [0.0, 0.0, 1.0]])

    def apply(self, points: Iterable[Sequence[float]]) -> list[tuple[float, float]]:
        M = self.matrix()
        return [
            (
                float(M[0, 0] * x + M[0, 1] * y + M[0, 2]),
                float(M[1, 0] * x + M[1, 1] * y + M[1, 2]),
            )
            for x, y in points
        ]

    def box(self, rect: Sequence[float]) -> tuple[int, int, int, int]:
        """The axis-aligned box `[x0, y0, x1, y1]` round `rect` once moved,
        rounded outwards to whole millimetres."""
        x0, y0, x1, y1 = rect
        corners = self.apply([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        # A quarter turn lands on whole numbers but for rounding noise
        return (
            math.floor(min(xs) + 1e-6),
            math.floor(min(ys) + 1e-6),
            math.ceil(max(xs) - 1e-6),
            math.ceil(max(ys) - 1e-6),
        )


def is_free_mode(calibration: Calibration) -> bool:
    """Whether every station was solved in the calibration's own frame.

    Read from the stations' solvers rather than the anchor: a placed
    calibration takes its site's anchor, which a controller checks it
    against, and stays movable.
    """
    return bool(calibration.stations) and all(
        st.solved_from in FREE_SOLVERS for st in calibration.stations
    )


def station_rect(station: StationSolution) -> tuple[int, int, int, int] | None:
    """The station's own validity rectangle, for files that carry one."""
    rect = getattr(station, "valid_mm", None)
    return tuple(int(v) for v in rect) if rect else None


def spin_centres(calibration: Calibration) -> dict[int, list[dict]]:
    """Each station's circles in the calibration's frame: name, centre and
    radius in mm, one per `[[track]]` that station saw."""
    out: dict[int, list[dict]] = {}
    for station in calibration.stations:
        samples = [t for t in calibration.tracks if t.station == station.index]
        tracks = [
            Track(points=t.camera_points(), radius_mm=t.radius_mm, name=t.name)
            for t in samples
            if t.count1
        ]
        out[station.index] = [
            {
                "name": fit.name,
                "x": fit.centre_mm[0],
                "y": fit.centre_mm[1],
                "radius_mm": fit.radius_mm,
            }
            for fit in fit_tracks(tracks, station.matrix)
        ]
    return out


def _weak(link) -> bool:
    from dotbot.calibration.multi_station import (
        LINK_SHARED_ADVISED,
        LINK_SPREAD_ADVISED_MM,
    )

    return link.shared < LINK_SHARED_ADVISED or link.spread_mm < LINK_SPREAD_ADVISED_MM


def overlay(calibration: Calibration) -> dict:
    """What the site editor draws for `calibration`, in its own frame: the
    fence, each station's rectangle (its own, else the fence) and spin
    centres, and the links between stations."""
    centres = spin_centres(calibration)
    fence = [int(v) for v in calibration.valid_mm]
    stations = []
    for st in sorted(calibration.stations, key=lambda s: s.index):
        rect = station_rect(st)
        circles = centres.get(st.index, [])
        stations.append(
            {
                "index": st.index,
                "channel": st.index + 1,
                "rect": list(rect) if rect is not None else fence,
                "centres": [[c["x"], c["y"]] for c in circles],
                "circles": circles,
                "solved_from": st.solved_from,
            }
        )
    return {
        "id": calibration.id,
        "id8": calibration.id8,
        "free": is_free_mode(calibration),
        "fence": fence,
        "stations": stations,
        "links": [
            {"a": link.a, "b": link.b, "shared": link.shared, "weak": _weak(link)}
            for link in getattr(calibration, "links", [])
        ],
        "tag": calibration.tag,
        "created_at": calibration.created_at,
        "site": calibration.site.name,
        "anchor": calibration.site.anchor,
    }


def placed_tag(tag: str, site_name: str, taken: Iterable[str] = ()) -> str:
    """The moved calibration's tag: `tag` suffixed with the site, then a
    number if that tag is taken, so the two files answer to different tags."""
    if not tag:
        return ""
    base = tag if tag.endswith(f"-{site_name}") else f"{tag}-{site_name}"
    taken = {t.lower() for t in taken}
    candidate, n = base, 2
    while candidate.lower() in taken or candidate.lower() == tag.lower():
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def place_calibration(
    calibration: Calibration,
    site: Site,
    transform: Rigid2D,
    *,
    reanchor: bool = False,
    taken_tags: Iterable[str] = (),
) -> Calibration:
    """`calibration` moved by `transform` into `site`, as a new calibration.

    Every station's homography becomes `T . H`, normalised; a station's own
    rectangle becomes the box round its turned corners and the fence their
    union (without per-station rectangles, the site's extent); placements'
    points move with it; tracks and links are copied. The original is not
    modified.

    A corner-collected calibration is tied to the floor through the site's
    anchor and is refused unless `reanchor`. A move that puts a spin centre
    or a station's rectangle below zero is refused: robots carry positions as
    unsigned millimetres.
    """
    if not calibration.stations:
        raise PlacementRefused(f"calibration {calibration.id8} has no solved station")
    if not is_free_mode(calibration) and not reanchor:
        kinds = sorted({st.solved_from for st in calibration.stations})
        raise PlacementRefused(
            f"calibration {calibration.id8} was collected at points of the room "
            f"(solved from {', '.join(kinds)}), so its frame is the site's "
            "anchor: moving it would misplace every robot. Re-anchor it only if "
            "the anchor itself moved."
        )
    T = transform.matrix()
    stations = []
    for st in calibration.stations:
        H = T @ st.matrix
        H = H / H[2, 2]
        changes = {"homography": [[float(v) for v in row] for row in H]}
        rect = station_rect(st)
        if rect is not None:
            changes["valid_mm"] = transform.box(rect)
        stations.append(dataclasses.replace(st, **changes))

    below = [
        f"station {st.index} (channel {st.index + 1})'s rectangle "
        f"{list(station_rect(st))}"
        for st in stations
        if station_rect(st) is not None and min(station_rect(st)[:2]) < 0
    ]
    for index, circles in spin_centres(
        dataclasses.replace(calibration, stations=stations)
    ).items():
        below += [
            f"circle {c['name']} (station {index}, channel {index + 1}) at "
            f"({c['x']:.0f}, {c['y']:.0f})"
            for c in circles
            if c["x"] < 0 or c["y"] < 0
        ]
    if below:
        more = f" and {len(below) - 3} more" if len(below) > 3 else ""
        raise PlacementRefused(
            "the move puts "
            + ", ".join(below[:3])
            + more
            + " below zero, where a robot cannot report a position"
        )

    rects = [station_rect(st) for st in stations]
    if rects and all(r is not None for r in rects):
        valid_mm = (
            min(r[0] for r in rects),
            min(r[1] for r in rects),
            max(r[2] for r in rects),
            max(r[3] for r in rects),
        )
    elif site.valid_mm is not None:
        valid_mm = site.valid_mm
    else:
        valid_mm = transform.box(calibration.valid_mm)
    placements = [
        dataclasses.replace(
            placement,
            points_mm=transform.apply(placement.points_mm),
            samples=[dataclasses.replace(s) for s in placement.samples],
        )
        for placement in calibration.placements
    ]
    extra = {}
    if hasattr(calibration, "links"):
        extra["links"] = list(calibration.links)
    return Calibration(
        **extra,
        site=Site(name=site.name, anchor=site.anchor),
        valid_mm=tuple(int(v) for v in valid_mm),
        placements=placements,
        stations=stations,
        tracks=list(calibration.tracks),
        created_at=calibration.created_at,
        tag=placed_tag(calibration.tag, site.name, taken_tags),
        robot=calibration.robot,
    )
