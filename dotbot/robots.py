# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Physical geometry of the robot models the host talks to, one record per
board revision.

Every point in a record is a coordinate in that revision's KiCad board frame:
millimetres, x to the robot's right, y toward the rear, nose at low y, origin
off the robot. The C copy of the drivetrain constants and the lever arm lives
in DotBot-libs `drv/geometry.h` and is pinned to this one by
`dotbot/tests/test_control_loop_geometry.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from enum import IntEnum
from typing import NamedTuple

ROBOT_DEFAULT = "dotbot-v3"


class Point(NamedTuple):
    x: float
    y: float


class HeadingSource(IntEnum):
    """How the heading a pose is built from was made."""

    NONE = 0  # no heading; the pose's heading is a placeholder
    TRAVEL = 1  # bearing of travel between two fixes
    EKF = 2  # body heading from the on-bot estimator


@dataclass(frozen=True)
class BodyPose:
    """A robot's body in the arena frame, in mm and degrees.

    `heading_deg` follows the robot `direction` convention: 0 = +y, and the
    body-forward unit vector is (-sin, +cos).
    """

    heading_deg: float
    heading_source: HeadingSource
    photodiode: Point  # where the pose places the LH2 photodiode
    axle: Point
    centre: Point
    nose: Point
    led: Point
    outline: tuple[Point, ...]
    wheels: tuple[tuple[Point, ...], ...]
    # Radii about the photodiode, which hold under any heading: `reach_mm`
    # encloses the whole body, tyres included; `core_mm` is covered by the
    # board. `envelope_mm` is the record's plan-view square.
    reach_mm: float
    core_mm: float
    envelope_mm: float


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distance from `p` to the segment `a`-`b`."""
    dx, dy = b.x - a.x, b.y - a.y
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2
    t = max(0.0, min(1.0, t))
    return math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y)


def _rect(centre: Point, width_mm: float, length_mm: float) -> tuple[Point, ...]:
    """An axis-aligned rectangle about `centre`, `width_mm` in x by `length_mm`
    in y, wound from its low-x low-y corner."""
    x0, x1 = centre.x - width_mm / 2, centre.x + width_mm / 2
    y0, y1 = centre.y - length_mm / 2, centre.y + length_mm / 2
    return (Point(x0, y0), Point(x1, y0), Point(x1, y1), Point(x0, y1))


@dataclass(frozen=True)
class RobotGeometry:
    """One board revision's outline, points and drivetrain, in the board frame.

    The edge distances (`diode_to_front_mm` and the rest) are measured with
    the robot's nose toward the frame's top edge, which is the low-y one since
    y grows down. That orientation is the board frame's own, and is not the
    robot `direction` convention, where 0 = +y.
    """

    model: str
    # Outer board path; each nose fillet (r 1.0) is its chord.
    outline_path: tuple[Point, ...]
    photodiode: Point
    led: Point
    caster: Point
    axle_midpoint: Point
    track_mm: float
    wheel_diameter_mm: float
    tyre_width_mm: float
    # The motor connector pin block, whose red housing is the axle the camera
    # detector fits: J5 to J6 centre to centre, then one housing's footprint.
    connector_spacing_mm: float
    connector_width_mm: float
    connector_length_mm: float
    encoder_cpr: int
    gear_ratio: float
    # The plan-view square for anything that needs a size rather than a shape.
    envelope_mm: float

    def __post_init__(self):
        if self.photodiode.x != self.axle_midpoint.x:
            raise ValueError(
                f"{self.model}: photodiode off the centreline; "
                "a non-zero lever angle is not handled"
            )

    @cached_property
    def outline_bbox(self) -> tuple[float, float, float, float]:
        """(x_min, y_min, x_max, y_max) of the outline."""
        xs = [p.x for p in self.outline_path]
        ys = [p.y for p in self.outline_path]
        return (min(xs), min(ys), max(xs), max(ys))

    @cached_property
    def outline_centre(self) -> Point:
        x_min, y_min, x_max, y_max = self.outline_bbox
        return Point((x_min + x_max) / 2, (y_min + y_max) / 2)

    @property
    def board_width_mm(self) -> float:
        x_min, _, x_max, _ = self.outline_bbox
        return x_max - x_min

    @property
    def board_length_mm(self) -> float:
        _, y_min, _, y_max = self.outline_bbox
        return y_max - y_min

    def _axle_pair(
        self, spacing_mm: float, width_mm: float, length_mm: float
    ) -> tuple[tuple[Point, ...], ...]:
        """One rectangle either side of the axle midpoint, the -x one first.

        `width_mm` is across the robot and `length_mm` along it, and each
        rectangle's centre sits half of `spacing_mm` off the centreline on the
        axle line.
        """
        return tuple(
            _rect(Point(cx, self.axle_midpoint.y), width_mm, length_mm)
            for cx in (
                self.axle_midpoint.x - spacing_mm / 2,
                self.axle_midpoint.x + spacing_mm / 2,
            )
        )

    @cached_property
    def wheel_paths(self) -> tuple[tuple[Point, ...], ...]:
        """Each driven wheel in plan view, as a rectangle in the board frame.

        A wheel is `tyre_width_mm` across the robot and `wheel_diameter_mm`
        along it, at half the track either side of the axle midpoint. The left
        wheel comes first, left being -x.
        """
        return self._axle_pair(
            self.track_mm, self.tyre_width_mm, self.wheel_diameter_mm
        )

    @property
    def connector_paths(self) -> tuple[tuple[Point, ...], ...]:
        """Each motor connector in plan view, as a rectangle in the board frame.

        The pair the camera detector reads as the axle, in the same order and
        the same frame as `wheel_paths`.
        """
        return self._axle_pair(
            self.connector_spacing_mm,
            self.connector_width_mm,
            self.connector_length_mm,
        )

    @property
    def lever_arm_mm(self) -> float:
        """Axle midpoint to photodiode, forward: `DB_LH2_LEVER_ARM`."""
        return self.axle_midpoint.y - self.photodiode.y

    @property
    def lever_angle_deg(self) -> float:
        """`DB_LH2_LEVER_ANGLE`; zero, as `__post_init__` enforces."""
        return 0.0

    @property
    def diode_to_front_mm(self) -> float:
        return self.photodiode.y - self.outline_bbox[1]

    @property
    def diode_to_rear_mm(self) -> float:
        return self.outline_bbox[3] - self.photodiode.y

    @property
    def diode_to_side_mm(self) -> float:
        x_min, _, x_max, _ = self.outline_bbox
        return min(self.photodiode.x - x_min, x_max - self.photodiode.x)

    @property
    def led_to_front_mm(self) -> float:
        return self.led.y - self.outline_bbox[1]

    @property
    def led_ahead_of_diode_mm(self) -> float:
        """How far the RGB LED sits toward the nose from the photodiode."""
        return self.photodiode.y - self.led.y

    @property
    def diode_ahead_of_centre_mm(self) -> float:
        return self.outline_centre.y - self.photodiode.y

    @cached_property
    def reach_mm(self) -> float:
        """Furthest outline or wheel point from the photodiode."""
        points = [*self.outline_path, *(p for w in self.wheel_paths for p in w)]
        return max(
            math.hypot(p.x - self.photodiode.x, p.y - self.photodiode.y)
            for p in points
        )

    @cached_property
    def core_mm(self) -> float:
        """Nearest board edge to the photodiode."""
        path = self.outline_path
        return min(
            _segment_distance(self.photodiode, a, b)
            for a, b in zip(path, path[1:] + path[:1])
        )

    @property
    def mm_per_count(self) -> float:
        """Wheel travel per encoder count: `DB_MM_PER_COUNT`."""
        return math.pi * self.wheel_diameter_mm / (self.encoder_cpr * self.gear_ratio)

    def body_pose(
        self, sensor: Point, heading_deg: float, source: HeadingSource
    ) -> BodyPose:
        """The body around a photodiode fix at `sensor`, facing `heading_deg`."""
        theta = math.radians(heading_deg)
        forward = (-math.sin(theta), math.cos(theta))
        right = (-math.cos(theta), -math.sin(theta))

        def place(point: Point) -> Point:
            ahead = self.photodiode.y - point.y
            aside = point.x - self.photodiode.x
            return Point(
                sensor[0] + ahead * forward[0] + aside * right[0],
                sensor[1] + ahead * forward[1] + aside * right[1],
            )

        return BodyPose(
            heading_deg=heading_deg,
            heading_source=source,
            photodiode=Point(sensor[0], sensor[1]),
            axle=place(self.axle_midpoint),
            centre=place(self.outline_centre),
            nose=place(Point(self.photodiode.x, self.outline_bbox[1])),
            led=place(self.led),
            outline=tuple(place(p) for p in self.outline_path),
            wheels=tuple(
                tuple(place(p) for p in wheel) for wheel in self.wheel_paths
            ),
            reach_mm=self.reach_mm,
            core_mm=self.core_mm,
            envelope_mm=self.envelope_mm,
        )

    def clearance_mm(self, edge: str) -> float:
        """Distance from the photodiode to the body edge facing `edge`.

        `edge` is one of top / bottom / left / right in frame orientation,
        with the nose toward the top edge and the rear toward the bottom one.
        """
        if edge == "top":
            return self.diode_to_front_mm
        if edge == "bottom":
            return self.diode_to_rear_mm
        if edge in ("left", "right"):
            return self.diode_to_side_mm
        raise ValueError(f"unknown edge {edge!r}; expected top/bottom/left/right")

    def photodiode_inset(self, corner: str) -> tuple[float, float]:
        """The (dx, dy) from a rectangle corner to the photodiode.

        The robot stands inside the rectangle with its board edges on the
        rectangle's edge lines and its nose toward the nearest top or bottom
        edge, so the front edge rests on the horizontal line at every corner
        and one side edge rests on the vertical one.
        """
        vertical, _, horizontal = corner.partition("-")
        dx = self.clearance_mm(horizontal)
        dy = self.diode_to_front_mm
        return (dx if horizontal == "left" else -dx, dy if vertical == "top" else -dy)


# DotBot v3, main board bd1.3a: board points from its KiCad file, wheel and
# track caliper-measured, tyre width measured on a photograph.
ROBOTS: dict[str, RobotGeometry] = {
    "dotbot-v3": RobotGeometry(
        model="dotbot-v3",
        outline_path=(
            Point(118.0, 60.5),
            Point(122.0, 60.5),
            Point(122.0, 98.5),
            Point(103.5, 98.5),
            Point(103.5, 147.5),
            Point(46.5, 147.5),
            Point(46.5, 98.5),
            Point(28.0, 98.5),
            Point(28.0, 60.5),
            Point(32.0, 60.5),
            Point(33.0, 59.5),
            Point(33.0, 52.5),
            Point(117.0, 52.5),
            Point(117.0, 59.5),
        ),
        photodiode=Point(75.0, 71.0),  # D17
        led=Point(75.0, 65.5),  # D18
        caster=Point(75.0, 59.0),  # J19/J20 midpoint
        axle_midpoint=Point(75.0, 124.5),  # M1/M2 midpoint
        track_mm=78.0,
        wheel_diameter_mm=44.0,
        tyre_width_mm=17.5,
        connector_spacing_mm=27.0,  # J5 to J6
        connector_width_mm=12.0,
        connector_length_mm=10.0,
        encoder_cpr=28,
        gear_ratio=50.0,
        envelope_mm=95.0,
    ),
}


# The geometry record for each device type swarmit's STATUS reports; a type
# missing here has none.
SWARMIT_DEVICE_MODELS: dict[str, str] = {"DotBotV3": "dotbot-v3"}


def robot_geometry(model: str = ROBOT_DEFAULT) -> RobotGeometry:
    """The geometry record for `model`."""
    try:
        return ROBOTS[model]
    except KeyError as exc:
        known = ", ".join(sorted(ROBOTS))
        raise ValueError(
            f"unknown robot model {model!r}; known models: {known}"
        ) from exc
