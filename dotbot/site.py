# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One place's floor: its anchor, its extent and its areas.

A site names a physical place and, with it, the coordinate frame every
position in that place is expressed in: zero at the top-left corner of the
extent, x growing right, y growing down, millimetres. The frame has no name
of its own - the site's name identifies it, and `anchor` is the prose that
re-establishes zero in the physical world.

Sites come from the `[sites.<name>]` tables of a dotbot config file, or from
site packs (`dotbot.site_packs`). The package default is deliberately empty:
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

    def registry(self) -> AreaRegistry:
        """The resolver `--points` runs against."""
        return AreaRegistry(named=dict(self.areas), site=self.name)


def check_site_name(name: str) -> str:
    """`name`, or ValueError when it is not letters, digits, `-` and `_`."""
    if not SITE_NAME.fullmatch(name):
        raise ValueError(f"site name {name!r}: use letters, digits, - and _")
    return name


def field_or_fallback(site: Site | None) -> Area:
    """The site's field, else a `FIELD_FALLBACK_MM` square at the frame origin."""
    area = site.field if site is not None else None
    if area is not None:
        return area
    return Area(0, 0, FIELD_FALLBACK_MM, FIELD_FALLBACK_MM)


def site_from_config(config: Any, name: str) -> Site:
    """The `[sites.<name>]` table of a loaded config, else an empty site.

    Takes the config duck-typed so the resolver stays independent of the
    pydantic model.
    """
    tables = getattr(config, "sites", None) or {}
    return site_from_table(name, tables.get(name))


def site_from_table(name: str, table: Any, pack: Path | None = None) -> Site:
    """A site from one `[sites.<name>]` table or pack `site.toml`; None is an
    empty site."""
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
    )
