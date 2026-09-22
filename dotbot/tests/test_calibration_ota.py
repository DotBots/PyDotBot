# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the over-the-air LH2 capture decoding + collection logic.

These exercise our host-side orchestration (payload decode, trigger/wait/
retry, per-station accumulation) with a fake client. They are NOT a
substitute for hardware-in-the-loop validation of the actual swarmit
transport - the fake stands in only for the SwarmitClient surface, never for
Mari/MQTT/serial behavior.
"""

import threading

from dotbot.calibration.lighthouse2 import LH_PERIODS
from dotbot.calibration.ota import (
    BUTTON_CAPTURE_TIMEOUT_DEFAULT,
    ButtonAssembler,
    CaptureSession,
    parse_button_payload,
    parse_capture_payload,
    samples_from_reads,
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
        self.triggers = 0

    def request_lh2_capture(self, device: str) -> None:
        self.triggers += 1
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
        samples = session.capture(timeout=2.0, retries=2)
    assert len(samples) == 1
    assert samples[0].lh_index == 0
    assert (samples[0].count1, samples[0].count2) == (111, 222)


def test_capture_session_ignores_other_devices():
    # Event addressed to a different bot must not satisfy the capture.
    client = _FakeClient("FFFF", _record(0, 1, 2))
    with CaptureSession(client, "ABCD", _TAG) as session:
        try:
            session.capture(timeout=0.3, retries=0)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError for mismatched addr")


def test_a_two_station_capture_payload_yields_two_samples():
    """Every visible station's records are kept, which is the seam evidence."""
    client = _FakeClient("ABCD", _record(0, 111, 222) + _record(1, 333, 444))
    with CaptureSession(client, "ABCD", _TAG) as session:
        samples = session.capture_point(
            point=0, reads=1, timeout=2.0, retries=0
        ).samples

    assert [s.station for s in samples] == [0, 1]
    assert [s.point for s in samples] == [0, 0]
    assert samples[0].count1 == [111] and samples[0].count2 == [222]
    assert samples[1].count1 == [333] and samples[1].count2 == [444]


def test_n_reads_accumulate_per_station():
    client = _FakeClient("ABCD", _record(0, 10, 20) + _record(1, 30, 40))
    with CaptureSession(client, "ABCD", _TAG) as session:
        samples = session.capture_point(
            point=2, reads=5, timeout=2.0, retries=0
        ).samples

    assert client.triggers == 5
    assert [s.reads for s in samples] == [5, 5]
    assert all(s.point == 2 for s in samples)
    assert samples[0].mean_counts().count1 == 10.0


def test_samples_from_reads_tolerates_a_station_a_capture_missed():
    reads = [
        parse_capture_payload(_payload(_record(0, 1, 2), _record(1, 3, 4)), _TAG),
        parse_capture_payload(_payload(_record(0, 5, 6)), _TAG),
    ]
    capture = samples_from_reads(reads, point=1)
    assert {s.station: s.reads for s in capture.samples} == {0: 2, 1: 1}
    assert capture.dropped == {}


# --- the capture-quality guard ----------------------------------------------
#
# A phantom station observed on the bench: a mis-decode in the firmware's
# polynomial matcher attributes a degenerate bit pattern to a basestation that
# is not there, with both sweeps on the same LFSR index and a count past the
# end of the sweep. The host cannot fix the decode, but it must not solve from
# it.

_PHANTOM_BYTES = bytes.fromhex("ca04b1fa0100b1fa0100")
_PHANTOM_COUNT = 129713


def test_the_bench_phantom_parses_faithfully():
    """The wire bytes of the phantom decode as sent - the parser is not at fault."""
    samples = parse_capture_payload(_PHANTOM_BYTES, _TAG)
    assert len(samples) == 1
    assert samples[0].lh_index == 4
    assert samples[0].count1 == _PHANTOM_COUNT
    assert samples[0].count2 == _PHANTOM_COUNT
    # And it is not a count any sweep of station 4 could report.
    assert _PHANTOM_COUNT > LH_PERIODS[4] // 8


def test_the_bench_phantom_is_dropped_and_creates_no_station():
    """23 good station-0 reads + the 2 phantom reads, as captured on the bench."""
    reads = [parse_capture_payload(_payload(_record(0, 43166, 75717)), _TAG)] * 23
    reads += [parse_capture_payload(_PHANTOM_BYTES, _TAG)] * 2

    capture = samples_from_reads(reads, point=0)
    assert [s.station for s in capture.samples] == [0]
    assert capture.samples[0].reads == 23
    assert capture.dropped == {4: 2}
    assert capture.drop_summary() == "dropped 2 impossible records (station 4)"


def test_equal_counts_are_dropped_even_inside_the_sweep():
    reads = [parse_capture_payload(_payload(_record(0, 5000, 5000)), _TAG)]
    capture = samples_from_reads(reads, point=0)
    assert capture.samples == []
    assert capture.dropped == {0: 1}


def test_a_count_past_the_end_of_the_sweep_is_dropped():
    over = LH_PERIODS[0] // 8 + 1
    reads = [parse_capture_payload(_payload(_record(0, 1000, over)), _TAG)]
    capture = samples_from_reads(reads, point=0)
    assert capture.samples == []
    assert capture.dropped == {0: 1}


def test_a_station_with_no_known_period_is_dropped():
    reads = [parse_capture_payload(_payload(_record(len(LH_PERIODS), 10, 20)), _TAG)]
    capture = samples_from_reads(reads, point=0)
    assert capture.samples == []
    assert capture.dropped == {len(LH_PERIODS): 1}


def test_a_station_seen_in_too_few_reads_is_dropped():
    """Station 1 is decoded in 2 of 25 reads: too rare to be in view."""
    reads = [parse_capture_payload(_payload(_record(0, 100, 200)), _TAG)] * 23
    reads += [
        parse_capture_payload(
            _payload(_record(0, 100, 200), _record(1, 300, 400)), _TAG
        )
    ] * 2

    capture = samples_from_reads(reads, point=0)
    assert [s.station for s in capture.samples] == [0]
    assert capture.samples[0].reads == 25
    assert capture.dropped == {1: 2}
    assert capture.drop_summary() == "dropped 2 impossible records (station 1)"


def test_a_station_seen_in_every_read_is_kept():
    reads = [parse_capture_payload(_payload(_record(0, 100, 200)), _TAG)] * 25
    capture = samples_from_reads(reads, point=0)
    assert [s.station for s in capture.samples] == [0]
    assert capture.samples[0].reads == 25
    assert capture.dropped == {}


def test_a_genuine_second_station_in_every_read_is_kept():
    reads = [
        parse_capture_payload(
            _payload(_record(0, 100, 200), _record(1, 300, 400)), _TAG
        )
    ] * 25
    capture = samples_from_reads(reads, point=0)
    assert {s.station: s.reads for s in capture.samples} == {0: 25, 1: 25}
    assert capture.dropped == {}


# --- captures from the calibrate app's button -------------------------------

_BUTTON_TAG = 0xCB


def _button_events(press: int, stations: dict[int, tuple[int, int]], reads: int = 25):
    """The log events of one press, one copy: records read by read, 13 per chunk."""
    records = [
        _record(index, count1 + i, count2 + i)
        for i in range(reads)
        for index, (count1, count2) in stations.items()
    ]
    chunks = [records[i : i + 13] for i in range(0, len(records), 13)]
    if len(records) % 13 == 0:
        chunks.append([])
    return [
        bytes([_BUTTON_TAG, (press << 3) | index]) + b"".join(chunk)
        for index, chunk in enumerate(chunks)
    ]


_TWO_STATIONS = {0: (43800, 81450), 1: (51000, 62000)}


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_firmwares_button_press_assembles_into_its_reads():
    from dotbot.tests.lh2_button_fixture import (
        EVENTS_HEX,
        PRESS,
        READS,
        STATION_COUNTS,
    )

    assembler = ButtonAssembler()
    captures = [
        assembler.add("feed", parse_button_payload(bytes.fromhex(event)))
        for event in EVENTS_HEX
    ]
    assert captures[:-1] == [None] * (len(EVENTS_HEX) - 1)
    capture = captures[-1]
    assert capture.press == PRESS
    assert len(capture.reads) == READS
    for i, read in enumerate(capture.reads):
        assert [(r.lh_index, r.count1, r.count2) for r in read] == [
            (station, count1 + i, count2 + i)
            for station, (count1, count2) in STATION_COUNTS.items()
        ]


def test_parse_button_payload_reads_press_chunk_and_records():
    events = _button_events(3, {0: (10, 20)}, reads=1)
    chunk = parse_button_payload(events[0])
    assert (chunk.press, chunk.chunk) == (3, 0)
    assert [(r.lh_index, r.count1, r.count2) for r in chunk.records] == [(0, 10, 20)]
    # The READY tag, a text line and a truncated record are not button chunks.
    assert parse_button_payload(_payload(_record(0, 1, 2))) is None
    assert parse_button_payload(b"R12 n30/60") is None
    assert parse_button_payload(events[0][:-1]) is None


def test_two_stations_arrive_as_four_chunks_of_13_13_13_11():
    events = _button_events(0, _TWO_STATIONS)
    assert [len(parse_button_payload(e).records) for e in events] == [13, 13, 13, 11]


def test_three_copies_with_a_lost_and_a_duplicated_chunk_assemble_once():
    copy = _button_events(0, _TWO_STATIONS)
    # Copy 1 lacks chunk 1, copy 2 carries chunk 2 twice, copy 3 is whole:
    # twelve events once the duplicate replaces the lost one.
    stream = copy[:1] + copy[2:] + copy[:2] + copy[2:3] + copy[2:] + copy
    assembler = ButtonAssembler()
    captures = [
        c
        for c in (assembler.add("abcd", parse_button_payload(e)) for e in stream)
        if c is not None
    ]
    assert len(captures) == 1
    capture = captures[0]
    assert (capture.device, capture.press, capture.lost) == ("ABCD", 0, 0)
    assert len(capture.reads) == 25
    point = samples_from_reads(capture.reads, point=0)
    assert [(s.station, s.reads) for s in point.samples] == [(0, 25), (1, 25)]
    assert point.samples[0].count1[:3] == [43800, 43801, 43802]


def test_a_chunk_missing_from_every_copy_yields_nothing_and_expires():
    copy = _button_events(4, _TWO_STATIONS)
    clock = _Clock()
    assembler = ButtonAssembler(timeout=5.0, clock=clock)
    for _ in range(3):
        for event in copy[:1] + copy[2:]:
            assert assembler.add("ABCD", parse_button_payload(event)) is None
    clock.now = 4.0
    assert assembler.expired() == []
    clock.now = 6.0
    assert assembler.expired() == [("ABCD", 4)]
    assert assembler.expired() == []


def test_an_incomplete_press_expires_without_anyone_polling():
    """A reused press number starts over instead of merging into the stale one."""
    clock = _Clock()
    assembler = ButtonAssembler(timeout=5.0, clock=clock)
    old = _button_events(4, _TWO_STATIONS)
    for event in old[:1] + old[2:]:
        assembler.add("ABCD", parse_button_payload(event))
    clock.now = 6.0
    new = _button_events(4, {0: (1000, 2000), 1: (3000, 4000)})
    captures = [assembler.add("ABCD", parse_button_payload(e)) for e in new]
    assert [c.reads[0][0].count1 for c in captures if c is not None] == [1000]
    assert assembler.expired() == [("ABCD", 4)]


def test_late_copies_of_a_given_up_press_are_not_reported_again():
    clock = _Clock()
    assembler = ButtonAssembler(timeout=5.0, clock=clock)
    copy = _button_events(4, _TWO_STATIONS)
    for event in copy[:1] + copy[2:]:
        assembler.add("ABCD", parse_button_payload(event))
    clock.now = 6.0
    assert assembler.expired() == [("ABCD", 4)]
    clock.now = 7.0
    for event in copy[2:]:
        assert assembler.add("ABCD", parse_button_payload(event)) is None
    clock.now = 13.0
    assert assembler.expired() == []


def test_the_last_copy_arrives_within_the_press_timeout():
    """Four stations' 24 events at half of huge's 3.77 packets/s."""
    assert BUTTON_CAPTURE_TIMEOUT_DEFAULT > 24 / (3.77 / 2)


def test_a_chunk_that_differs_from_its_stored_copy_starts_a_new_press():
    assembler = ButtonAssembler()
    old = _button_events(4, _TWO_STATIONS)
    for event in old[:1] + old[2:]:
        assembler.add("ABCD", parse_button_payload(event))
    new = _button_events(4, {0: (1000, 2000), 1: (3000, 4000)})
    captures = [assembler.add("ABCD", parse_button_payload(e)) for e in new]
    assert [c.reads[0][0].count1 for c in captures if c is not None] == [1000]


def test_a_jump_in_the_press_counter_reports_the_lost_presses():
    assembler = ButtonAssembler()
    results = []
    for press in (3, 5):
        for event in _button_events(press, {0: (100, 200)}):
            capture = assembler.add("ABCD", parse_button_payload(event))
            if capture is not None:
                results.append((capture.press, capture.lost))
    assert results == [(3, 0), (5, 1)]


def test_a_late_copy_of_a_completed_press_is_not_a_new_press():
    clock = _Clock()
    assembler = ButtonAssembler(clock=clock)
    copy = _button_events(1, {0: (100, 200)})
    captures = [assembler.add("ABCD", parse_button_payload(e)) for e in copy]
    clock.now = 6.0
    captures += [assembler.add("ABCD", parse_button_payload(e)) for e in copy * 2]
    assert [c.press for c in captures if c is not None] == [1]


def test_an_app_restart_reusing_press_0_is_a_new_press_with_nothing_lost():
    clock = _Clock()
    assembler = ButtonAssembler(clock=clock)
    captures = []
    for at, press in ((0.0, 0), (20.0, 1), (60.0, 0)):
        clock.now = at
        for event in _button_events(press, {0: (100, 200)}):
            captures.append(assembler.add("ABCD", parse_button_payload(event)))
    assert [(c.press, c.lost) for c in captures if c is not None] == [
        (0, 0),
        (1, 0),
        (0, 0),
    ]


class _ButtonClient:
    """Emits one press's events, three copies, from a device the session did not name."""

    def __init__(self, events: list[bytes]):
        self._events = events

    def watch_log_events(self):
        for data in self._events:
            yield {"addr": "FEED", "data_hex": data.hex()}
        threading.Event().wait()


def test_capture_session_hands_a_button_press_from_any_device_over_once():
    got = []
    done = threading.Event()

    def on_button(capture):
        got.append(capture)
        done.set()

    events = _button_events(2, _TWO_STATIONS) * 3
    with CaptureSession(
        _ButtonClient(events), "ABCD", _TAG, on_button_capture=on_button
    ):
        assert done.wait(timeout=2.0)
    assert [(c.device, c.press, len(c.reads)) for c in got] == [("FEED", 2, 25)]
