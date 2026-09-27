# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The controller's open-loop twin of a robot, logged beside the real one."""

import math

from dotbot import kinematics
from dotbot.protocol import DIRECTION_NONE
from dotbot.robots import robot_geometry

_GEOMETRY = robot_geometry()

# Motor speed constant, RPM per volt
KV = 700

# Battery: a linear discharge over three hours
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION_S = 60 * 60 * 3


def battery_discharge_model(time_elapsed_s: float) -> int:
    """Linear discharge over MAX_BATTERY_DURATION_S (supercapacitor idle model)."""
    t = min(time_elapsed_s / MAX_BATTERY_DURATION_S, 1.0)
    return max(0, int(INITIAL_BATTERY_VOLTAGE * (1 - t)))


def wheel_speed_from_pwm(pwm: float) -> float:
    """A duty's wheel speed in mm/s, on the motor constant alone."""
    pwm = max(-100.0, min(100.0, pwm))
    return pwm * _GEOMETRY.wheel_diameter_mm * KV / (_GEOMETRY.gear_ratio * 127)


class DotBotTwin:
    """A robot moved on its reported duties alone, with no wheel lag."""

    def __init__(self, pos_x: float, pos_y: float, direction: int = DIRECTION_NONE):
        self.pos_x = float(pos_x)
        self.pos_y = float(pos_y)
        self.has_heading = direction != DIRECTION_NONE
        self.heading_deg = (
            float(kinematics.wrap180(float(direction))) if self.has_heading else 0.0
        )
        self.pwm_left = 0
        self.pwm_right = 0
        # Encoder counts not yet logged
        self.encoder_left_acc = 0.0
        self.encoder_right_acc = 0.0
        self.time_elapsed_s = 0.0
        self.battery_voltage = float(INITIAL_BATTERY_VOLTAGE)

    @property
    def direction(self) -> int:
        """The heading as advertised, DIRECTION_NONE if the twin started without one."""
        if not self.has_heading:
            return DIRECTION_NONE
        heading = int(
            math.copysign(math.floor(abs(self.heading_deg) + 0.5), self.heading_deg)
        )
        return heading - 360 if heading >= 180 else heading

    def update(self, dt: float):
        """Move for `dt` seconds on the current duties."""
        x, y, heading = kinematics.move(
            self.pos_x,
            self.pos_y,
            self.heading_deg,
            wheel_speed_from_pwm(self.pwm_left) * dt,
            wheel_speed_from_pwm(self.pwm_right) * dt,
        )
        self.pos_x, self.pos_y, self.heading_deg = float(x), float(y), float(heading)
        self.time_elapsed_s += dt
        self.battery_voltage = battery_discharge_model(self.time_elapsed_s)
