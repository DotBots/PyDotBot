# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A capture client for a controller running on the simulator.

There is no fleet behind `--conn simulator`, so a calibration session would
otherwise stall on its first point and the console's calibration mode could
not be walked at all. A simulated robot presses its calibrate app's button
at each outstanding point, `PRESS_DELAY_S` after the point opens, with the
counts a station would report there, by inverting one plausible station
matrix, so a rehearsal produces a real solve with real residuals rather than
a screen that never advances.

It is a rehearsal surface, not hardware validation: the counts are computed
from the declared point, so they agree with it by construction.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

from dotbot.calibration.ota import (
    BUTTON_CAPTURE_TAG,
    BUTTON_CHUNK_RECORDS,
    BUTTON_PRESS_MODULUS,
)

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
SIMULATED_DEVICE = "SIMULATED"
PRESS_DELAY_S = 2.0
PRESS_READS = 5


def counts_at(point_mm: tuple[float, float], station: int) -> tuple[int, int]:
    """The two sweep counts `station` would report for a floor point."""
    camera = apply_homography(
        np.linalg.inv(STATION_MATRIX), np.array([list(point_mm)], dtype=np.float64)
    )[0]
    counts = counts_for_camera_point(float(camera[0]), float(camera[1]), station)
    return (round(counts.count1), round(counts.count2))


class SimulatedCaptureClient:
    """The swarmit client surface a calibration session uses, simulated.

    `point_provider` returns the index and frame coordinates of the point
    the session is capturing, so each press matches the prompt the operator
    is answering.
    """

    def __init__(
        self,
        point_provider: Callable[[], tuple[int, tuple[float, float]] | None],
        stations: tuple[int, ...] = SIMULATED_STATIONS,
        press_delay_s: float = PRESS_DELAY_S,
    ):
        self.device = SIMULATED_DEVICE
        self._point_provider = point_provider
        self._stations = stations
        self._press_delay_s = press_delay_s
        self._press = 0
        self.pushed: list[bytes] = []

    def __enter__(self) -> SimulatedCaptureClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def press(self, point: tuple[float, float]) -> list[dict]:
        """The log events of one button press at `point`."""
        records = bytearray()
        for _ in range(PRESS_READS):
            for station in self._stations:
                count1, count2 = counts_at(point, station)
                records.append(station)
                records += count1.to_bytes(4, "little")
                records += count2.to_bytes(4, "little")
        size = 9 * BUTTON_CHUNK_RECORDS
        # A chunk short of BUTTON_CHUNK_RECORDS ends the press, so a press of
        # whole chunks ends with an empty one.
        chunks = [records[off : off + size] for off in range(0, len(records), size)]
        if len(records) % size == 0:
            chunks.append(bytearray())
        header = (self._press % BUTTON_PRESS_MODULUS) << 3
        self._press += 1
        return [
            {
                "addr": self.device,
                "data_hex": bytes([BUTTON_CAPTURE_TAG, header | index, *chunk]).hex(),
            }
            for index, chunk in enumerate(chunks)
        ]

    def send_lh2_calibration(
        self, payload: bytes, devices: list[str] | None = None
    ) -> None:
        self.pushed.append(payload)

    def refresh_device_info(self, devices: list[str] | None = None) -> None:
        pass

    def status(self) -> dict[str, Any]:
        """The one simulated robot, on current firmware, holding the last push."""
        site, calibration_id = "", ""
        if self.pushed:
            site, calibration_id = message_site(
                self.pushed[-1][:LH2_CALIBRATION_MESSAGE_BYTES]
            )
        info = SimpleNamespace(
            info_version=4, lh2_site_name=site, lh2_calibration_id=calibration_id
        )
        return {self.device: SimpleNamespace(info_gen=1, info=info)}

    def watch_log_events(self):
        """One press per opening of a point, so a redone point is pressed again."""
        seen, opened_at, pressed = None, 0.0, False
        while True:
            point = self._point_provider()
            if point != seen:
                seen, opened_at, pressed = point, time.monotonic(), False
            if point is not None and not pressed and time.monotonic() - opened_at >= self._press_delay_s:
                pressed = True
                yield from self.press(point[1])
                continue
            time.sleep(0.02)
