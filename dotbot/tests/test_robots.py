"""The geometry record's derived quantities, recovered from its board points."""

import math

import numpy as np
import pytest

from dotbot.robots import (
    ROBOT_DEFAULT,
    ROBOTS,
    HeadingSource,
    Point,
    RobotGeometry,
    robot_geometry,
)

V3 = ROBOTS["dotbot-v3"]


@pytest.mark.parametrize(
    "prop,expected",
    [
        ("diode_to_front_mm", 18.5),
        ("diode_to_rear_mm", 76.5),
        ("diode_to_side_mm", 47.0),
        ("led_to_front_mm", 13.0),
        ("led_ahead_of_diode_mm", 5.5),
        ("diode_ahead_of_centre_mm", 29.0),
        ("lever_arm_mm", 53.5),
        ("lever_angle_deg", 0.0),
        ("board_width_mm", 94.0),
        ("board_length_mm", 95.0),
    ],
)
def test_v3_derived_distances(prop, expected):
    assert getattr(V3, prop) == pytest.approx(expected)


def test_v3_reach_is_the_far_tyre_corner():
    """The rear outer corner of a tyre, not of the board, is the furthest point."""
    assert V3.reach_mm == pytest.approx(math.hypot(47.75, 75.5))
    assert V3.reach_mm == pytest.approx(89.33, abs=0.01)


def test_v3_core_is_the_front_edge():
    assert V3.core_mm == pytest.approx(V3.diode_to_front_mm)
    assert V3.core_mm == pytest.approx(18.5)


def test_v3_outline():
    assert V3.outline_bbox == (28.0, 52.5, 122.0, 147.5)
    assert V3.outline_centre == Point(75.0, 100.0)
    assert len(V3.outline_path) == 14


def test_v3_drivetrain_matches_the_c_constants():
    """`DB_MM_PER_COUNT` is about 0.0987 mm per count on a v3."""
    assert V3.mm_per_count == pytest.approx(0.098736, rel=1e-4)


def test_default_is_v3():
    assert robot_geometry() is V3
    assert ROBOT_DEFAULT == "dotbot-v3"


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="unknown robot model"):
        robot_geometry("dotbot-v9")


def test_an_off_centre_photodiode_is_refused():
    """A non-zero lever angle is not handled, so a record implying one fails."""
    with pytest.raises(ValueError, match="centreline"):
        RobotGeometry(
            model="off-centre",
            outline_path=V3.outline_path,
            photodiode=Point(76.0, 71.0),
            led=V3.led,
            caster=V3.caster,
            axle_midpoint=V3.axle_midpoint,
            track_mm=V3.track_mm,
            wheel_diameter_mm=V3.wheel_diameter_mm,
            tyre_width_mm=V3.tyre_width_mm,
            connector_spacing_mm=V3.connector_spacing_mm,
            connector_width_mm=V3.connector_width_mm,
            connector_length_mm=V3.connector_length_mm,
            encoder_cpr=V3.encoder_cpr,
            gear_ratio=V3.gear_ratio,
            envelope_mm=V3.envelope_mm,
        )


# --- the expansion from the photodiode to the body --------------------------

SENSOR = Point(1000.0, 1000.0)


@pytest.mark.parametrize(
    "heading,centre,nose",
    [
        (0.0, (1000.0, 971.0), (1000.0, 1018.5)),
        (90.0, (1029.0, 1000.0), (981.5, 1000.0)),
        (180.0, (1000.0, 1029.0), (1000.0, 981.5)),
        (270.0, (971.0, 1000.0), (1018.5, 1000.0)),
    ],
)
def test_the_centre_is_29_mm_behind_the_sensor(heading, centre, nose):
    """Body-forward at heading theta is (-sin, +cos)."""
    pose = V3.body_pose(SENSOR, heading, HeadingSource.TRAVEL)
    assert pose.centre == pytest.approx(centre)
    assert pose.nose == pytest.approx(nose)
    forward = (-math.sin(math.radians(heading)), math.cos(math.radians(heading)))
    assert pose.axle == pytest.approx(
        (SENSOR.x - 53.5 * forward[0], SENSOR.y - 53.5 * forward[1])
    )
    assert pose.led == pytest.approx(
        (SENSOR.x + 5.5 * forward[0], SENSOR.y + 5.5 * forward[1])
    )
    assert pose.heading_deg == heading
    assert pose.heading_source == HeadingSource.TRAVEL


@pytest.mark.parametrize("heading", [0.0, 37.0, 90.0, 213.0])
def test_a_pose_s_radii_hold_whatever_the_heading(heading):
    pose = V3.body_pose(SENSOR, heading, HeadingSource.TRAVEL)
    points = [*pose.outline, *(p for w in pose.wheels for p in w)]
    far = max(math.hypot(p.x - SENSOR.x, p.y - SENSOR.y) for p in points)
    assert pose.reach_mm == pytest.approx(far)
    assert pose.core_mm == pytest.approx(18.5)
    assert pose.envelope_mm == V3.envelope_mm


@pytest.mark.parametrize("heading", [0.0, 37.0, 90.0])
def test_the_pose_places_the_photodiode_on_the_sensor(heading):
    pose = V3.body_pose(SENSOR, heading, HeadingSource.TRAVEL)
    assert pose.photodiode == SENSOR


def test_the_robot_s_left_side_is_on_its_left():
    """At heading 0 the robot faces +y; seen from above with y down, its left
    is +x. The board's left edge is its low-x edge."""
    pose = V3.body_pose(SENSOR, 0.0, HeadingSource.TRAVEL)
    left_edge = [p for q, p in zip(V3.outline_path, pose.outline) if q.x == 28.0]
    right_edge = [p for q, p in zip(V3.outline_path, pose.outline) if q.x == 122.0]
    assert all(p.x == pytest.approx(SENSOR.x + 47.0) for p in left_edge)
    assert all(p.x == pytest.approx(SENSOR.x - 47.0) for p in right_edge)


@pytest.mark.parametrize("heading", [0.0, 37.0, 90.0, -123.0, 180.0])
def test_the_body_is_the_camera_detector_s_body(heading):
    """The detector draws the same board and the same tyres from its centre
    and its own heading convention; the two must agree point for point."""
    from dotbot.camera.detection.pose import OUTLINE_MM, WHEELS_MM, axes

    pose = V3.body_pose(SENSOR, heading, HeadingSource.TRAVEL)
    right, forward = axes(heading + 90.0)
    centre = np.asarray(pose.centre)

    def detector(path):
        return [centre + p[0] * right + p[1] * forward for p in path]

    assert np.allclose(np.asarray(pose.outline), detector(OUTLINE_MM), atol=1e-9)
    assert len(pose.wheels) == len(WHEELS_MM)
    for wheel, tyre in zip(pose.wheels, WHEELS_MM):
        assert np.allclose(np.asarray(wheel), detector(tyre), atol=1e-9)


def test_an_unknown_model_has_no_body():
    with pytest.raises(ValueError):
        robot_geometry("dotbot-v2").body_pose(SENSOR, 0.0, HeadingSource.TRAVEL)


def test_a_wheel_is_the_record_s_track_width_and_diameter():
    """The plan-view tyre rectangle is the drivetrain scalars and nothing else,
    so the console and the detector can draw the same wheel."""
    left, right = V3.wheel_paths
    for wheel, sign in ((left, -1), (right, 1)):
        xs = [p.x for p in wheel]
        ys = [p.y for p in wheel]
        assert max(xs) - min(xs) == pytest.approx(V3.tyre_width_mm)
        assert max(ys) - min(ys) == pytest.approx(V3.wheel_diameter_mm)
        assert (min(xs) + max(xs)) / 2 == pytest.approx(
            V3.axle_midpoint.x + sign * V3.track_mm / 2
        )
        assert (min(ys) + max(ys)) / 2 == pytest.approx(V3.axle_midpoint.y)


def test_the_wheels_stand_in_the_notches_beside_the_rear_tab():
    """A tyre is outside the board's rear tab and inside its widest part, which
    is why it shows on a map that draws the board over it."""
    x_min, _, x_max, _ = V3.outline_bbox
    tab = [p.x for p in V3.outline_path if p.y > V3.axle_midpoint.y]
    for wheel in V3.wheel_paths:
        xs = [p.x for p in wheel]
        assert min(xs) >= x_min - V3.tyre_width_mm / 2
        assert max(xs) <= x_max + V3.tyre_width_mm / 2
        assert min(xs) > max(tab) or max(xs) < min(tab)


def test_a_pose_carries_its_wheels_where_it_carries_its_board():
    """The wheels arrive placed in the arena frame, like the outline: the
    console is never asked to rotate a rectangle of its own."""
    pose = V3.body_pose(SENSOR, 0.0, HeadingSource.TRAVEL)
    assert len(pose.wheels) == len(V3.wheel_paths)
    # Heading 0 faces +y and the robot's left is +x, so the left wheel's
    # centre lands half a track to +x of the axle.
    left = pose.wheels[0]
    assert sum(p.x for p in left) / 4 == pytest.approx(
        pose.axle.x + V3.track_mm / 2
    )
    assert sum(p.y for p in left) / 4 == pytest.approx(pose.axle.y)
