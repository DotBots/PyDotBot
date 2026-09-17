# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The overhead camera: registration, the warp the controller serves, detection.

`sheets` is what gets printed and where it goes, `capture` finds the camera
that sees it and reads it back, `registration` solves the homography and
writes the file. `raster` is the grid a registered camera is warped into,
`service` runs the warp and holds one JPEG for every viewer, and `detection`
finds a DotBot on that raster.

Importing this package costs nothing without the `[calibrate]` extra:
every `cv2` import sits inside the function that uses it.
"""
