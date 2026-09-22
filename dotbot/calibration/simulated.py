# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A capture client for a controller running on the simulator.

There is no fleet behind `--conn simulator`, so a calibration session would
otherwise stall on its first capture and the console's calibration mode
could not be walked at all. This answers each capture request with the
counts a station would report for the point the session is asking about, by
inverting one plausible station matrix, so a rehearsal produces a real solve
with real residuals rather than a screen that never advances.

It is a rehearsal surface, not hardware validation: the counts are computed
from the declared point, so they agree with it by construction.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

from dotbot.calibration.lighthouse2 import (
    LH2_CALIBRATION_MESSAGE_BYTES,
    apply_homography,
    counts_for_camera_point,
    message_site,
)

# A wall-mounted station: the magnitude of perspective row real files carry.
STATION_MATRIX = np.array(
    [
        [1523.4, -38.2, 1012.7],
        [41.9, 1531.8, 988.3],
        [0.2134, -0.0871, 1.0],
    ],
    dtype=np.float64,
)

SIMULATED_STATIONS = (0, 1)

# What a capture reply carries, mirroring the bootloader's log payload.
_SAMPLE_TAG: int | None = None


def _tag() -> int:
    global _SAMPLE_TAG
    if _SAMPLE_TAG is None:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        _SAMPLE_TAG = LH2_CALIB_TAG
    return _SAMPLE_TAG


def counts_at(point_mm: tuple[float, float], station: int) -> tuple[int, int]:
    """The two sweep counts `station` would report for a floor point."""
    camera = apply_homography(
        np.linalg.inv(STATION_MATRIX), np.array([list(point_mm)], dtype=np.float64)
    )[0]
    counts = counts_for_camera_point(float(camera[0]), float(camera[1]), station)
    return (round(counts.count1), round(counts.count2))


class SimulatedCaptureClient:
    """The swarmit client surface a calibration session uses, simulated.

    `point_provider` returns the frame coordinates the session is capturing,
    so each reply matches the prompt the operator is answering.
    """

    def __init__(
        self,
        device: str,
        point_provider: Callable[[], tuple[float, float] | None],
        stations: tuple[int, ...] = SIMULATED_STATIONS,
    ):
        self.device = (device or "SIMULATED").upper()
        self._point_provider = point_provider
        self._stations = stations
        self._pending: list[dict] = []
        self.pushed: list[bytes] = []

    def __enter__(self) -> SimulatedCaptureClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def request_lh2_capture(self, device: str) -> None:
        point = self._point_provider()
        if point is None:
            return
        body = bytearray([_tag()])
        for station in self._stations:
            count1, count2 = counts_at(point, station)
            body.append(station)
            body += count1.to_bytes(4, "little")
            body += count2.to_bytes(4, "little")
        self._pending.append({"addr": self.device, "data_hex": bytes(body).hex()})

    def send_lh2_calibration(
        self, payload: bytes, devices: list[str] | None = None
    ) -> None:
        self.pushed.append(payload)

    def refresh_device_info(self, devices: list[str] | None = None) -> None:
        pass

    def status(self) -> dict[str, Any]:
        """The one simulated robot, on float32 firmware, holding the last push."""
        site, calibration_id = "", ""
        if self.pushed:
            site, calibration_id = message_site(
                self.pushed[-1][:LH2_CALIBRATION_MESSAGE_BYTES]
            )
        info = SimpleNamespace(
            info_version=2, lh2_site_name=site, lh2_calibration_id=calibration_id
        )
        return {self.device: SimpleNamespace(info_gen=1, info=info)}

    def watch_log_events(self):
        import time

        while True:
            if self._pending:
                yield self._pending.pop(0)
            else:
                time.sleep(0.02)
