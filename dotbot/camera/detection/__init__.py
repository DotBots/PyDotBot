# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Finding a DotBot on the floor raster a registered camera is warped into.

Two stages: `propose` says where a robot-sized object might be, `pose` fits
the board outline to the evidence around each of those points, and `robot`
runs both and reports the results in frame millimetres.

The detector is tooling for comparing what the camera sees against what the
lighthouse reports. The camera identifies nothing by itself: a pose carries
a robot address only when a lighthouse fix handed to it stands on that
candidate.
"""

from dotbot.camera.detection.robot import (
    Detection,
    Pose,
    Prior,
    RobotDetector,
    RobotFix,
    frame_pose,
    wrap180,
)

__all__ = [
    "Detection",
    "Pose",
    "Prior",
    "RobotDetector",
    "RobotFix",
    "frame_pose",
    "wrap180",
]
