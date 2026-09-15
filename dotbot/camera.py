# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The camera layer the controller serves: one warp for every viewer.

A registered camera is read on its own thread at whatever rate the device
delivers. At most `WARP_FPS_MAX` times a second one of those frames is
warped into its area's raster through the file's homography, encoded as
JPEG and held; every client of the stream is served that held frame, so
the layer costs one warp per tick rather than one per connection.

Which raster pixels have a source at all is fixed by the homography and
the frame's size, both of which hold for the whole registration, so the
camera's coverage rides in the descriptor as one polygon rather than in
every frame as an alpha channel.

`cv2` is imported inside the methods that use it, so importing this module
costs nothing without the `[calibrate]` extra.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

import numpy as np

from dotbot.area import Area
from dotbot.calibration.camera import (
    CameraCalibration,
    capture_fps,
    open_capture,
    release_capture,
    settle,
)
from dotbot.logger import LOGGER

# The raster a camera is warped into: one pixel per two millimetres of
# floor, so a 1 x 1 m area is 500 x 500. Halving it costs four times the
# pixels per frame.
MM_PER_PX = 2.0

# Warps per second. The device is read at its own rate; this is how often
# one of those frames is paid for.
WARP_FPS_MAX = 10.0

JPEG_QUALITY = 80

STREAM_BOUNDARY = "frame"
STREAM_MEDIA_TYPE = f"multipart/x-mixed-replace; boundary={STREAM_BOUNDARY}"

# Both sides of the frame-rate check are floats a driver rounds on its own.
FPS_TOLERANCE = 0.5


class CameraService:
    """One registered camera, warped into one area and held as JPEG.

    `open_source` is the seam a scripted capture is handed in on, the same
    one `collect` probes through, so the mode check and the warp are
    exercisable without a device.
    """

    def __init__(
        self,
        calibration: CameraCalibration,
        area: Area,
        open_source: Callable | None = None,
        logger=None,
    ):
        self.calibration = calibration
        self.area = area
        self.logger = logger or LOGGER.bind(context=__name__)
        self._open_source = open_source
        self._capture = None
        self._thread: threading.Thread | None = None
        self._reading = False
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._sequence = 0
        self.transform = _raster_transform(calibration.matrix, area)
        self.coverage_mm = _coverage_mm(
            calibration.matrix, calibration.width, calibration.height
        )

    @property
    def raster(self) -> tuple[int, int]:
        """The area's size in raster pixels, as (width, height)."""
        return (
            round(self.area.w / MM_PER_PX),
            round(self.area.h / MM_PER_PX),
        )

    @property
    def live(self) -> bool:
        """Registered, and holding a warped frame to serve."""
        return self._jpeg is not None

    @property
    def reading(self) -> bool:
        """The reader thread is still taking frames off the device."""
        return self._reading

    def descriptor(self) -> dict:
        """What the console needs to place, mask and label the layer."""
        width, height = self.raster
        return {
            "area": self.area.name,
            "source": self.calibration.source,
            "mm_per_px": MM_PER_PX,
            "width": width,
            "height": height,
            "span_mm": [[float(x), float(y)] for x, y in self.calibration.span_mm],
            "coverage_mm": self.coverage_mm,
            "residual_mm": float(self.calibration.residual_mm),
            "id": self.calibration.id,
            "lens": self.calibration.lens,
        }

    def start(self) -> bool:
        """Open the source, check its mode, and hold the first warp.

        Returns whether the layer is served. A camera that will not open,
        delivers nothing, or delivers a mode other than the one the file was
        solved on is a warning and no layer: the homography describes one
        pixel grid, so a plausible image off another grid would put every
        position it implies out by the scale ratio.
        """
        source = self.calibration.source
        capture = open_capture(source, self._open_source)
        if not capture.isOpened():
            release_capture(capture)
            self.logger.warning(
                "Camera source did not open, so no camera layer is served",
                source=source,
                area=self.area.name,
            )
            return False

        settled = settle(capture)
        if settled.frame is None:
            release_capture(capture)
            self.logger.warning(
                "Camera source delivered no frame, so no camera layer is served",
                source=source,
                area=self.area.name,
            )
            return False

        height, width = np.asarray(settled.frame).shape[:2]
        fps = capture_fps(capture)
        mismatch = self._mode_mismatch(int(width), int(height), fps)
        if mismatch:
            release_capture(capture)
            self.logger.warning(
                "Camera delivers a different mode than its calibration was "
                "solved on, so no camera layer is served. Register it again "
                "with `dotbot run camera-calibration collect`.",
                source=source,
                area=self.area.name,
                delivered=mismatch[0],
                calibrated=mismatch[1],
            )
            return False

        self._capture = capture
        self._reading = True
        self._warp(settled.frame)
        self._thread = threading.Thread(
            target=self._read_loop,
            name=f"Camera {self.area.name}",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop reading, drop the held frame and release the device."""
        self._reading = False
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        capture, self._capture = self._capture, None
        if capture is not None:
            release_capture(capture)
        with self._lock:
            self._jpeg = None

    def held(self) -> tuple[bytes | None, int]:
        """The latest warped JPEG and the count of warps behind it."""
        with self._lock:
            return self._jpeg, self._sequence

    async def parts(self):
        """The held frame as `multipart/x-mixed-replace` parts.

        One part per warp, never the same one twice, and the stream ends
        when the reader has stopped and its last frame has gone out: no
        further frame can arrive, and a held image re-served as a live one
        manufactures a disagreement between the robot and the picture.
        """
        interval = 1.0 / WARP_FPS_MAX
        sent = -1
        while True:
            jpeg, sequence = self.held()
            if jpeg is None:
                return
            if sequence != sent:
                sent = sequence
                yield _part(jpeg)
            if not self._reading:
                return
            await asyncio.sleep(interval)

    def _mode_mismatch(
        self, width: int, height: int, fps: float
    ) -> tuple[str, str] | None:
        """What the device delivers against what the file records, or None.

        A source that declares no frame rate is compared on size alone:
        there is nothing to compare a rate against.
        """
        recorded = self.calibration
        rate_differs = (
            recorded.fps
            and fps
            and abs(float(fps) - float(recorded.fps)) > FPS_TOLERANCE
        )
        if (width, height) == (recorded.width, recorded.height) and not rate_differs:
            return None
        return (
            _mode(width, height, fps),
            _mode(recorded.width, recorded.height, recorded.fps),
        )

    def _read_loop(self) -> None:
        """Take frames at the device's rate, warp at most `WARP_FPS_MAX`."""
        interval = 1.0 / WARP_FPS_MAX
        next_warp = 0.0
        while self._reading:
            ok, frame = self._capture.read()
            if not ok or frame is None:
                self.logger.info(
                    "Camera source stopped delivering frames",
                    source=self.calibration.source,
                    area=self.area.name,
                )
                break
            now = time.monotonic()
            if now < next_warp:
                continue
            next_warp = now + interval
            self._warp(frame)
        self._reading = False

    def _warp(self, frame) -> None:
        """One frame into the area's raster, held as JPEG."""
        import cv2  # lazy: opencv-python is only required to warp a frame

        width, height = self.raster
        warped = cv2.warpPerspective(np.asarray(frame), self.transform, (width, height))
        ok, buffer = cv2.imencode(
            ".jpg", warped, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        )
        if not ok:
            return
        with self._lock:
            self._jpeg = buffer.tobytes()
            self._sequence += 1


def _coverage_mm(matrix, width: int, height: int) -> list[list[float]]:
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


def _raster_transform(matrix, area: Area) -> np.ndarray:
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


def _mode(width: int, height: int, fps: float) -> str:
    """One video mode as the operator reads it off a camera's menu."""
    rate = f"{float(fps):g} fps" if fps else "an undeclared rate"
    return f"{int(width)} x {int(height)} at {rate}"


def _part(jpeg: bytes) -> bytes:
    """One JPEG as a part of the multipart stream."""
    head = (
        f"--{STREAM_BOUNDARY}\r\n"
        "Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(jpeg)}\r\n\r\n"
    )
    return head.encode("ascii") + jpeg + b"\r\n"
