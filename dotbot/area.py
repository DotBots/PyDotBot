# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Named areas: the rectangles of a site's frame.

An area is session configuration, a view into the frame that carries no
homography: changing it never touches a calibration file. Named areas come
from the `[sites.<site>.areas.<name>]` tables of a dotbot config file, so a
fresh install with no config has none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# What a renderer draws when neither a shown area nor a site extent says
# otherwise: a 2 x 2 m square at the frame origin.
AREA_FALLBACK_MM = (0, 0, 2000, 2000)


@dataclass(frozen=True)
class Area:
    """One rectangle in frame millimetres.

    Edges are named as the console draws the frame: x grows right, y grows
    down, so `top` is the low-y edge.
    """

    x: int
    y: int
    w: int
    h: int
    name: str = ""

    @property
    def x_max(self) -> int:
        return self.x + self.w

    @property
    def y_max(self) -> int:
        return self.y + self.h

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def as_dict(self) -> dict[str, int]:
        """The four numbers plus the name, the shape every consumer receives."""
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "name": self.name}


def fallback_area(name: str = "") -> Area:
    """The rectangle a renderer falls back to, named after its caller."""
    return Area(*AREA_FALLBACK_MM, name)


@dataclass
class AreaRegistry:
    """The named areas of one site, and the resolver over them.

    `site` appears only in error messages, so an unresolvable name says which
    site was searched.
    """

    named: dict[str, Area] = field(default_factory=dict)
    site: str = ""

    def resolve(self, spec: str) -> Area:
        """One area from a name, a `+`-joined composite, or `x,y,w,h` in mm.

        A composite is the bounding box of its parts.
        """
        spec = spec.strip()
        if not spec:
            raise ValueError("empty area specification")
        if spec in self.named:
            return self.named[spec]
        if "," in spec:
            parts = [p.strip() for p in spec.split(",")]
            if len(parts) != 4:
                raise ValueError(
                    f"area {spec!r}: a literal rectangle is x,y,w,h in mm"
                )
            try:
                x, y, w, h = (int(p) for p in parts)
            except ValueError as exc:
                raise ValueError(
                    f"area {spec!r}: x,y,w,h must be whole millimetres"
                ) from exc
            return Area(x, y, w, h, spec)
        if "+" in spec:
            return self._composite(spec)
        raise ValueError(f"unknown area {spec!r}; {self._known()}")

    def resolve_all(self, specs: list[str] | tuple[str, ...]) -> list[Area]:
        """The areas shown: one rectangle per specification, in order."""
        return [self.resolve(spec) for spec in specs]

    def _known(self) -> str:
        where = f"site {self.site!r}" if self.site else "the active site"
        if not self.named:
            table = f"[sites.{self.site or '<site>'}.areas.<name>]"
            return (
                f"{where} defines no areas. Add a {table} table to your "
                "dotbot config, or give the rectangle as x,y,w,h in mm"
            )
        return f"{where} defines: {', '.join(sorted(self.named))}"

    def _composite(self, spec: str) -> Area:
        parts = [self.resolve(p) for p in spec.split("+")]
        return _bounding_box(parts, spec)


def union(areas: list[Area]) -> Area:
    """The bounding box of the areas shown, for a renderer that needs one box."""
    if not areas:
        return fallback_area()
    return _bounding_box(areas, "")


def drawn_area(areas: list[Area], extent: Area | None, name: str = "") -> Area:
    """The one rectangle to draw: the areas shown, else the whole site.

    An empty list of areas means the whole site, so a renderer that needs a
    single box resolves it here instead of reading `areas[0]`.
    """
    if areas:
        return union(areas)
    return extent or fallback_area(name)


def _bounding_box(areas: list[Area], name: str) -> Area:
    x = min(a.x for a in areas)
    y = min(a.y for a in areas)
    x_max = max(a.x_max for a in areas)
    y_max = max(a.y_max for a in areas)
    return Area(x, y, x_max - x, y_max - y, name)
