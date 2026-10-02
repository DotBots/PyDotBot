# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The simulated robots' bodies, the whole fleet at once.

Motor duty and brakes in; whole encoder counts and noisy LH2 fixes of the
photodiode out, the fixes FIX_AGE_TICKS old as the estimator expects. Arrays
are indexed by robot; per-wheel arrays are (2, count), left then right.
"""

import math

import numpy as np

from dotbot.kinematics import LEVER_ARM_EFFECTIVE_MM, forward, move, wrap180
from dotbot.robots import robot_geometry

TICK_S = 0.01

# Each wheel follows the speed its duty holds, and brakes, with this lag
WHEEL_TAU_S = 0.05
# The duty-to-speed line of a v3 wheel on carpet: rolling from 32 % duty at
# 0.097 % per mm/s, and a wheel at rest breaks away only from 40 %
DUTY_RUN = 32.0
DUTY_PER_MM_S = 0.097
DUTY_BREAKAWAY = 40.0

# The age of a fix when the robot reads it, in ticks: DB_POSE_ESTIMATOR_FIX_AGE_TICKS
FIX_AGE_TICKS = 2
# LH2 fixes are unsigned millimetres
FIX_MAX_MM = 0xFFFFFFFF

# Battery: a linear discharge over three hours
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION_S = 60 * 60 * 3
# A robot whose axle midpoint is this close to a charger's point charges,
# from empty to full in CHARGE_FULL_S
CHARGER_REACH_MM = 100.0
CHARGE_FULL_S = 120.0


def battery_discharge_model(time_elapsed_s: float) -> int:
    """Linear discharge over MAX_BATTERY_DURATION_S (supercapacitor idle model)."""
    t = min(time_elapsed_s / MAX_BATTERY_DURATION_S, 1.0)
    return max(0, int(INITIAL_BATTERY_VOLTAGE * (1 - t)))


class FleetPlant:
    """Truth for `count` robots: axle midpoint, heading and wheel speeds."""

    def __init__(
        self,
        x,
        y,
        heading_deg,
        motor_error=None,
        noise_mm=None,
        rng: np.random.Generator = None,
        barriers=None,
    ):
        self.x = np.array(x, dtype=float)
        self.y = np.array(y, dtype=float)
        self.heading_deg = wrap180(np.array(heading_deg, dtype=float))
        count = len(self.x)
        self.count = count
        # Share of its speed each wheel loses, as a worn or weak motor would
        self.motor_error = (
            np.zeros((2, count))
            if motor_error is None
            else np.array(motor_error, dtype=float)
        )
        self.noise_mm = (
            np.zeros(count) if noise_mm is None else np.array(noise_mm, dtype=float)
        )
        self.rng = rng if rng is not None else np.random.default_rng()
        # A site's walls and obstacles (`dotbot.sim.barriers`); None: open floor
        self.barriers = barriers if barriers else None
        self.mm_per_count = robot_geometry().mm_per_count
        self.speed = np.zeros((2, count))
        self.pwm = np.zeros((2, count))
        self.brake = np.zeros((2, count), dtype=bool)
        # Robots a hand holds still: their wheels cannot turn
        self.held = np.zeros(count, dtype=bool)
        self._travel = np.zeros((2, count))
        self._gain = 1.0 - math.exp(-TICK_S / WHEEL_TAU_S)
        # The photodiode over the last FIX_AGE_TICKS + 1 ticks, oldest first
        self._history = np.repeat(
            np.stack(self.photodiode())[np.newaxis], FIX_AGE_TICKS + 1, axis=0
        )
        self.fix_sequence = np.zeros(count, dtype=np.uint32)
        self.fix_x = np.zeros(count, dtype=np.uint32)
        self.fix_y = np.zeros(count, dtype=np.uint32)

    def photodiode(self):
        fx, fy = forward(self.heading_deg)
        return (
            self.x + LEVER_ARM_EFFECTIVE_MM * fx,
            self.y + LEVER_ARM_EFFECTIVE_MM * fy,
        )

    def _wheel_targets(self) -> np.ndarray:
        duty = np.abs(self.pwm)
        standing = (np.abs(self.speed) < 1.0) & (duty < DUTY_BREAKAWAY)
        coasting = (duty <= DUTY_RUN) | standing | self.brake
        speed = np.sign(self.pwm) * (duty - DUTY_RUN) / DUTY_PER_MM_S
        return np.where(coasting, 0.0, speed * (1.0 - self.motor_error))

    def step(self, fixes: np.ndarray):
        """Move every robot one tick. Returns each wheel's whole encoder counts
        over it, and publishes a new fix for the robots `fixes` selects."""
        target = self._wheel_targets()
        speed = self.speed + self._gain * (target - self.speed)
        # A wheel coasting to a stop stands once it has all but stopped
        speed = np.where(
            ((target == 0) & (np.abs(speed) < 0.1)) | self.held, 0.0, speed
        )
        travel = (self.speed + speed) / 2.0 * TICK_S
        travel[:, self.held] = 0.0
        self.speed = speed
        x, y, heading = move(self.x, self.y, self.heading_deg, travel[0], travel[1])
        barriers = self.barriers
        moving = np.flatnonzero((travel != 0).any(axis=0))
        if barriers is not None and len(moving):
            # A body the barriers stop stays where it was, its wheels stalled
            hit = np.zeros(len(x), dtype=bool)
            hit[moving] = barriers.refused(
                (self.x[moving], self.y[moving], self.heading_deg[moving]),
                (x[moving], y[moving], heading[moving]),
            )
            if hit.any():
                x = np.where(hit, self.x, x)
                y = np.where(hit, self.y, y)
                heading = np.where(hit, self.heading_deg, heading)
                travel[:, hit] = 0.0
                self.speed[:, hit] = 0.0
        self.x, self.y, self.heading_deg = x, y, heading
        self._travel += travel / self.mm_per_count
        counts = np.trunc(self._travel)
        self._travel -= counts

        self._history = np.roll(self._history, -1, axis=0)
        self._history[-1] = self.photodiode()
        if fixes.any():
            aged = self._history[0][:, fixes]
            if self.noise_mm.any():
                aged = (
                    aged + self.rng.standard_normal(aged.shape) * self.noise_mm[fixes]
                )
            aged = np.clip(np.rint(aged), 0, FIX_MAX_MM)
            self.fix_sequence[fixes] += 1
            self.fix_x[fixes] = aged[0]
            self.fix_y[fixes] = aged[1]
        return counts.astype(np.int32)

    def apply(self, outputs: np.ndarray):
        """Take the motor writes of one control tick."""
        write = outputs["write"] != 0
        if not write.any():
            return
        self.pwm[0, write] = outputs["pwm_left"][write]
        self.pwm[1, write] = outputs["pwm_right"][write]
        self.brake[0, write] = outputs["brake_left"][write] != 0
        self.brake[1, write] = outputs["brake_right"][write] != 0

    def place(self, index: int, x: float, y: float, heading_deg: float):
        """Put robot `index` down elsewhere, as a hand would."""
        self.x[index], self.y[index] = x, y
        self.heading_deg[index] = wrap180(heading_deg)
        px, py = self.photodiode()
        self._history[:, 0, index] = px[index]
        self._history[:, 1, index] = py[index]

    def add_counts(self, index: int, left: float, right: float):
        """Credit robot `index`'s encoders with counts its wheels did not turn."""
        self._travel[0, index] += left
        self._travel[1, index] += right
