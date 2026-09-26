"""Tests for `dotbot.steering`, the Python port of the firmware steering, on
its own; `test_steering_fidelity.py` checks it against the C."""

import pytest

from dotbot.protocol import PayloadLH2Location, PayloadLH2Waypoints
from dotbot.steering import (
    MAX_POINTS,
    Completion,
    Output,
    Path,
    Pose,
    PoseStatus,
    Steering,
    SteeringState,
    path_from_payload,
    path_points,
    track_effective_mm,
    wheels_from_twist,
)


def _payload(n=2, **kwargs) -> PayloadLH2Waypoints:
    return PayloadLH2Waypoints(
        threshold=15,
        count=n,
        waypoints=[PayloadLH2Location(pos_x=100 * i, pos_y=200 * i) for i in range(n)],
        **kwargs,
    )


def test_a_payload_with_its_trailer_gives_the_batch_and_its_id():
    payload = _payload(batch_id=9, heading_tol_deg=4, pass_mm=35)
    payload.headings[1].heading_cdeg = -9050
    wire = PayloadLH2Waypoints().from_bytes(payload.to_bytes())
    path, batch_id = path_from_payload(wire)
    assert batch_id == 9
    assert (path.threshold_mm, path.pass_mm, path.heading_tol_deg) == (15, 35, 4)
    assert [(p.x_mm, p.y_mm) for p in path.points] == [(0, 0), (100, 200)]
    assert [p.has_heading for p in path.points] == [False, True]
    assert path.points[1].heading_deg == pytest.approx(-90.5)


def test_a_payload_without_a_trailer_has_no_headings_and_id_zero():
    points_only = _payload().to_bytes()[: 3 + 2 * 8]
    path, batch_id = path_from_payload(PayloadLH2Waypoints().from_bytes(points_only))
    assert batch_id == 0
    assert path.count == 2
    assert not any(p.has_heading for p in path.points)


def test_points_past_the_firmware_limit_are_dropped():
    path, _ = path_from_payload(_payload(n=MAX_POINTS + 3))
    assert path.count == MAX_POINTS


def test_the_twist_mixer_speeds_the_left_wheel_up_on_a_clockwise_turn():
    left, right = wheels_from_twist(0, 90)
    assert left == pytest.approx(-right)
    assert left > 0
    # In place, the spin track
    assert left - right == pytest.approx(81 * 3.14159265 / 2, rel=1e-6)
    assert track_effective_mm(100, 100) == 85


def _tracking(x=0.0, y=0.0, h=0.0) -> Pose:
    return Pose(PoseStatus.TRACKING, x, y, h)


def test_a_batch_from_rest_goes_through_no_heading_straight_to_align():
    steering = Steering()
    steering.set_path(Path(points=path_points([(0, 500)]), threshold_mm=10))
    assert steering.state == SteeringState.NO_HEADING
    assert steering.completion == Completion.IN_PROGRESS
    out = Output()
    steering.step(_tracking(h=90), 10, out)
    # Target straight ahead of +y, robot facing -x: a turn in place, clockwise
    assert steering.state == SteeringState.ALIGN
    assert out.left_mm_s == pytest.approx(-out.right_mm_s)


def test_a_seeding_pose_spins_in_place():
    steering = Steering()
    steering.set_path(Path(points=path_points([(0, 500)]), threshold_mm=10))
    out = Output()
    steering.step(Pose(PoseStatus.SEEDING, 0, 0, 0), 10, out)
    assert steering.state == SteeringState.NO_HEADING
    assert (out.left_mm_s, out.right_mm_s) == (200, -200)


def test_stop_aborts_a_batch_in_progress_and_empty_batch_stops():
    steering = Steering()
    steering.set_path(Path(points=path_points([(0, 500)]), threshold_mm=10))
    steering.set_path(Path())
    assert steering.state == SteeringState.IDLE
    assert steering.completion == Completion.ABORTED


def test_max_speed_zero_restores_the_default():
    steering = Steering()
    steering.set_max_speed(120)
    assert steering.v_max_mm_s == 120
    steering.set_max_speed(0)
    assert steering.v_max_mm_s == 300
