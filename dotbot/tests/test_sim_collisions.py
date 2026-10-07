"""Tests for robot-robot contact in the simulated fleet."""

import math

import numpy as np
import pytest

from dotbot.dotbot_simulator import (
    DotBotSimulatorCommunicationInterface,
    InitStateToml,
    SimulatedDotBotSettings,
)
from dotbot.protocol import (
    PayloadLH2Location,
    PayloadLH2Waypoints,
    PayloadWaypointHeading,
)
from dotbot.sim import core as control
from dotbot.sim.collisions import BODY_CENTRE_AHEAD_MM, CONTACT_MM, body_centres
from dotbot.sim.core import OUTPUT
from dotbot.sim.plant import TICK_S, FleetPlant

from .test_dotbot_simulator import _frame

# Full duty: the fastest a wheel turns
DUTY_MAX = 100


def _plant(poses, collisions=True):
    """A plant of robots at (x, y, heading) axle poses."""
    x, y, heading = zip(*poses)
    return FleetPlant(list(x), list(y), list(heading), collisions=collisions)


def _drive(plant: FleetPlant, duties):
    """Hold each robot's wheels at its (left, right) duty."""
    outputs = np.zeros(plant.count, OUTPUT)
    outputs["pwm_left"] = [d[0] for d in duties]
    outputs["pwm_right"] = [d[1] for d in duties]
    outputs["write"] = 1
    plant.apply(outputs)


def _min_gap(plant: FleetPlant) -> float:
    centres = body_centres(plant.x, plant.y, plant.heading_deg)
    gap = np.linalg.norm(centres[:, None] - centres[None], axis=2)
    np.fill_diagonal(gap, np.inf)
    return float(gap.min())


def _run(plant: FleetPlant, ticks: int, each_tick=None):
    """Step `ticks` times; the smallest body gap seen at any tick."""
    fixes = np.zeros(plant.count, dtype=bool)
    smallest = _min_gap(plant)
    for _ in range(ticks):
        plant.step(fixes)
        smallest = min(smallest, _min_gap(plant))
        if each_tick is not None:
            each_tick()
    return smallest


def _axle_for_centre(cx, cy, heading):
    """The axle pose whose body centre is at (cx, cy)."""
    rad = math.radians(heading)
    return (
        cx + BODY_CENTRE_AHEAD_MM * math.sin(rad),
        cy - BODY_CENTRE_AHEAD_MM * math.cos(rad),
        heading,
    )


def test_the_body_centre_is_ahead_of_the_axle():
    centre = body_centres(np.array([1000.0]), np.array([1000.0]), np.array([0.0]))
    # Heading 0 faces +y
    assert centre[0] == pytest.approx([1000, 1000 + BODY_CENTRE_AHEAD_MM])


def test_head_on_robots_stop_at_contact():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1400, 180)])
    _drive(plant, [(70, 70), (70, 70)])
    smallest = _run(plant, 300)
    assert smallest >= CONTACT_MM
    # Stopped within a tick's travel of touching
    assert _min_gap(plant) < CONTACT_MM + 10
    assert (plant.speed == 0).all()


def test_without_collisions_robots_drive_through_each_other():
    plant = _plant(
        [_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1400, 180)],
        collisions=False,
    )
    _drive(plant, [(70, 70), (70, 70)])
    assert _run(plant, 300) < 10


def test_a_robot_driving_into_a_slower_one_follows_it_at_contact():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1200, 0)])
    _drive(plant, [(80, 80), (50, 50)])
    smallest = _run(plant, 500)
    assert smallest >= CONTACT_MM
    assert _min_gap(plant) < CONTACT_MM + 10
    # Neither is pushed: the one ahead keeps its own pace
    assert plant.speed[:, 1] == pytest.approx([(50 - 32) / 0.097] * 2, rel=1e-3)


def test_a_robot_standing_still_is_never_pushed():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1200, 0)])
    _drive(plant, [(DUTY_MAX, DUTY_MAX), (0, 0)])
    _run(plant, 300)
    assert (plant.x[1], plant.y[1]) == _axle_for_centre(1000, 1200, 0)[:2]


def test_a_glancing_robot_slides_past():
    # Centres 60 mm apart sideways: the bodies overlap on the way past
    plant = _plant([_axle_for_centre(1060, 1000, 0), _axle_for_centre(1000, 1300, 0)])
    _drive(plant, [(70, 70), (0, 0)])
    smallest = _run(plant, 400)
    assert smallest >= CONTACT_MM - 1e-6
    centres = body_centres(plant.x, plant.y, plant.heading_deg)
    # Past the robot it touched, and pushed aside by it
    assert centres[0, 1] > 1300 + CONTACT_MM
    assert centres[0, 0] > 1060


def test_many_robots_driving_into_one_never_overlap_and_never_move_it():
    count = 12
    poses = [(1000.0, 1000.0, 0.0)]
    for k in range(count):
        angle = 2 * math.pi * k / count
        cx, cy = 1000 + 300 * math.cos(
            angle
        ), 1000 + BODY_CENTRE_AHEAD_MM + 300 * math.sin(angle)
        # Facing the robot in the middle: forward is (-sin, cos)
        heading = math.degrees(
            math.atan2(-(1000 - cx), (1000 + BODY_CENTRE_AHEAD_MM - cy))
        )
        poses.append(_axle_for_centre(cx, cy, heading))
    plant = _plant(poses)
    _drive(plant, [(0, 0)] + [(70, 70)] * count)
    smallest = _run(plant, 600)
    assert smallest >= CONTACT_MM
    assert (plant.x[0], plant.y[0]) == (1000.0, 1000.0)
    # Every pusher reached the ring around the one in the middle
    centres = body_centres(plant.x, plant.y, plant.heading_deg)
    reach = np.linalg.norm(centres[1:] - centres[0], axis=1)
    assert reach.max() < 2 * CONTACT_MM


def test_a_random_crowd_never_overlaps():
    rng = np.random.default_rng(7)
    side = 8
    poses = [
        (500 + 160 * (k % side), 500 + 160 * (k // side), rng.uniform(-180, 180))
        for k in range(side * side)
    ]
    plant = _plant(poses)
    assert _min_gap(plant) >= CONTACT_MM

    def turn():
        if rng.random() < 0.05:
            _drive(plant, rng.integers(-90, 91, size=(plant.count, 2)).tolist())

    _drive(plant, rng.integers(-90, 91, size=(plant.count, 2)).tolist())
    assert _run(plant, 1500, turn) >= CONTACT_MM


def test_robots_put_down_overlapping_may_part_but_not_close():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1050, 0)])
    # The rear one drives in, the front one away
    _drive(plant, [(70, 70), (0, 0)])
    start = _min_gap(plant)
    assert _run(plant, 100) >= start
    assert np.isfinite(plant.x).all() and np.isfinite(plant.y).all()
    _drive(plant, [(0, 0), (70, 70)])
    _run(plant, 300)
    assert _min_gap(plant) > CONTACT_MM


def test_robots_put_down_on_top_of_each_other_can_drive_off():
    plant = _plant([(1000, 1000, 0), (1000, 1000, 180)])
    _drive(plant, [(70, 70), (70, 70)])
    _run(plant, 300)
    assert _min_gap(plant) > CONTACT_MM


def test_a_robot_at_full_speed_does_not_pass_through_another():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1600, 180)])
    _drive(plant, [(DUTY_MAX, DUTY_MAX), (DUTY_MAX, DUTY_MAX)])
    steps = []

    def record():
        steps.append(np.abs(plant.speed).max() * TICK_S)

    assert _run(plant, 300, record) >= CONTACT_MM
    # A tick's travel is far short of a body: nothing to tunnel through
    assert max(steps) < CONTACT_MM / 4


def test_robots_pushing_at_contact_hold_still_without_jitter():
    plant = _plant(
        [_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1400, 180)]
        # A column pushing in behind the first
        + [_axle_for_centre(1000, 1000 - 150 * k, 0) for k in (1, 2, 3)]
    )
    _drive(plant, [(70, 70)] * plant.count)
    assert _run(plant, 400) >= CONTACT_MM
    pose = (plant.x.copy(), plant.y.copy(), plant.heading_deg.copy())
    _run(plant, 200)
    for before, after in zip(pose, (plant.x, plant.y, plant.heading_deg)):
        np.testing.assert_array_equal(before, after)


def test_a_blocked_robot_stalls_its_wheels_and_counts_nothing():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1100, 0)])
    _drive(plant, [(70, 70), (0, 0)])
    fixes = np.zeros(2, dtype=bool)
    counts = sum(plant.step(fixes) for _ in range(100))
    assert (counts == 0).all()


def test_a_robot_at_contact_still_turns_in_place():
    plant = _plant([_axle_for_centre(1000, 1000, 0), _axle_for_centre(1000, 1100, 0)])
    _drive(plant, [(70, -70), (0, 0)])
    _run(plant, 100)
    assert plant.heading_deg[0] != 0
    assert _min_gap(plant) >= CONTACT_MM - 1e-6


def _waypoint(address, x, y):
    return _frame(
        address,
        PayloadLH2Waypoints(
            threshold=20,
            count=1,
            waypoints=[PayloadLH2Location(pos_x=x, pos_y=y)],
            batch_id=1,
            pass_mm=0,
            headings=[PayloadWaypointHeading()],
        ),
    )


@pytest.mark.parametrize("collisions", [True, False])
def test_robots_sent_through_each_other_stop_only_with_collisions(collisions):
    fleet = InitStateToml(
        dotbots=[
            SimulatedDotBotSettings(
                address="0000000000000001", pos_x=1000, pos_y=800, direction=0
            ),
            SimulatedDotBotSettings(
                address="0000000000000002", pos_x=1000, pos_y=1600, direction=180
            ),
        ]
    )
    sim = DotBotSimulatorCommunicationInterface(
        lambda _: None, fleet, collisions=collisions
    )
    sim.write(_waypoint("0000000000000001", 1000, 1600).to_bytes())
    sim.write(_waypoint("0000000000000002", 1000, 800).to_bytes())
    smallest = math.inf
    for _ in range(1500):
        sim.step()
        smallest = min(smallest, _min_gap(sim.plant))
    a, b = sim.dotbots
    if collisions:
        assert smallest >= CONTACT_MM
        assert a.steering_state != control.SteeringState.ARRIVED
    else:
        assert smallest < CONTACT_MM
        assert a.steering_state == control.SteeringState.ARRIVED
