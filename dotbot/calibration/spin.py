# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Spin calibration: run the calibrate-spin app and turn its reads into tracks.

The app spins a robot counter clockwise in place and sends the raw counts
it read as SWARMIT_EVENT_LOG payloads: [tag][run][chunk][chunks] and 9-byte
records, the first station's reads in order, then the next station's.
DotBot-firmware apps-sandbox/calibrate-spin/main.c writes this layout.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from dotbot.calibration.conics import TRACKS_ADVISED, ConicSolution
from dotbot.calibration.lighthouse2 import (
    LH2CalibrationSample,
    TrackSample,
    station_label,
)
from dotbot.calibration.ota import _is_impossible, _parse_records
from dotbot.calibration.push import in_app, stop_robots

SPIN_TAG = 0xCC
SPIN_HEADER_BYTES = 4
SPIN_RECORD_BYTES = 9
# What one log event carries at most: 127 bytes less the header.
SPIN_CHUNK_RECORDS = 13
# The image name `dotbot swarm flash` records starts with the app's name.
SPIN_IMAGE = "calibrate-spin"
# Seconds from the start to the last chunk, at most.
SPIN_CAPTURE_TIMEOUT = 90.0
# Seconds without a new chunk, once chunks flow, after which the rest are lost.
SPIN_QUIET_TIMEOUT = 15.0
SPIN_POLL_INTERVAL = 0.5


@dataclass(frozen=True)
class SpinChunk:
    run: int
    chunk: int
    chunks: int
    records: list[LH2CalibrationSample]


def parse_spin_payload(data: bytes) -> SpinChunk | None:
    """Decode one log event of the calibrate-spin app, or None if it is not one."""
    if len(data) < SPIN_HEADER_BYTES or data[0] != SPIN_TAG:
        return None
    run, chunk, chunks = data[1], data[2], data[3]
    body = data[SPIN_HEADER_BYTES:]
    if (
        chunk >= chunks
        or len(body) % SPIN_RECORD_BYTES
        or len(body) > SPIN_CHUNK_RECORDS * SPIN_RECORD_BYTES
    ):
        return None
    return SpinChunk(run=run, chunk=chunk, chunks=chunks, records=_parse_records(body))


@dataclass
class Spin:
    """One robot's spin, as far as its chunks have arrived."""

    device: str
    run: int
    chunks: int
    received: dict[int, list[LH2CalibrationSample]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return len(self.received) == self.chunks

    def reads(self) -> list[LH2CalibrationSample]:
        """The records of every chunk received, in order; a lost chunk is a gap."""
        return [r for k in sorted(self.received) for r in self.received[k]]

    def samples(self, radius_mm: float, round_: int = 0) -> list[TrackSample]:
        """One counter clockwise track per station, as raw counts, of
        collection round `round_`."""
        by_station: dict[int, list[LH2CalibrationSample]] = {}
        for record in self.reads():
            if not _is_impossible(record):
                by_station.setdefault(record.lh_index, []).append(record)
        return [
            TrackSample(
                station=station,
                name=self.device,
                radius_mm=radius_mm,
                turn=1,
                count1=[r.count1 for r in records],
                count2=[r.count2 for r in records],
                round=round_,
            )
            for station, records in sorted(by_station.items())
        ]


class SpinAssembler:
    """Collects chunks per (device, run); copies of a chunk are dropped."""

    def __init__(self):
        self.spins: dict[tuple[str, int], Spin] = {}

    def add(self, device: str, chunk: SpinChunk) -> Spin:
        key = (device.upper(), chunk.run)
        spin = self.spins.setdefault(
            key, Spin(device=key[0], run=chunk.run, chunks=chunk.chunks)
        )
        spin.received.setdefault(chunk.chunk, chunk.records)
        return spin

    def add_event(self, event: Mapping[str, Any]) -> Spin | None:
        """Add a swarmit log event, if it is a chunk of a spin."""
        try:
            chunk = parse_spin_payload(bytes.fromhex(event.get("data_hex", "")))
        except ValueError:
            return None
        if chunk is None or not event.get("addr"):
            return None
        return self.add(str(event["addr"]), chunk)

    def by_device(self) -> dict[str, Spin]:
        """Each robot's best spin: the one with the most chunks received."""
        best: dict[str, Spin] = {}
        for spin in self.spins.values():
            held = best.get(spin.device)
            if held is None or len(spin.received) >= len(held.received):
                best[spin.device] = spin
        return best


@dataclass
class SpinRobots:
    """The robots a spin would start, sorted by what stops them."""

    ready: list[str] = field(default_factory=list)
    running: list[str] = field(default_factory=list)
    busy: dict[str, str] = field(default_factory=dict)
    wrong_image: dict[str, str] = field(default_factory=dict)
    unanswered: list[str] = field(default_factory=list)

    @property
    def robots(self) -> list[str]:
        return sorted(self.ready + self.running)

    def refusal(self) -> str:
        """Why the spin must not start, or "" when it may."""
        reasons = []
        if self.wrong_image:
            listed = ", ".join(
                f"{addr} ({name})" for addr, name in sorted(self.wrong_image.items())
            )
            devices = ",".join(sorted(self.wrong_image))
            reasons.append(
                f"not running the {SPIN_IMAGE} app: {listed}. Flash it with "
                f"`dotbot swarm -d {devices} flash -y {SPIN_IMAGE}`, or leave "
                "them out with `dotbot swarm -d <addresses> ...`."
            )
        if self.busy:
            listed = ", ".join(f"{a} ({st})" for a, st in sorted(self.busy.items()))
            reasons.append(f"resetting or programming: {listed}. Retry once done.")
        if self.unanswered:
            reasons.append(
                "no device info, so their app cannot be checked: "
                + ", ".join(self.unanswered)
                + ". Retry once they answer `dotbot swarm status`."
            )
        return "\n".join(reasons)


def check_spin_robots(status: Mapping[str, Any]) -> SpinRobots:
    """Sort the robots of a swarmit `status()` mapping for a spin."""
    out = SpinRobots()
    for addr, node in sorted(status.items()):
        info = getattr(node, "info", None)
        if info is None:
            out.unanswered.append(addr)
            continue
        name = getattr(info, "image_name", "") or ""
        if not name.startswith(SPIN_IMAGE):
            out.wrong_image[addr] = name or "unnamed image"
            continue
        state = getattr(getattr(node, "status", None), "name", "")
        if state in ("Resetting", "Programming"):
            out.busy[addr] = state
        elif in_app(node):
            out.running.append(addr)
        else:
            out.ready.append(addr)
    return out


def capture_spins(
    client: Any,
    robots: SpinRobots,
    timeout: float | None = None,
    echo: Callable[[str], None] = print,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Spin]:
    """Start the calibrate-spin app on `robots`, collect each one's spin, stop them.

    A robot already in its app is stopped first, so every robot spins anew.
    Returns each robot's spin as far as it arrived; a robot that sent
    nothing is absent. Every robot is stopped again before returning, also
    on an error or an interrupt. Raises RuntimeError when the log events
    cannot be followed or a robot does not stop.
    """
    timeout = SPIN_CAPTURE_TIMEOUT if timeout is None else timeout
    devices = robots.robots
    if robots.running:
        echo(f"Stopping {len(robots.running)} robot(s) already in the app...")
        busy = stop_robots(client, robots.running, clock=clock, sleep=sleep)
        if busy:
            raise RuntimeError("still in their app after a stop: " + ", ".join(busy))
    assembler = SpinAssembler()
    lock = threading.Lock()
    done = threading.Event()
    failure: list[BaseException] = []
    last_chunk: list[float] = []

    def listen() -> None:
        try:
            for event in client.watch_log_events():
                if done.is_set():
                    return
                with lock:
                    if assembler.add_event(event) is not None:
                        last_chunk[:] = [clock()]
        except Exception as exc:  # pylint: disable=broad-except
            failure.append(exc)

    threading.Thread(target=listen, daemon=True).start()
    # Lets the listener subscribe before the first chunk can be sent; the
    # app counts down for 3 s before it moves, and sends only after.
    sleep(SPIN_POLL_INTERVAL)
    wanted = set(devices)
    reported: set[str] = set()
    try:
        client.start(devices)
        echo(
            f"Started the {SPIN_IMAGE} app on {len(devices)} robot(s): each spins "
            "twice in place after a 3 s countdown, then sends its reads."
        )
        deadline = clock() + timeout
        while clock() < deadline:
            if failure:
                raise RuntimeError(f"lost the robots' log events: {failure[0]}")
            with lock:
                spins = {d: s for d, s in assembler.by_device().items() if d in wanted}
                quiet = (
                    bool(last_chunk) and clock() - last_chunk[0] > SPIN_QUIET_TIMEOUT
                )
            for device, spin in sorted(spins.items()):
                if spin.complete and device not in reported:
                    reported.add(device)
                    echo(
                        f"  {device}: {spin.chunks}/{spin.chunks} chunks, "
                        f"{len(spin.reads())} reads"
                    )
            if reported == wanted or quiet:
                break
            sleep(SPIN_POLL_INTERVAL)
    finally:
        done.set()
        busy = stop_robots(client, devices, clock=clock, sleep=sleep)
    if busy:
        raise RuntimeError("still in their app after a stop: " + ", ".join(busy))
    with lock:
        return {d: s for d, s in assembler.by_device().items() if d in wanted}


def spin_report(
    spins: Mapping[str, Spin],
    robots: Iterable[str],
    solutions: Mapping[int, ConicSolution],
    unsolved: Mapping[int, str],
) -> list[str]:
    """What the operator reads after a spin calibration: per circle, per station."""
    lines = []
    for device in sorted(robots):
        spin = spins.get(device)
        if spin is None:
            lines.append(f"  {device}: no reads arrived")
        elif not spin.complete:
            lines.append(
                f"  {device}: {len(spin.received)}/{spin.chunks} chunks arrived, "
                "solved from what did"
            )
    for station, solution in sorted(solutions.items()):
        lines.append(f"{station_label(station)}:")
        fits = sorted(solution.tracks + solution.dropped, key=lambda t: t.name)
        for t in fits:
            verdict = f"dropped: {t.why}" if t.why else "kept"
            name = t.name if not t.round else f"{t.name}#{t.round}"
            lines.append(
                f"  {name:<18} {t.points:4d} reads  centre "
                f"({t.centre_mm[0]:6.0f}, {t.centre_mm[1]:6.0f}) mm  "
                f"r {t.radius_mm:5.1f} mm  ratio {t.axis_ratio:.3f}  "
                f"rms {t.rms_mm:4.1f} mm  {verdict}"
            )
        lines.append(
            f"  {len(solution.tracks)} of {len(fits)} circles kept, rms "
            f"{solution.residual_mm:.1f} mm over every kept read"
        )
        if len(solution.tracks) < TRACKS_ADVISED:
            lines.append(
                f"  warning: {len(solution.tracks)} circles; {TRACKS_ADVISED} or "
                "more, spread over the area, hold the frame better"
            )
    for station, why in sorted(unsolved.items()):
        lines.append(f"{station_label(station)}: not solved, {why}")
    return lines
