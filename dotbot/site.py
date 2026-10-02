# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One place's floor: its anchor, its extent and its areas.

A site names a physical place and, with it, the coordinate frame every
position in that place is expressed in: zero at the top-left corner of the
extent, x growing right, y growing down, millimetres. The frame has no name
of its own - the site's name identifies it, and `anchor` is the prose that
re-establishes zero in the physical world.

Sites come from site packs (`dotbot.site_packs`). The package default is deliberately empty:
a real site is measured, never shipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotbot.area import Area, AreaRegistry, area_role

SITE_DEFAULT = "default"
# A site name is a bare TOML key, and names a site pack's folder
SITE_NAME = re.compile(r"[A-Za-z0-9_-]+")
# The side of the square, at the frame origin, a site that declares nothing
# works in.
FIELD_FALLBACK_MM = 2000
# A site pack's folder of calibration files
PACK_CALIBRATIONS = "calibrations"
# The starter site's geometry, all derived from the field: a margin of floor
# round it, and a staging strip along its bottom edge.
SITE_MARGIN_MM = 1500
STAGING_DEPTH_MM = 600


Point = tuple[int, int]


@dataclass(frozen=True)
class Wall:
    """A polyline robots cannot cross, in frame mm."""

    points: tuple[Point, ...]
    name: str = ""


@dataclass(frozen=True)
class Obstacle:
    """A polygon robots cannot enter, in frame mm; the last point joins the first."""

    points: tuple[Point, ...]
    name: str = ""


@dataclass(frozen=True)
class SiteObject:
    """A thing on the floor (a charger, a dock, a landmark, a camera) at a
    pose in frame mm; `heading_deg` follows the robots' convention."""

    name: str
    kind: str
    x: int
    y: int
    heading_deg: float = 0.0


@dataclass
class Site:
    """A site as the config declares it.

    `extent_mm` is (width, height) in millimetres with zero at its top-left
    corner, which is the site's anchor. A calibration file records only
    `name` and `anchor`, so a site read back from one carries no extent and
    no areas. `pack` is the site pack folder the site was read from, if any.
    """

    name: str = SITE_DEFAULT
    anchor: str = ""
    extent_mm: tuple[int, int] | None = None
    areas: dict[str, Area] = field(default_factory=dict)
    pack: Path | None = None
    walls: list[Wall] = field(default_factory=list)
    obstacles: list[Obstacle] = field(default_factory=list)
    objects: dict[str, SiteObject] = field(default_factory=dict)

    @property
    def extent(self) -> Area | None:
        """The whole site as one rectangle, when its extent is known."""
        if self.extent_mm is None:
            return None
        return Area(0, 0, int(self.extent_mm[0]), int(self.extent_mm[1]), self.name)

    @property
    def valid_mm(self) -> tuple[int, int, int, int] | None:
        """The plausibility fence a bot applies, when the extent is known.

        `[x_min, y_min, x_max, y_max]`: a position outside the site cannot be
        a position in it.
        """
        if self.extent_mm is None:
            return None
        return (0, 0, int(self.extent_mm[0]), int(self.extent_mm[1]))

    @property
    def field(self) -> Area | None:
        """Where experiments happen: what a fleet, a calibration and a camera default to.

        The area whose role is `field`, else the first area that is neither
        `staging` nor `corner`, else the first area, else the whole extent,
        named as its `x,y,w,h` literal so the registry resolves it. None for
        a site that declares nothing.
        """
        areas = list(self.areas.values())
        roles = [area_role(area.name, area.role) for area in areas]
        for area, role in zip(areas, roles):
            if role == "field":
                return area
        for area, role in zip(areas, roles):
            if role not in ("staging", "corner"):
                return area
        if areas:
            return areas[0]
        extent = self.extent
        if extent is None:
            return None
        return Area(0, 0, extent.w, extent.h, f"0,0,{extent.w},{extent.h}")

    @property
    def pack_calibrations(self) -> Path | None:
        """The pack's calibration folder, looked in before the home one."""
        return self.pack / PACK_CALIBRATIONS if self.pack is not None else None

    @property
    def staging(self) -> Area | None:
        """Where robots park and charge: the first area whose role is `staging`."""
        for area in self.areas.values():
            if area_role(area.name, area.role) == "staging":
                return area
        return None

    def objects_of(self, kind: str) -> list[SiteObject]:
        """The objects of `kind`, in the order the file declares them."""
        return [o for o in self.objects.values() if o.kind == kind]

    def registry(self) -> AreaRegistry:
        """The resolver `--points` runs against."""
        return AreaRegistry(named=dict(self.areas), site=self.name)


def check_site_name(name: str) -> str:
    """`name`, or ValueError when it is not letters, digits, `-` and `_`."""
    if not SITE_NAME.fullmatch(name):
        raise ValueError(f"site name {name!r}: use letters, digits, - and _")
    return name


def starter_layout(
    field_mm: tuple[int, int], size_mm: tuple[int, int] | None = None
) -> tuple[tuple[int, int], Area, Area]:
    """The starter site around a field of `field_mm`: (extent, field, staging).

    The field sits `SITE_MARGIN_MM` in from each wall, or centred in a
    `size_mm` site; staging is a `STAGING_DEPTH_MM` strip along the field's
    bottom (+y) edge, as wide as the field. ValueError when `size_mm` cannot
    hold the field with the strip below it.
    """
    width, height = field_mm
    extent = size_mm or (width + 2 * SITE_MARGIN_MM, height + 2 * SITE_MARGIN_MM)
    x, y = (extent[0] - width) // 2, (extent[1] - height) // 2
    if x < 0 or y < STAGING_DEPTH_MM:
        raise ValueError(
            f"a {width} x {height} mm field centred with a {STAGING_DEPTH_MM} mm "
            f"staging strip below it does not fit a {extent[0]} x {extent[1]} mm site"
        )
    field_area = Area(x, y, width, height, "field", role="field")
    staging = Area(x, y + height, width, STAGING_DEPTH_MM, "staging", role="staging")
    return (int(extent[0]), int(extent[1])), field_area, staging


def field_or_fallback(site: Site | None) -> Area:
    """The site's field, else a `FIELD_FALLBACK_MM` square at the frame origin."""
    area = site.field if site is not None else None
    if area is not None:
        return area
    return Area(0, 0, FIELD_FALLBACK_MM, FIELD_FALLBACK_MM)


def site_from_table(name: str, table: Any, pack: Path | None = None) -> Site:
    """A site from a pack's `site.toml` table; None is an empty site."""
    if table is None:
        return Site(name=name, pack=pack)
    extent = getattr(table, "extent_mm", None)
    return Site(
        name=name,
        pack=pack,
        anchor=getattr(table, "anchor", None) or "",
        extent_mm=(int(extent[0]), int(extent[1])) if extent else None,
        areas={
            area_name: Area(
                x=area.x,
                y=area.y,
                w=area.w,
                h=area.h,
                name=area_name,
                role=area_role(area_name, getattr(area, "role", None)),
            )
            for area_name, area in (getattr(table, "areas", None) or {}).items()
        },
        walls=[
            Wall(tuple(tuple(p) for p in wall.points), wall.name or "")
            for wall in getattr(table, "walls", None) or []
        ],
        obstacles=[
            Obstacle(tuple(tuple(p) for p in obstacle.points), obstacle.name or "")
            for obstacle in getattr(table, "obstacles", None) or []
        ],
        objects={
            name: SiteObject(name, o.kind, o.x, o.y, o.heading_deg)
            for name, o in (getattr(table, "objects", None) or {}).items()
        },
    )
