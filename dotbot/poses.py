"""A robot's pose, the few numbers that place it, and the body it places."""

from typing import Dict, Optional, Tuple

from dotbot.models import DotBotBodyModel, DotBotLH2Position, DotBotPoseModel
from dotbot.protocol import DIRECTION_NONE
from dotbot.robots import (
    ROBOTS,
    SWARMIT_DEVICE_MODELS,
    HeadingSource,
    Point,
    robot_geometry,
)

# Stands in for the body heading until the control loop advertises one.
PLACEHOLDER_HEADING_DEG = 0


def _heading(direction: int) -> Tuple[float, HeadingSource]:
    """The heading an advertised direction gives, and how it was made.

    With no advertised direction it is `PLACEHOLDER_HEADING_DEG`.
    """
    if direction != DIRECTION_NONE:
        return direction, HeadingSource.TRAVEL
    return PLACEHOLDER_HEADING_DEG, HeadingSource.NONE


def robot_pose(
    model: str, position: DotBotLH2Position, direction: int
) -> DotBotPoseModel:
    """The pose of a robot whose photodiode is at `position`, facing the
    advertised direction: its axle to 0.1 mm, its heading to 0.01 degree."""
    heading, source = _heading(direction)
    axle = robot_geometry(model).axle_at(Point(position.x, position.y), heading)
    return DotBotPoseModel.model_construct(
        x=round(axle.x, 1),
        y=round(axle.y, 1),
        heading_deg=round(float(heading), 2),
        heading_source=source.name.lower(),
    )


def robot_body(model: str, pose: DotBotPoseModel) -> DotBotBodyModel:
    """The body `pose` places, as a robot of `model`."""
    source = HeadingSource[pose.heading_source.upper()]
    return DotBotBodyModel.from_body_pose(
        robot_geometry(model).body_at_axle(
            Point(pose.x, pose.y), pose.heading_deg, source
        )
    )


def body_pose(
    model: str, position: DotBotLH2Position, direction: int
) -> DotBotBodyModel:
    """The body around an LH2 photodiode fix, facing the advertised direction."""
    heading, source = _heading(direction)
    return DotBotBodyModel.from_body_pose(
        robot_geometry(model).body_pose(Point(position.x, position.y), heading, source)
    )


def robot_models() -> Dict[str, DotBotBodyModel]:
    """Each robot model's body with its axle at the origin, facing 0."""
    return {
        name: DotBotBodyModel.from_body_pose(geometry.shape)
        for name, geometry in ROBOTS.items()
    }


def device_pose(device: str, position: DotBotLH2Position) -> Optional[DotBotBodyModel]:
    """The headingless pose of a robot swarmit reports as `device` at
    `position`, or None when the host has no geometry record for that type."""
    model = SWARMIT_DEVICE_MODELS.get(device)
    if model is None:
        return None
    return body_pose(model, position, DIRECTION_NONE)
