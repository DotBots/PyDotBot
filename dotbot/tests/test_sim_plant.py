"""Tests for the simulated robots' bodies."""

import numpy as np
import pytest

from dotbot.kinematics import LEVER_ARM_EFFECTIVE_MM
from dotbot.sim.core import OUTPUT
from dotbot.sim.plant import (
    DUTY_PER_MM_S,
    DUTY_RUN,
    FIX_AGE_TICKS,
    TICK_S,
    WHEEL_TAU_S,
    FleetPlant,
)

ALL = np.ones(1, dtype=bool)
NONE = np.zeros(1, dtype=bool)


def _duty(plant: FleetPlant, left: int, right: int, brake=False):
    outputs = np.zeros(plant.count, OUTPUT)
    outputs["pwm_left"], outputs["pwm_right"] = left, right
    outputs["brake_left"] = outputs["brake_right"] = brake
    outputs["write"] = 1
    plant.apply(outputs)


def test_a_duty_holds_the_speed_of_the_feedforward_line():
    plant = FleetPlant([1000], [1000], [0])
    _duty(plant, 62, 62)
    for _ in range(100):
        plant.step(NONE)
    expected = (62 - DUTY_RUN) / DUTY_PER_MM_S
    assert plant.speed[:, 0] == pytest.approx([expected, expected], rel=1e-3)
    assert plant.heading_deg[0] == pytest.approx(0)
    assert plant.x[0] == pytest.approx(1000)
    # Facing +y: forward is down the frame
    assert plant.y[0] > 1000


def test_a_standing_wheel_needs_the_breakaway_duty():
    plant = FleetPlant([1000], [1000], [0])
    _duty(plant, 38, 38)
    for _ in range(50):
        plant.step(NONE)
    assert (plant.speed == 0).all()


def test_a_braked_wheel_stops_within_its_lag_and_stands():
    plant = FleetPlant([1000], [1000], [0])
    _duty(plant, 62, 62)
    for _ in range(100):
        plant.step(NONE)
    speed, start = plant.speed[0, 0], plant.y[0]
    _duty(plant, 0, 0, brake=True)
    for _ in range(100):
        plant.step(NONE)
    assert (plant.speed == 0).all()
    assert plant.y[0] - start == pytest.approx(speed * WHEEL_TAU_S, rel=0.05)


def test_counts_are_whole_and_carry_their_remainder():
    plant = FleetPlant([1000], [1000], [0])
    _duty(plant, 62, -62)
    total, travel = np.zeros(2), np.zeros(2)
    for _ in range(100):
        before = plant.speed[:, 0].copy()
        counts = plant.step(NONE)
        assert counts.dtype == np.int32
        total += counts[:, 0]
        travel += (before + plant.speed[:, 0]) / 2 * TICK_S
    assert np.abs(total - travel / plant.mm_per_count).max() < 1
    assert total[0] == -total[1]


def test_a_motor_error_slows_its_wheel():
    plant = FleetPlant([1000], [1000], [0], motor_error=[[0.3], [0.0]])
    _duty(plant, 62, 62)
    for _ in range(100):
        plant.step(NONE)
    assert plant.speed[0, 0] == pytest.approx(0.7 * plant.speed[1, 0])


def test_a_fix_is_the_photodiode_some_ticks_ago():
    plant = FleetPlant([1000], [1000], [0])
    _duty(plant, 80, 80)
    photodiodes = []
    for _ in range(50):
        plant.step(ALL)
        photodiodes.append(plant.photodiode())
    x, y = photodiodes[-1 - FIX_AGE_TICKS]
    assert plant.fix_sequence[0] == 50
    assert (plant.fix_x[0], plant.fix_y[0]) == (round(x[0]), round(y[0]))
    # The photodiode sits a lever arm ahead of the axle
    assert plant.photodiode()[1][0] - plant.y[0] == pytest.approx(
        LEVER_ARM_EFFECTIVE_MM
    )


def test_an_unseen_robot_gets_no_new_fix():
    plant = FleetPlant([1000], [1000], [0])
    plant.step(NONE)
    assert plant.fix_sequence[0] == 0


def test_fix_noise_has_the_declared_spread():
    plant = FleetPlant(
        [1000] * 400,
        [1000] * 400,
        [0] * 400,
        noise_mm=[5.0] * 400,
        rng=np.random.default_rng(1),
    )
    plant.step(np.ones(400, dtype=bool))
    assert np.std(plant.fix_x.astype(float)) == pytest.approx(5.0, rel=0.15)


def test_a_held_robot_does_not_move():
    plant = FleetPlant([1000], [1000], [0])
    plant.held[0] = True
    _duty(plant, 90, 90)
    for _ in range(50):
        assert (plant.step(NONE) == 0).all()
    assert (plant.x[0], plant.y[0]) == (1000, 1000)
