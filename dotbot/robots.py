# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Physical geometry of the robot models the host talks to.

Anything that has to reason about where a robot's sensors sit relative to
its body reads this: the calibration point resolver offsets a corner mark
by the photodiode's distance to the body edges resting on that corner.
"""

from __future__ import annotations

from dataclasses import dataclass

ROBOT_DEFAULT = "dotbot-v3"


@dataclass(frozen=True)
class RobotGeometry:
    """One robot model's board footprint and sensor offsets, in millimetres.

    Distances are measured from the photodiode to a board edge with the
    robot's nose toward the frame's top edge, which is the low-y one since
    y grows down. That orientation is this class's own reference, and is
    not the robot `direction` convention, where 0 = +y.
    """

    model: str
    board_width_mm: float  # side to side
    board_length_mm: float  # nose to tail
    diode_to_front_mm: float
    diode_to_rear_mm: float
    diode_to_side_mm: float
    led_to_front_mm: float  # RGB LED, on the centreline

    @property
    def led_ahead_of_diode_mm(self) -> float:
        """How far the RGB LED sits toward the nose from the photodiode.

        A camera tracking the LED reports this offset, rotated by the
        robot's orientation, away from the photodiode's position.
        """
        return self.diode_to_front_mm - self.led_to_front_mm

    def clearance_mm(self, edge: str) -> float:
        """Distance from the photodiode to the body edge facing `edge`.

        `edge` is one of top / bottom / left / right in frame orientation,
        with the nose toward the top edge and the rear toward the bottom
        one, which is this class's own reference.
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


# Measured off the DotBot v3 main board bd1.3a in KiCad: the Edge.Cuts
# outline is 94.00 x 95.00 mm, the photodiode D17 (Osram BPW34S, footprint
# centre = active-area centre) sits on the centreline 18.5 mm from one long
# edge, and the RGB LED D18 sits 13.0 mm from the same edge. That edge is
# taken as the robot's front, which is the nest-sheet generator's convention.
ROBOTS: dict[str, RobotGeometry] = {
    "dotbot-v3": RobotGeometry(
        model="dotbot-v3",
        board_width_mm=94.0,
        board_length_mm=95.0,
        diode_to_front_mm=18.5,
        diode_to_rear_mm=76.5,
        diode_to_side_mm=47.0,
        led_to_front_mm=13.0,
    ),
}


def robot_geometry(model: str = ROBOT_DEFAULT) -> RobotGeometry:
    """The geometry record for `model`."""
    try:
        return ROBOTS[model]
    except KeyError as exc:
        known = ", ".join(sorted(ROBOTS))
        raise ValueError(
            f"unknown robot model {model!r}; known models: {known}"
        ) from exc
