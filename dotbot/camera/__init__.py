# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The overhead camera: registration, the warp the controller serves, detection.

`calibration` registers a camera against four printed ArUco sheets and
writes the homography; `service` warps a registered camera's frames into
its area's raster and holds one JPEG for every viewer; `detection` finds a
DotBot on that raster.

Importing this package costs nothing without the `[calibrate]` extra:
every `cv2` import sits inside the function that uses it.
"""
