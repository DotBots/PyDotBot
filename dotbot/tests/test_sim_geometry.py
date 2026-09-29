"""Pins the geometry in `dotbot.robots` and `dotbot.kinematics` to DotBot-libs
`drv/geometry.h`, as built into the vendored control core."""

import pytest

from dotbot import kinematics
from dotbot.robots import ROBOT_DEFAULT, robot_geometry
from dotbot.sim import core as control


@pytest.fixture(scope="module", name="built")
def built_fixture():
    return control.ControlCore(1).geometry()


@pytest.mark.parametrize(
    "field,record_field",
    [
        ("wheel_diameter_mm", "wheel_diameter_mm"),
        ("track_mm", "track_mm"),
        ("encoder_cpr", "encoder_cpr"),
        ("gear_ratio", "gear_ratio"),
        ("mm_per_count", "mm_per_count"),
        ("lever_arm_mm", "lever_arm_mm"),
        ("lever_angle_deg", "lever_angle_deg"),
    ],
)
def test_the_robot_record_matches_the_core(built, field, record_field):
    record = robot_geometry(ROBOT_DEFAULT)
    assert float(built[field]) == pytest.approx(getattr(record, record_field), rel=1e-6)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lever_arm_effective_mm", kinematics.LEVER_ARM_EFFECTIVE_MM),
        ("track_effective_mm", kinematics.TRACK_EFFECTIVE_MM),
        ("track_effective_arc_mm", kinematics.TRACK_EFFECTIVE_ARC_MM),
        ("track_effective_arc_ratio", kinematics.TRACK_EFFECTIVE_ARC_RATIO),
    ],
)
def test_the_kinematics_match_the_core(built, field, value):
    assert float(built[field]) == pytest.approx(value, rel=1e-6)
