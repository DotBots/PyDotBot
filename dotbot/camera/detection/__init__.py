# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Finding a DotBot on the floor raster a registered camera is warped into.

Two stages: `propose` says where a robot-sized object might be, `pose` fits
the board outline to the evidence around one of those points, and `robot`
runs both and reports the result in frame millimetres.

The detector is tooling for comparing what the camera sees against what the
lighthouse reports. It identifies nothing: one pose per frame, the strongest
candidate, with no association to any robot address.
"""

from dotbot.camera.detection.robot import (
    Detection,
    Pose,
    RobotDetector,
    frame_pose,
    wrap180,
)

__all__ = ["Detection", "Pose", "RobotDetector", "frame_pose", "wrap180"]
