# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The raster a registered camera is warped into, and the maps that fit it.

One area, one raster: a top-down grid at `MM_PER_PX` millimetres per pixel
with the area's own origin at (0, 0). Everything here is a pure function of
a registration's homography and the area, so it holds for the whole
registration and is computed once when a camera starts.
"""

from __future__ import annotations

import numpy as np

from dotbot.area import Area

# One pixel per two millimetres of floor, so a 1 x 1 m area is 500 x 500.
# Halving it costs four times the pixels per frame.
MM_PER_PX = 2.0

# Warps per second. The device is read at its own rate; this is how often
# one of those frames is paid for.
WARP_FPS_MAX = 10.0


def raster_size(area: Area) -> tuple[int, int]:
    """One area's raster, as (width, height) in pixels."""
    return (round(area.w / MM_PER_PX), round(area.h / MM_PER_PX))


def raster_transform(matrix, area: Area) -> np.ndarray:
    """Image pixels to raster pixels: the homography, then the area's scale.

    The file maps image pixels to frame millimetres; this puts the area's
    own origin at the raster's (0, 0) and scales to `MM_PER_PX`.
    """
    scale = np.array(
        [
            [1.0 / MM_PER_PX, 0.0, -area.x / MM_PER_PX],
            [0.0, 1.0 / MM_PER_PX, -area.y / MM_PER_PX],
            [0.0, 0.0, 1.0],
        ]
    )
    return scale @ np.array(matrix, dtype=np.float64)


def coverage_mm(matrix, width: int, height: int) -> list[list[float]]:
    """The floor the camera can see, as a polygon in frame millimetres.

    The source frame's own rectangle through the homography. Empty when
    the rectangle crosses the homography's horizon, where its image is not
    a polygon at all: the sign of the homogeneous divisor is constant over
    a convex hull exactly when it is constant at every corner.
    """
    if not matrix or width < 2 or height < 2:
        return []
    corners = np.array(
        [
            [0.0, 0.0, 1.0],
            [width - 1.0, 0.0, 1.0],
            [width - 1.0, height - 1.0, 1.0],
            [0.0, height - 1.0, 1.0],
        ]
    )
    mapped = corners @ np.array(matrix, dtype=np.float64).T
    divisor = mapped[:, 2]
    if not (np.all(divisor > 0) or np.all(divisor < 0)):
        return []
    points = mapped[:, :2] / divisor[:, None]
    return [[float(x), float(y)] for x, y in points]


def keep_mask(
    transform, source_size: tuple[int, int], raster: tuple[int, int]
) -> np.ndarray:
    """The raster pixels the warp had a source for, as the detector's floor.

    `source_size` is the camera frame's (width, height). Its own rectangle
    goes through the same transform, eroded so the warp's interpolated edge
    is not counted as floor. The registration sheets are inside it, not cut
    out.
    """
    import cv2  # lazy: opencv-python is only required to warp a frame

    source_width, source_height = source_size
    width, height = raster
    source = np.full((int(source_height), int(source_width)), 255, np.uint8)
    valid = cv2.warpPerspective(
        source, transform, (width, height), flags=cv2.INTER_NEAREST
    )
    return cv2.erode(valid, np.ones((3, 3), np.uint8))


def mode_string(width: int, height: int, fps: float) -> str:
    """One video mode as the operator reads it off a camera's menu."""
    rate = f"{float(fps):g} fps" if fps else "an undeclared rate"
    return f"{int(width)} x {int(height)} at {rate}"
