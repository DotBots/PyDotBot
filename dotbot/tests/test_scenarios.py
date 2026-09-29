"""End-to-end scenarios: the controller's REST API driving simulated robots.

Deselected by default; run with `pytest -m scenario`. They check the
simulator and the controller together, on a stepped clock, and say nothing
about how a real robot behaves.
"""

import collections
import itertools
import math

import pytest
import pytest_asyncio

from dotbot.models import DotBotLH2Position
from dotbot.protocol import WaypointsStatus
from dotbot.sim.core import PoseStatus, SteeringState
from dotbot.tests.scenario_harness import (
    Scenario,
    axle_error_mm,
    heading_error_deg,
    speed_mm_s,
)

pytestmark = [pytest.mark.scenario, pytest.mark.asyncio]

A = "BADCAFE111111111"
B = "DEADBEEF22222222"

# DB_STEERING_FINAL_TOL_DEG, how far off its heading a final turn may stop
FINAL_TOL_DEG = 3.0

# Longer than the wheels must stand before a jump of the fixes is a kidnap,
# DB_POSE_ESTIMATOR_KIDNAP_SETTLE_TICKS
KIDNAP_SETTLE_S = 0.7

# The v3 body reaches 79 mm from its axle midpoint, so two bodies whose axles
# are 160 mm apart cannot touch
BODY_CLEARANCE_MM = 160


@pytest_asyncio.fixture
async def scenario(tmp_path):
    scenarios = []

    def make(dotbots, seed=0):
        scenarios.append(Scenario(tmp_path, dotbots, seed=seed))
        return scenarios[-1]

    yield make
    for made in scenarios:
        await made.close()


def _bot(address=A, x=500, y=500, **settings):
    return {"address": address, "pos_x": x, "pos_y": y, **settings}


async def test_a_waypoint_batch_arrives_within_threshold_and_time(scenario):
    """Guards the REST -> steering -> advertisement round trip of a plain batch."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    points = [(1000, 500), (1000, 1000), (600, 1200)]
    await s.waypoints(A, points, threshold=20)

    assert await s.run_until_reported([A], "ARRIVED", seconds=20)

    robot = s.robots[A]
    assert axle_error_mm(robot, *points[-1]) <= 20
    dotbot = await s.get(A)
    assert dotbot["mode"] == 0  # MANUAL once the batch is done
    assert dotbot["waypoints_status"] == WaypointsStatus.ARRIVED
    assert dotbot["waypoint_index"] == len(points)
    assert dotbot.get("waypoints_reason") is None
    assert robot.batch_id == s.batch_id(A)
    assert s.states[A][-1] == SteeringState.ARRIVED


async def test_per_point_headings_are_honoured(scenario):
    """Guards pose waypoints: the robot turns to each point's heading before going on."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(1000, 500, 90), (1000, 1000, 180)], threshold=20)
    robot = s.robots[A]
    headings_at_advance = []

    def watch():
        if robot.waypoint_index == 1 and not headings_at_advance:
            headings_at_advance.append(robot.heading_deg)

    assert await s.run_until_reported([A], "ARRIVED", seconds=20, each_tick=watch)

    tolerance = FINAL_TOL_DEG + 1
    assert heading_error_deg(headings_at_advance[0], 90) <= tolerance
    assert heading_error_deg(robot.heading_deg, 180) <= tolerance
    assert axle_error_mm(robot, 1000, 1000) <= 20
    assert SteeringState.FINAL_TURN in s.states[A]


async def test_a_robot_without_heading_acquires_it_before_driving(scenario):
    """Guards NO_HEADING: a robot from boot spins in place for a heading, then drives."""
    s = scenario([_bot()])
    await s.run(1.0)
    assert s.dotbot(A).direction is None
    robot = s.robots[A]
    start = (robot.pos_x, robot.pos_y)
    acquired_at = []

    def watch():
        if robot.estimator_status == PoseStatus.TRACKING and not acquired_at:
            acquired_at.append((robot.pos_x, robot.pos_y))

    await s.waypoints(A, [(900, 900)], threshold=20)
    assert await s.run_until_reported([A], "ARRIVED", seconds=20, each_tick=watch)

    states = s.states[A]
    assert states.index(SteeringState.NO_HEADING) < states.index(SteeringState.DRIVE)
    assert math.dist(acquired_at[0], start) < 5  # spun in place, did not drive
    assert s.dotbot(A).direction is not None
    assert axle_error_mm(robot, 900, 900) <= 20


async def test_a_robot_that_never_sees_lh2_fails_no_heading(scenario):
    """Guards the NO_HEADING timeout and its FAILED report."""
    s = scenario([_bot()])
    await s.run(1.0)
    s.robots[A].lh2_visible = False
    await s.waypoints(A, [(900, 900)])

    # 4 spins of 3 s with 1 s rests before NO_HEADING
    assert await s.run_until_reported([A], "FAILED", seconds=20)
    assert s.dotbot(A).waypoints_reason == "NO_HEADING"
    assert s.robots[A].batch_id == s.batch_id(A)


async def test_losing_lh2_mid_drive_holds_then_fails(scenario):
    """Guards HOLD: an occluded robot stops, and fails HOLD if LH2 never returns."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 2000)])
    await s.run(2.0)
    s.robots[A].lh2_visible = False

    assert await s.run_until_reported([A], "FAILED", seconds=10)
    assert SteeringState.HOLD in s.states[A]
    assert s.dotbot(A).waypoints_reason == "HOLD"
    assert speed_mm_s(s.robots[A]) == 0


async def test_lh2_returning_during_hold_resumes_the_batch(scenario):
    """Guards HOLD -> ALIGN: the batch goes on once the robot is seen again."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1500)])
    await s.run(1.5)
    robot = s.robots[A]
    robot.lh2_visible = False
    assert await s.run(5, until=lambda: robot.steering_state == SteeringState.HOLD)
    robot.lh2_visible = True

    assert await s.run_until_reported([A], "ARRIVED", seconds=15)
    assert axle_error_mm(robot, 500, 1500) <= 20


async def _pick_up_and_move(s, robot, dx_mm: float, turn_deg: float):
    """Grab a driving robot, hold it until its wheels have stood, and put it
    down elsewhere; still held once its estimator has taken it as a kidnap."""
    robot.held = True
    await s.run(KIDNAP_SETTLE_S)
    robot.kidnap(robot.pos_x + dx_mm, robot.pos_y, robot.heading_deg + turn_deg)
    assert await s.run(
        1.0, until=lambda: robot.estimator_status == PoseStatus.SEEDING
    ), "the estimator did not take the move as a kidnap"


async def test_a_robot_moved_by_hand_mid_drive_recovers(scenario):
    """Guards RECOVER: a heading lost while driving is re-acquired by driving on."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1800)])
    await s.run(1.5)
    robot = s.robots[A]
    await _pick_up_and_move(s, robot, 100, 30)
    robot.held = False

    assert await s.run_until_reported([A], "ARRIVED", seconds=20)
    assert SteeringState.RECOVER in s.states[A]
    assert axle_error_mm(robot, 500, 1800) <= 20


async def test_a_robot_moved_while_its_wheels_turn_reseeds_and_arrives(scenario):
    """Guards the LOST re-anchor: a jump the wheels did not stand through is
    not a kidnap, so the robot holds on a lost pose, then reseeds once it has
    stood and spins for a heading before finishing the batch."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1800)])
    await s.run(1.5)
    robot = s.robots[A]
    robot.kidnap(robot.pos_x + 100, robot.pos_y, robot.heading_deg + 30)
    statuses = []

    def watch():
        if not statuses or statuses[-1] != robot.estimator_status:
            statuses.append(robot.estimator_status)

    assert await s.run_until_reported([A], "ARRIVED", seconds=20, each_tick=watch)

    assert statuses.index(PoseStatus.LOST) < statuses.index(PoseStatus.SEEDING)
    states = s.states[A]
    hold = states.index(SteeringState.HOLD)
    assert SteeringState.NO_HEADING in states[hold:]
    assert SteeringState.RECOVER not in states
    assert s.dotbot(A).waypoints_reason is None
    assert axle_error_mm(robot, 500, 1800) <= 20


async def test_recovering_without_lh2_fails_heading_lost(scenario):
    """Guards the RECOVER distance limit and its HEADING_LOST report."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1800)])
    await s.run(1.5)
    robot = s.robots[A]
    await _pick_up_and_move(s, robot, 100, 0)
    robot.lh2_visible = False
    robot.held = False

    assert await s.run_until_reported([A], "FAILED", seconds=10)
    assert SteeringState.RECOVER in s.states[A]
    assert s.dotbot(A).waypoints_reason == "HEADING_LOST"


async def test_the_max_speed_command_caps_the_cruise_speed(scenario):
    """Guards CMD_MAX_SPEED end to end: confirmed in the report, honoured on the wheels."""
    s = scenario([_bot(direction=0), _bot(B, x=1500, direction=0)])
    await s.run(1.0)
    await s.max_speed(A, 100)
    await s.run(1.0)
    assert s.dotbot(A).max_speed == 100
    assert s.dotbot(B).max_speed == 300  # the firmware default, untouched

    # The wheel loop kicks a standing wheel and closes on whole counts, so
    # single ticks overshoot; the cap holds for the speed over half a second
    peak = {A: 0.0, B: 0.0}
    recent = {address: collections.deque(maxlen=50) for address in peak}

    def watch():
        for address in peak:
            recent[address].append(abs(speed_mm_s(s.robots[address])))
            window = recent[address]
            if len(window) == window.maxlen:
                peak[address] = max(peak[address], sum(window) / len(window))

    await s.waypoints(A, [(500, 1800)])
    await s.waypoints(B, [(1500, 1800)])
    assert await s.run_until_reported(peak, "ARRIVED", seconds=30, each_tick=watch)

    assert peak[A] <= 100 * 1.05
    assert peak[B] > 250  # the cap is what held A back, not the path


async def test_a_new_batch_pre_empts_the_one_in_flight(scenario):
    """Guards pre-emption: the latest batch and its id win, the first is dropped."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1800)])
    first = s.batch_id(A)
    await s.run(2.0)
    await s.waypoints(A, [(1200, 800)])
    second = s.batch_id(A)
    assert second != first

    assert await s.run_until_reported([A], "ARRIVED", seconds=20)
    robot = s.robots[A]
    assert axle_error_mm(robot, 1200, 800) <= 20
    assert robot.batch_id == second
    assert s.controller.advertised_batch_ids[A] == second


async def test_an_empty_batch_stops_the_robot(scenario):
    """Guards clear/stop: an empty batch aborts with STOP and the robot comes to rest."""
    s = scenario([_bot(direction=0)])
    await s.run(1.0)
    await s.waypoints(A, [(500, 1800)])
    await s.run(2.0)
    robot = s.robots[A]
    assert speed_mm_s(robot) > 100
    await s.waypoints(A, [])

    assert await s.run_until_reported([A], "ABORTED", seconds=2)
    assert s.dotbot(A).waypoints_reason == "STOP"
    await s.run(1.0)
    at_rest = (robot.pos_x, robot.pos_y)
    await s.run(2.0)
    assert speed_mm_s(robot) == 0
    assert (robot.pos_x, robot.pos_y) == at_rest
    assert s.dotbot(A).mode == 0


async def test_ten_robots_rotate_round_a_circle_without_touching(scenario):
    """Guards a multi-robot choreography: every step arrives and no two bodies meet."""
    count, radius, centre = 10, 600, 1500
    slots = [
        (
            round(centre + radius * math.cos(2 * math.pi * i / count)),
            round(centre + radius * math.sin(2 * math.pi * i / count)),
        )
        for i in range(count)
    ]
    addresses = [f"{0xB0 + i:016X}" for i in range(count)]
    s = scenario(
        [_bot(address, x, y, direction=0) for address, (x, y) in zip(addresses, slots)]
    )
    await s.run(1.0)
    closest = [math.inf]

    def watch():
        robots = list(s.robots.values())
        closest[0] = min(
            closest[0],
            min(
                math.hypot(p.pos_x - q.pos_x, p.pos_y - q.pos_y)
                for p, q in itertools.combinations(robots, 2)
            ),
        )

    for step in range(1, 4):
        for i, address in enumerate(addresses):
            await s.waypoints(address, [slots[(i + step) % count]], threshold=20)
        assert await s.run_until_reported(
            addresses, "ARRIVED", seconds=20, each_tick=watch
        ), f"step {step} did not arrive"
        for i, address in enumerate(addresses):
            assert axle_error_mm(s.robots[address], *slots[(i + step) % count]) <= 20

    assert closest[0] >= BODY_CLEARANCE_MM


async def test_no_origin_point_is_recorded_before_the_first_fix(scenario):
    """Guards the (0, 0) pre-fix guard: an unlocalised robot adds no trail point at origin."""
    s = scenario([_bot()])
    robot = s.robots[A]
    robot.lh2_visible = False
    await s.run(3.0)  # several advertisements of (0, 0)
    assert s.dotbot(A).lh2_position is None
    robot.lh2_visible = True
    await s.run(2.0)

    origin = DotBotLH2Position(x=0, y=0)
    dotbot = (await s.client.get(f"/controller/dotbots/{A}?trail=1000")).json()
    trail = [DotBotLH2Position(**p) for p in dotbot["trail"]]
    assert trail, "the robot was never localised"
    assert origin not in trail
    assert dotbot["lh2_position"] != {"x": 0, "y": 0}
    pushed = [state.get("lh2_position") for state in s.socket.robot_states()]
    assert any(pushed), "the stream carried no fix"
    assert {"x": 0.0, "y": 0.0} not in pushed
