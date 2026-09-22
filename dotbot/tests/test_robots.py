"""The geometry record's derived quantities, recovered from its board points."""

import pytest

from dotbot.robots import ROBOT_DEFAULT, ROBOTS, Point, RobotGeometry, robot_geometry

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
            encoder_cpr=V3.encoder_cpr,
            gear_ratio=V3.gear_ratio,
            envelope_mm=V3.envelope_mm,
        )
