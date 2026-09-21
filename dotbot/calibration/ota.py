# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Over-the-air LH2 capture collection (swarmit transport).

A DotBot's secure bootloader samples its own raw LH2 counts on request
(READY mode only) and ships them back inside a SWARMIT_EVENT_LOG. This
module triggers the captures and decodes the records; the solve and the file
live in `lighthouse2`.

A capture is n reads per point, not one: the per-point error is the
placement sigma and the lighthouse's own over sqrt(n) in quadrature, so a
single read costs about 60 % at every point of the field. Every record of
every visible station in every reply is kept, because a point seen by two
stations is the co-visibility evidence a seam needs - all but the records a
real pair of sweeps cannot produce, which `samples_from_reads` drops.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from dotbot.calibration.lighthouse2 import LH_PERIODS, LH2CalibrationSample, Sample
from dotbot.calibration.points import CORNERS  # noqa: F401 - the capture order

CAPTURE_TIMEOUT_DEFAULT = 5.0
CAPTURE_RETRIES_DEFAULT = 3
CAPTURE_READS_DEFAULT = 25

# Each raw sample inside the LOG payload is [lh_index:1][count1:4 LE][count2:4 LE].
_SAMPLE_SIZE = 9

# A capture from the calibrate app's button: [tag][header][records], the header
# packing the press counter (high five bits) and the chunk index (low three).
# The last chunk of a press carries fewer than BUTTON_CHUNK_RECORDS records.
BUTTON_CAPTURE_TAG = 0xCB
BUTTON_CHUNK_RECORDS = 13
BUTTON_PRESS_MODULUS = 32
# Seconds from a press's first chunk to its last before the press is given up.
BUTTON_CAPTURE_TIMEOUT_DEFAULT = 5.0
# Seconds a completed press is remembered, so a late copy is not a new press:
# past the copies' spread (24 events at 3.77/s on huge for four stations),
# short enough that an app restarting its counter from 0 is heard again.
BUTTON_DUPLICATE_WINDOW = 10.0

# A station really in view is decoded on nearly every read, so a station under
# this share of a point's reads is a decode artefact rather than a station.
STATION_PRESENCE_RATIO_MIN = 0.5


def parse_capture_payload(data: bytes, tag: int) -> list[LH2CalibrationSample]:
    """Decode a SWARMIT_EVENT_LOG payload of raw LH2 samples.

    Layout (mirrors the swarmit bootloader): a 1-byte `tag`, then N
    fixed-size records. Returns [] for any payload that is not a capture
    (regular text log lines do not carry `tag` as their first byte).
    """
    if len(data) < 1 or data[0] != tag:
        return []
    return _parse_records(data[1:])


def _parse_records(body: bytes) -> list[LH2CalibrationSample]:
    samples: list[LH2CalibrationSample] = []
    for off in range(0, len(body) - _SAMPLE_SIZE + 1, _SAMPLE_SIZE):
        lh_index = body[off]
        count1 = int.from_bytes(body[off + 1 : off + 5], "little")
        count2 = int.from_bytes(body[off + 5 : off + 9], "little")
        samples.append(LH2CalibrationSample(lh_index, count1, count2))
    return samples


@dataclass(frozen=True)
class ButtonChunk:
    """One log event of a button capture: part of one press's records."""

    press: int
    chunk: int
    records: list[LH2CalibrationSample]


def parse_button_payload(data: bytes) -> ButtonChunk | None:
    """Decode one log event of the calibrate app, or None if it is not one."""
    if len(data) < 2 or data[0] != BUTTON_CAPTURE_TAG:
        return None
    body = data[2:]
    if len(body) % _SAMPLE_SIZE or len(body) // _SAMPLE_SIZE > BUTTON_CHUNK_RECORDS:
        return None
    return ButtonChunk(
        press=data[1] >> 3, chunk=data[1] & 0x07, records=_parse_records(body)
    )


@dataclass
class ButtonCapture:
    """One press, assembled: its reads, and how many presses were lost before it."""

    device: str
    press: int
    reads: list[list[LH2CalibrationSample]]
    lost: int = 0


class ButtonAssembler:
    """Keeps one copy of each chunk and hands back a press once it is whole.

    The app sends every press three times, so the same (device, press, chunk)
    arrives up to three times and any copy of a chunk will do.
    """

    def __init__(
        self,
        timeout: float = BUTTON_CAPTURE_TIMEOUT_DEFAULT,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._timeout = timeout
        self._clock = clock
        self._pending: dict[tuple[str, int], tuple[float, dict[int, list]]] = {}
        # Per device: the last completed press and when it completed.
        self._completed: dict[str, tuple[int, float]] = {}

    def add(self, device: str, chunk: ButtonChunk) -> ButtonCapture | None:
        device = device.upper()
        now = self._clock()
        last = self._completed.get(device)
        if (
            last is not None
            and last[0] == chunk.press
            and now - last[1] < BUTTON_DUPLICATE_WINDOW
        ):
            return None
        key = (device, chunk.press)
        started, chunks = self._pending.setdefault(key, (now, {}))
        chunks.setdefault(chunk.chunk, chunk.records)
        records = _whole_press(chunks)
        if records is None:
            return None
        del self._pending[key]
        # A counter back at 0 is an app restart as often as a wrap, so it
        # reports nothing lost.
        lost = (
            (chunk.press - last[0] - 1) % BUTTON_PRESS_MODULUS
            if last is not None and chunk.press != 0
            else 0
        )
        self._completed[device] = (chunk.press, now)
        return ButtonCapture(
            device=device, press=chunk.press, reads=_reads_by_station(records), lost=lost
        )

    def expired(self) -> list[tuple[str, int]]:
        """Drop and return the presses that stayed incomplete past the timeout."""
        now = self._clock()
        stale = [
            key
            for key, (started, _) in self._pending.items()
            if now - started > self._timeout
        ]
        for key in stale:
            del self._pending[key]
        return stale


def _whole_press(chunks: dict[int, list]) -> list[LH2CalibrationSample] | None:
    """The press's records in order, or None while a chunk is still missing."""
    records: list[LH2CalibrationSample] = []
    for index in range(len(chunks)):
        if index not in chunks:
            return None
        records.extend(chunks[index])
        if len(chunks[index]) < BUTTON_CHUNK_RECORDS:
            return records
    return None


def _reads_by_station(
    records: list[LH2CalibrationSample],
) -> list[list[LH2CalibrationSample]]:
    """Regroup a press's records into reads, read i holding each station's i-th."""
    per_station: dict[int, list[LH2CalibrationSample]] = {}
    for record in records:
        per_station.setdefault(record.lh_index, []).append(record)
    if not per_station:
        return []
    count = min(len(column) for column in per_station.values())
    return [[column[i] for column in per_station.values()] for i in range(count)]


@dataclass
class PointCapture:
    """One point's per-station samples, plus what the quality guard dropped.

    `dropped` maps a station index to how many of its records were rejected,
    so the caller can say so once per point instead of silently solving from
    less data than it captured.
    """

    samples: list[Sample] = field(default_factory=list)
    dropped: dict[int, int] = field(default_factory=dict)

    @property
    def drop_count(self) -> int:
        return sum(self.dropped.values())

    def drop_summary(self) -> str:
        """One operator-facing line naming the stations that were dropped."""
        stations = ", ".join(f"station {index}" for index in sorted(self.dropped))
        plural = "" if self.drop_count == 1 else "s"
        return f"dropped {self.drop_count} impossible record{plural} ({stations})"


def _count_bound(station: int) -> int | None:
    """The largest LFSR count a real sweep of `station` can report.

    A count is an index into the station's 17-bit LFSR sequence and `count * 8`
    spans the rotation period, so `period // 8` is the end of the sweep; the
    sequence keeps running past it, which is where a mis-decode lands. None
    when no period is known for the index, which is itself disqualifying.
    """
    if not 0 <= station < len(LH_PERIODS):
        return None
    return LH_PERIODS[station] // 8


def _is_impossible(record: LH2CalibrationSample) -> bool:
    """True for a record that no real pair of sweeps could have produced."""
    # The two sweeps of one station hit the sensor at different rotor angles,
    # so they cannot share an LFSR index.
    if record.count1 == record.count2:
        return True
    bound = _count_bound(record.lh_index)
    if bound is None:
        return True
    return not (0 <= record.count1 <= bound and 0 <= record.count2 <= bound)


def samples_from_reads(
    reads: list[list[LH2CalibrationSample]], point: int
) -> PointCapture:
    """Group per-capture records into one `Sample` per station at `point`.

    A station that a capture missed contributes fewer reads than the others,
    which the stillness guard and the solve both tolerate. Records that are
    physically impossible, and stations that appear in too few of the reads to
    be in view at all, are dropped here and counted in the result.
    """
    per_station: dict[int, Sample] = {}
    dropped: dict[int, int] = {}
    for capture in reads:
        for record in capture:
            if _is_impossible(record):
                dropped[record.lh_index] = dropped.get(record.lh_index, 0) + 1
                continue
            sample = per_station.setdefault(
                record.lh_index, Sample(station=record.lh_index, point=point)
            )
            sample.count1.append(record.count1)
            sample.count2.append(record.count2)

    presence_minimum = len(reads) * STATION_PRESENCE_RATIO_MIN
    for index in sorted(per_station):
        if per_station[index].reads < presence_minimum:
            dropped[index] = dropped.get(index, 0) + per_station[index].reads
            del per_station[index]

    return PointCapture(
        samples=[per_station[index] for index in sorted(per_station)],
        dropped=dropped,
    )


class CaptureSession:
    """One shared log-event stream for a whole collect session.

    The bot only emits raw counts in reply to a trigger, so nothing arrives
    unsolicited - a single `watch_log_events()` stream serves every point. A
    background reader thread decodes records addressed to `device` into a
    queue; `capture()` triggers and waits, re-triggering on timeout because
    the trigger send is best-effort (no transport-level ack).

    A capture from the calibrate app's button can come from any device and
    at any time; its chunks are assembled into one `ButtonCapture` per press
    and handed to `on_button_capture`.
    """

    def __init__(
        self,
        client,
        device: str,
        tag: int,
        on_button_capture: Callable[[ButtonCapture], None] | None = None,
        button_timeout: float = BUTTON_CAPTURE_TIMEOUT_DEFAULT,
    ):
        self._client = client
        self._device = device.upper()
        self._tag = tag
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._on_button_capture = on_button_capture
        self._assembler = ButtonAssembler(timeout=button_timeout)
        self._assembler_lock = threading.Lock()
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
                addr = str(event.get("addr", "")).upper()
                data = bytes.fromhex(event.get("data_hex", ""))
                chunk = parse_button_payload(data)
                if chunk is not None:
                    self._on_button_chunk(addr, chunk)
                    continue
                if addr != self._device:
                    continue
                decoded = parse_capture_payload(data, self._tag)
                if decoded:
                    self._queue.put(decoded)
        except Exception as exc:  # surfaced on the next capture() get()
            self._queue.put(exc)

    def _on_button_chunk(self, addr: str, chunk: ButtonChunk) -> None:
        if self._on_button_capture is None:
            return
        with self._assembler_lock:
            capture = self._assembler.add(addr, chunk)
        if capture is not None:
            self._on_button_capture(capture)

    def expired_presses(self) -> list[tuple[str, int]]:
        """Button presses given up on since the last call: (device, press)."""
        with self._assembler_lock:
            return self._assembler.expired()

    def capture(
        self,
        timeout: float,
        retries: int,
        on_attempt: Callable[[int, int], None] | None = None,
    ) -> list[LH2CalibrationSample]:
        """Trigger one capture and return every station's record from the reply.

        Raises TimeoutError if nothing arrives within `retries + 1` triggers.
        """
        # Discard anything left over from the previous point.
        while not self._queue.empty():
            self._queue.get_nowait()

        attempts = retries + 1
        for attempt in range(attempts):
            if on_attempt is not None:
                on_attempt(attempt + 1, attempts)
            self._client.request_lh2_capture(self._device)
            deadline = time.monotonic() + timeout
            remaining = deadline - time.monotonic()
            while remaining > 0:
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                if isinstance(item, Exception):
                    raise item
                return item

        raise TimeoutError(
            f"no LH2 samples from {self._device} after {retries + 1} attempt(s); "
            f"is the DotBot in READY (app stopped) and in view of a lighthouse?"
        )

    def capture_point(
        self,
        point: int,
        reads: int = CAPTURE_READS_DEFAULT,
        timeout: float = CAPTURE_TIMEOUT_DEFAULT,
        retries: int = CAPTURE_RETRIES_DEFAULT,
        on_attempt: Callable[[int, int], None] | None = None,
        on_read: (
            Callable[[int, int, list[list[LH2CalibrationSample]]], None] | None
        ) = None,
    ) -> PointCapture:
        """Take `reads` captures at one point and group them per station."""
        collected: list[list[LH2CalibrationSample]] = []
        for index in range(reads):
            collected.append(
                self.capture(timeout=timeout, retries=retries, on_attempt=on_attempt)
            )
            if on_read is not None:
                on_read(index + 1, reads, collected)
        return samples_from_reads(collected, point)
