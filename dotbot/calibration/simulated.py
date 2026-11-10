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

from dotbot.calibration.lighthouse2 import (
    LH2_CALIBRATION_MESSAGE_BYTES,
    apply_homography,
    counts_for_camera_point,
    message_site,
)
from dotbot.calibration.ota import (
    BUTTON_CAPTURE_TAG,
    BUTTON_CHUNK_RECORDS,
    BUTTON_PRESS_MODULUS,
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
            if (
                point is not None
                and not pressed
                and time.monotonic() - opened_at >= self._press_delay_s
            ):
                pressed = True
                yield from self.press(point[1])
                continue
            time.sleep(0.02)


# A second station, looking at the floor from the other side
STATION_MATRIX_B = np.array(
    [
        [-150.0, -2600.0, 3100.0],
        [2100.0, -250.0, 1500.0],
        [-0.07, -0.08, 1.0],
    ],
    dtype=np.float64,
)
SPIN_READS = 120
SPIN_START_DELAY_S = 1.0
SPIN_CHUNK_GAP_S = 0.01


def spin_counts(
    centre_mm: tuple[float, float], radius_mm: float, station: int
) -> list[tuple[int, int]]:
    """The counts `station` reads from a sensor turning once counter
    clockwise round `centre_mm`."""
    matrix = STATION_MATRIX if station == 0 else STATION_MATRIX_B
    angles = np.linspace(0.0, 2 * np.pi, SPIN_READS, endpoint=False)
    # Counter clockwise as drawn, with y down
    floor = np.stack(
        [
            centre_mm[0] + radius_mm * np.cos(angles),
            centre_mm[1] - radius_mm * np.sin(angles),
        ],
        axis=1,
    )
    cameras = apply_homography(np.linalg.inv(matrix), floor)
    out = []
    for x, y in cameras:
        counts = counts_for_camera_point(float(x), float(y), station)
        out.append((round(counts.count1), round(counts.count2)))
    return out


class SimulatedSpinClient:
    """The swarmit client surface a spin uses, simulated: every robot
    `positions` returns runs calibrate-spin, and once started turns in place
    where it stands, seen by two stations."""

    def __init__(
        self,
        positions: Callable[[], dict[str, tuple[float, float]]],
        radius_mm: float,
        stations: tuple[int, ...] = SIMULATED_STATIONS,
    ):
        self._positions = positions
        self._radius_mm = radius_mm
        self._stations = stations
        self._running: dict[str, float] = {}
        self._sent: set[str] = set()
        self._run = 0

    def __enter__(self) -> SimulatedSpinClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def refresh_device_info(self, devices: list[str] | None = None) -> None:
        pass

    def status(self) -> dict[str, Any]:
        out = {}
        for address in self._positions():
            info = SimpleNamespace(
                info_version=4,
                image_name="calibrate-spin",
                image_digest="",
                lh2_site_name="",
                lh2_calibration_id="",
            )
            state = "Running" if address in self._running else "Bootloader"
            out[address] = SimpleNamespace(
                info_gen=1, info=info, status=SimpleNamespace(name=state)
            )
        return out

    def start(self, devices: list[str]) -> None:
        self._run = (self._run + 1) % 256
        for device in devices:
            self._running[device] = time.monotonic()
            self._sent.discard(device)

    def stop(self, devices: list[str]) -> None:
        for device in devices:
            self._running.pop(device, None)

    def events_of(self, device: str, centre: tuple[float, float]) -> list[dict]:
        """The log events of one robot's spin."""
        from dotbot.calibration.spin import SPIN_CHUNK_RECORDS, SPIN_TAG

        records = bytearray()
        for station in self._stations:
            for count1, count2 in spin_counts(centre, self._radius_mm, station):
                records.append(station)
                records += count1.to_bytes(4, "little")
                records += count2.to_bytes(4, "little")
        size = 9 * SPIN_CHUNK_RECORDS
        chunks = [records[off : off + size] for off in range(0, len(records), size)]
        return [
            {
                "addr": device,
                "data_hex": bytes(
                    [SPIN_TAG, self._run, index, len(chunks), *chunk]
                ).hex(),
            }
            for index, chunk in enumerate(chunks)
        ]

    def watch_log_events(self):
        while True:
            now = time.monotonic()
            positions = self._positions()
            for device, started in list(self._running.items()):
                if device in self._sent or now - started < SPIN_START_DELAY_S:
                    continue
                self._sent.add(device)
                centre = positions.get(device)
                if centre is None:
                    continue
                for event in self.events_of(device, centre):
                    yield event
                    time.sleep(SPIN_CHUNK_GAP_S)
            time.sleep(0.05)
