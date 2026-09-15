# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Resolve what the operator typed into frame coordinates.

One function turns a `--points` specification into the millimetre
coordinates stored as a placement's `points_mm`, each paired with the
placement instruction the operator has to follow to make that coordinate
true. Nothing downstream ever sees the specification again: the solver reads
(point index, frame mm) pairs, and the free-text `at` note keeps the
provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from dotbot.area import Area, AreaRegistry
from dotbot.robots import ROBOT_DEFAULT, robot_geometry
from dotbot.site import Site

# The corners of a rectangle, in the order a placement stores them.
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(frozen=True)
class PointPlacement:
    """One resolved point, and how the robot has to sit to realise it.

    `corner` is None for a point typed as coordinates: nothing is known
    about the robot's pose there, so there is nothing to instruct.
    """

    mm: tuple[float, float]
    area: str = ""
    corner: str | None = None
    side_edge: str = ""  # left | right
    front_edge: str = ""  # top | bottom, the line the nose-side edge rests on
    nose: str = ""  # top | bottom, where the nose points

    @property
    def where(self) -> str:
        """Which corner of which area, as a phrase."""
        if self.corner is None:
            return ""
        if self.area:
            return f"{self.corner} corner of {self.area}"
        return f"{self.corner} corner"

    @property
    def how(self) -> str:
        """How the robot sits there, as a phrase."""
        if self.corner is None:
            return ""
        return (
            "robot inside the rectangle, "
            f"{self.side_edge} edge on the {self.side_edge} line, "
            f"front edge on the {self.front_edge} line, "
            f"nose toward the {self.nose}"
        )


def corner_mark(area: Area, corner: str, robot: str = ROBOT_DEFAULT) -> PointPlacement:
    """Where a robot's photodiode lands when placed at `corner`.

    The robot sits inside the rectangle with its PCB edges on the
    rectangle's edge lines and its nose toward the nearest top or bottom
    edge, so the mark is the corner inset by the photodiode's distance to
    those two edges.
    """
    if corner not in CORNERS:
        raise ValueError(
            f"unknown corner {corner!r}; expected one of {', '.join(CORNERS)}"
        )
    dx, dy = robot_geometry(robot).photodiode_inset(corner)
    vertical, _, horizontal = corner.partition("-")
    x = area.x if horizontal == "left" else area.x_max
    y = area.y if vertical == "top" else area.y_max
    return PointPlacement(
        mm=(x + dx, y + dy),
        area=area.name,
        corner=corner,
        side_edge=horizontal,
        front_edge=vertical,
        nose=vertical,
    )


def resolve_points(
    spec: str,
    registry: AreaRegistry | None = None,
    robot: str = ROBOT_DEFAULT,
) -> list[PointPlacement]:
    """The frame coordinates one `--points` specification stands for.

    Four forms, where `<area>` is a name, a `+`-joined composite, or a
    literal `x,y,w,h` rectangle in millimetres:

    - `x,y` - one literal point in frame millimetres, the photodiode's own
      position, taken exactly as typed.
    - `<area>` - one point at that rectangle's centre.
    - `<area>:<corner>` - one corner mark, `<corner>` from CORNERS.
    - `<area>:corners` - all four corner marks, in CORNERS order.
    """
    registry = registry or AreaRegistry()
    spec = spec.strip()
    if not spec:
        raise ValueError("empty points specification")

    if ":" in spec:
        name, _, corner = spec.partition(":")
        area = registry.resolve(name)
        if corner == "corners":
            return [corner_mark(area, c, robot) for c in CORNERS]
        return [corner_mark(area, corner, robot)]

    if "," in spec:
        parts = [p.strip() for p in spec.split(",")]
        if len(parts) == 4:
            return [_centre(registry.resolve(spec))]
        if len(parts) != 2:
            raise ValueError(
                f"points {spec!r}: two numbers are a point x,y, four are a "
                f"rectangle x,y,w,h, both in frame mm"
            )
        try:
            return [PointPlacement(mm=(float(parts[0]), float(parts[1])))]
        except ValueError as exc:
            raise ValueError(f"points {spec!r}: x,y must be numbers") from exc

    return [_centre(registry.resolve(spec))]


def resolve_placement_points(
    specs: list[str] | tuple[str, ...],
    registry: AreaRegistry | None = None,
    robot: str = ROBOT_DEFAULT,
) -> list[PointPlacement]:
    """Every point of one placement, concatenated in the order given."""
    registry = registry or AreaRegistry()
    points: list[PointPlacement] = []
    for spec in specs:
        points.extend(resolve_points(spec, registry, robot))
    return points


def _centre(area: Area) -> PointPlacement:
    """A rectangle's centre, which constrains no pose."""
    return PointPlacement(mm=area.centre, area=area.name)


def point_prompt(index: int, total: int, point: PointPlacement) -> str:
    """What the operator reads before one capture.

    The corner and the pose come first and the coordinate last: the operator
    places the robot by the rectangle's edges, and the millimetres are the
    consequence, not the instruction.
    """
    head = f"point {index} of {total}"
    x, y = point.mm
    if point.corner is None:
        return f"{head}: photodiode on ({x:g}, {y:g}) mm. Press Enter when it is still."
    return (
        f"{head}, {point.where}: {point.how}. "
        f"Photodiode lands at ({x:g}, {y:g}) mm. Press Enter when it is still."
    )


def collect_header(
    site: Site, source: str, total: int, reads: int, device: str = ""
) -> str:
    """The paragraph printed once, before the first capture prompt."""
    target = f" from {device.upper()}" if device else ""
    zero = (
        site.anchor
        or "the site's anchor, which this config does not describe (add "
        f"`anchor` to [sites.{site.name}])"
    )
    return (
        f"\nCollecting LH2 calibration{target} in site {site.name} "
        f"(from {source}). Coordinates are millimetres in the site's frame: "
        f"x grows right, y grows down, and zero is {zero}. A corner point is "
        "where the photodiode lands with the robot inside the rectangle, its "
        "PCB edges resting on the rectangle's edge lines and its nose toward "
        "the nearest top or bottom edge.\n"
        "Stop the robot's app first (capture only runs in READY).\n"
        f"{total} point(s), {reads} reads each, in the order listed.\n"
    )
