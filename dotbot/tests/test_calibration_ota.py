# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the over-the-air LH2 capture decoding + collection logic.

These exercise our host-side orchestration (payload decode, trigger/wait/
retry) with a fake client. They are NOT a substitute for hardware-in-the-
loop validation of the actual swarmit transport - the fake stands in only
for the SwarmitClient surface, never for Mari/MQTT/serial behavior.
"""

import threading

from dotbot.calibration.ota import (
    CaptureSession,
    parse_capture_payload,
)

_TAG = 0xCA


def _record(lh_index: int, count1: int, count2: int) -> bytes:
    return (
        bytes([lh_index]) + count1.to_bytes(4, "little") + count2.to_bytes(4, "little")
    )


def _payload(*records: bytes) -> bytes:
    return bytes([_TAG]) + b"".join(records)


def test_parse_empty_or_untagged_returns_nothing():
    assert parse_capture_payload(b"", _TAG) == []
    # A regular text log line: first byte is not the tag.
    assert parse_capture_payload(b"hello world", _TAG) == []


def test_parse_single_sample():
    samples = parse_capture_payload(_payload(_record(0, 49341, 85887)), _TAG)
    assert len(samples) == 1
    assert samples[0].lh_index == 0
    assert samples[0].count1 == 49341
    assert samples[0].count2 == 85887


def test_parse_multiple_samples():
    samples = parse_capture_payload(
        _payload(_record(0, 1, 2), _record(1, 3, 4), _record(2, 5, 6)),
        _TAG,
    )
    assert [(s.lh_index, s.count1, s.count2) for s in samples] == [
        (0, 1, 2),
        (1, 3, 4),
        (2, 5, 6),
    ]


def test_parse_ignores_trailing_partial_record():
    # Tag + one full 9-byte record + 3 stray bytes that can't form a record.
    data = _payload(_record(0, 7, 8)) + b"\x01\x02\x03"
    samples = parse_capture_payload(data, _TAG)
    assert len(samples) == 1
    assert (samples[0].count1, samples[0].count2) == (7, 8)


class _FakeClient:
    """Minimal SwarmitClient stand-in: emits one tagged event per trigger.

    Mirrors the real firmware contract (samples only arrive in reply to a
    capture request), so CaptureSession's drain-then-trigger ordering is
    exercised the same way it is against a bot.
    """

    def __init__(self, device: str, records: bytes):
        self._device = device.upper()
        self._records = records
        self._triggered = threading.Event()

    def request_lh2_capture(self, device: str) -> None:
        self._triggered.set()

    def watch_log_events(self):
        while True:
            if self._triggered.wait(timeout=0.05):
                self._triggered.clear()
                yield {
                    "addr": self._device,
                    "data_hex": _payload(self._records).hex(),
                }


def test_capture_session_returns_triggered_sample():
    client = _FakeClient("ABCD", _record(0, 111, 222))
    with CaptureSession(client, "abcd", _TAG) as session:
        sample = session.capture(lh_index=0, timeout=2.0, retries=2)
    assert sample.lh_index == 0
    assert (sample.count1, sample.count2) == (111, 222)


def test_capture_session_ignores_other_devices():
    # Event addressed to a different bot must not satisfy the capture.
    client = _FakeClient("FFFF", _record(0, 1, 2))
    with CaptureSession(client, "ABCD", _TAG) as session:
        try:
            session.capture(lh_index=0, timeout=0.3, retries=0)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError for mismatched addr")
