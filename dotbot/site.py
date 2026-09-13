# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One deployment's floor: its anchor, its extent and its areas.

A site names a physical place and, with it, the coordinate frame every
position in that place is expressed in: zero at the top-left corner of the
extent, x growing right, y growing down, millimetres. The frame has no name
of its own - the site's name identifies it, and `anchor` is the prose that
re-establishes zero in the physical world.

Sites come from the `[sites.<name>]` tables of a dotbot config file. The
package default is deliberately empty: a real site is measured, never
shipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from dotbot.area import Area, AreaRegistry

SITE_DEFAULT = "default"


@dataclass
class Site:
    """A site as the config declares it.

    `extent_mm` is (width, height) in millimetres with zero at its top-left
    corner, which is the site's anchor. A calibration file records only
    `name` and `anchor`, so a site read back from one carries no extent and
    no areas.
    """

    name: str = SITE_DEFAULT
    anchor: str = ""
    extent_mm: Optional[tuple[int, int]] = None
    areas: dict[str, Area] = field(default_factory=dict)

    @property
    def extent(self) -> Optional[Area]:
        """The whole site as one rectangle, when its extent is known."""
        if self.extent_mm is None:
            return None
        return Area(0, 0, int(self.extent_mm[0]), int(self.extent_mm[1]), self.name)

    @property
    def valid_mm(self) -> Optional[tuple[int, int, int, int]]:
        """The plausibility fence a bot applies, when the extent is known.

        `[x_min, y_min, x_max, y_max]`: a position outside the site cannot be
        a position in it.
        """
        if self.extent_mm is None:
            return None
        return (0, 0, int(self.extent_mm[0]), int(self.extent_mm[1]))

    def registry(self) -> AreaRegistry:
        """The resolver `--points` runs against."""
        return AreaRegistry(named=dict(self.areas), site=self.name)


def site_from_config(config: Any, name: str) -> Site:
    """The `[sites.<name>]` table of a loaded config, else an empty site.

    Takes the config duck-typed so the resolver stays independent of the
    pydantic model.
    """
    tables = getattr(config, "sites", None) or {}
    table = tables.get(name)
    if table is None:
        return Site(name=name)
    extent = getattr(table, "extent_mm", None)
    return Site(
        name=name,
        anchor=getattr(table, "anchor", None) or "",
        extent_mm=(int(extent[0]), int(extent[1])) if extent else None,
        areas={
            area_name: Area(
                x=area.x, y=area.y, w=area.w, h=area.h, name=area_name
            )
            for area_name, area in (getattr(table, "areas", None) or {}).items()
        },
    )
