# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Over-the-air LH2 calibration collection (swarmit transport).

Variant A: a single DotBot, no serial cable. The bot's secure bootloader
samples its own raw LH2 counts on request (READY mode only) and ships them
back inside a SWARMIT_EVENT_LOG. This module triggers one capture per arena
corner and decodes the samples; the homography solve and save live in
`lighthouse2.LighthouseManager`, exactly as in the serial flow.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from dotbot.calibration.lighthouse2 import LH2CalibrationSample

# The four reference corners, in the order LighthouseManager expects them:
# it zips the collected counts against REFERENCE_POINTS_DEFAULT positionally
# (top-left, top-right, bottom-left, bottom-right), so the collection order
# is load-bearing, not cosmetic.
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

CAPTURE_TIMEOUT_DEFAULT = 5.0
CAPTURE_RETRIES_DEFAULT = 3

# Each raw sample inside the LOG payload is [lh_index:1][count1:4 LE][count2:4 LE].
_SAMPLE_SIZE = 9


def parse_capture_payload(data: bytes, tag: int) -> list[LH2CalibrationSample]:
    """Decode a SWARMIT_EVENT_LOG payload of raw LH2 samples.

    Layout (mirrors the swarmit bootloader): a 1-byte `tag`, then N
    fixed-size records. Returns [] for any payload that is not a capture
    (regular text log lines do not carry `tag` as their first byte).
    """
    if len(data) < 1 or data[0] != tag:
        return []
    body = data[1:]
    samples: list[LH2CalibrationSample] = []
    for off in range(0, len(body) - _SAMPLE_SIZE + 1, _SAMPLE_SIZE):
        lh_index = body[off]
        count1 = int.from_bytes(body[off + 1 : off + 5], "little")
        count2 = int.from_bytes(body[off + 5 : off + 9], "little")
        samples.append(LH2CalibrationSample(lh_index, count1, count2))
    return samples


class CaptureSession:
    """One shared log-event stream for a whole collect session.

    The bot only emits raw counts in reply to a trigger, so nothing arrives
    unsolicited - a single `watch_log_events()` stream serves every corner.
    A background reader thread decodes samples addressed to `device` into a
    queue; `capture()` triggers and waits, re-triggering on timeout because
    the trigger send is best-effort (no transport-level ack).
    """

    def __init__(self, client, device: str, tag: int):
        self._client = client
        self._device = device.upper()
        self._tag = tag
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)

    def __enter__(self) -> CaptureSession:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()

    def _reader(self) -> None:
        try:
            for event in self._client.watch_log_events():
                if self._stop.is_set():
                    break
                if str(event.get("addr", "")).upper() != self._device:
                    continue
                data = bytes.fromhex(event.get("data_hex", ""))
                for sample in parse_capture_payload(data, self._tag):
                    self._queue.put(sample)
        except Exception as exc:  # surfaced on the next capture() get()
            self._queue.put(exc)

    def capture(
        self,
        lh_index: int,
        timeout: float,
        retries: int,
        on_attempt: Callable[[int, int], None] | None = None,
    ) -> LH2CalibrationSample:
        """Trigger a capture and return the first sample for `lh_index`.

        Retries the trigger up to `retries` times; raises TimeoutError if
        no matching sample arrives. `on_attempt(n, total)` runs just before
        each trigger so callers can show progress during the otherwise silent
        wait.
        """
        # Discard anything left over from the previous corner.
        while not self._queue.empty():
            self._queue.get_nowait()

        attempts = retries + 1
        for attempt in range(attempts):
            if on_attempt is not None:
                on_attempt(attempt + 1, attempts)
            self._client.request_lh2_capture(self._device)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                if isinstance(item, Exception):
                    raise item
                if item.lh_index == lh_index:
                    return item
                # A sample for a different lighthouse: ignore, keep waiting.

        raise TimeoutError(
            f"no LH{lh_index} sample from {self._device} after "
            f"{retries + 1} attempt(s); is the DotBot in READY (app stopped) "
            f"and in view of the lighthouse?"
        )
