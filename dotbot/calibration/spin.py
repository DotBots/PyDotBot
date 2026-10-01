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

import numpy as np

from dotbot.calibration.conics import (
    TRACKS_ADVISED,
    ConicSolution,
    Track,
)
from dotbot.calibration.lighthouse2 import (
    LH2CalibrationSample,
    LH2Counts,
    TrackSample,
    calculate_camera_point,
)
from dotbot.calibration.ota import _is_impossible, _parse_records

SPIN_TAG = 0xCC
SPIN_HEADER_BYTES = 4
# The image name `dotbot swarm flash` records starts with the app's name.
SPIN_IMAGE = "calibrate-spin"
# Seconds from the start to the last chunk: a spin took about 29 s on the
# bench, mostly sending at the node's uplink pace.
SPIN_CAPTURE_TIMEOUT = 90.0
# Seconds a stopped robot gets to report it left its app.
SPIN_STOP_TIMEOUT = 10.0
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
    if chunk >= chunks or len(body) % 9:
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

    def samples(self, radius_mm: float) -> list[TrackSample]:
        """One counter clockwise track per station, as raw counts."""
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
            )
            for station, records in sorted(by_station.items())
        ]

    def tracks(self, radius_mm: float) -> list[Track]:
        """One counter clockwise track per station, in camera points."""
        return [
            Track(
                points=np.array(
                    [
                        calculate_camera_point(LH2Counts(s.station, c1, c2))
                        for c1, c2 in zip(s.count1, s.count2)
                    ]
                ),
                radius_mm=radius_mm,
                turn=s.turn,
                name=f"{s.name}/{s.station}",
            )
            for s in self.samples(radius_mm)
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
        if self.unanswered:
            reasons.append(
                "no device info, so their app cannot be checked: "
                + ", ".join(self.unanswered)
                + ". Retry once they answer `dotbot swarm status`."
            )
        return "\n".join(reasons)


def _status_name(node: Any) -> str:
    return getattr(getattr(node, "status", None), "name", "")


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
        if _status_name(node) in ("Running", "Stopping"):
            out.running.append(addr)
        else:
            out.ready.append(addr)
    return out


def _wait_stopped(
    client: Any, devices: list[str], timeout: float, clock, sleep
) -> list[str]:
    """The robots still in their app after `timeout`."""
    deadline = clock() + timeout
    while True:
        status = client.status()
        busy = [
            d for d in devices if _status_name(status.get(d)) in ("Running", "Stopping")
        ]
        if not busy or clock() >= deadline:
            return busy
        sleep(SPIN_POLL_INTERVAL)


def capture_spins(
    client: Any,
    robots: SpinRobots,
    timeout: float = SPIN_CAPTURE_TIMEOUT,
    echo: Callable[[str], None] = print,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Spin]:
    """Start the calibrate-spin app on `robots`, collect each one's spin, stop them.

    A robot already in its app is stopped first, so every robot spins anew.
    Returns each robot's spin as far as it arrived; a robot that sent
    nothing is absent. Every robot is stopped again before returning, so a
    calibration push reaches them.
    """
    devices = robots.robots
    if robots.running:
        echo(f"Stopping {len(robots.running)} robot(s) already in the app...")
        client.stop(robots.running)
        busy = _wait_stopped(client, robots.running, SPIN_STOP_TIMEOUT, clock, sleep)
        if busy:
            raise RuntimeError("still in their app after a stop: " + ", ".join(busy))
    assembler = SpinAssembler()
    lock = threading.Lock()
    started = threading.Event()

    def listen(events: Iterable[dict]) -> None:
        for event in events:
            if not started.is_set():
                continue
            with lock:
                assembler.add_event(event)

    events = client.watch_log_events()
    threading.Thread(target=listen, args=(events,), daemon=True).start()
    # Lets the listener subscribe before the first chunk can be sent; the
    # app counts down for 3 s before it moves, and sends only after.
    sleep(SPIN_POLL_INTERVAL)
    started.set()
    client.start(devices)
    echo(
        f"Started the {SPIN_IMAGE} app on {len(devices)} robot(s): each spins "
        "twice in place after a 3 s countdown, then sends its reads."
    )
    wanted = set(devices)
    reported: set[str] = set()
    deadline = clock() + timeout
    try:
        while clock() < deadline:
            with lock:
                spins = {d: s for d, s in assembler.by_device().items() if d in wanted}
            for device, spin in sorted(spins.items()):
                if spin.complete and device not in reported:
                    reported.add(device)
                    echo(
                        f"  {device}: {spin.chunks}/{spin.chunks} chunks, "
                        f"{len(spin.reads())} reads"
                    )
            if reported == wanted:
                break
            sleep(SPIN_POLL_INTERVAL)
    finally:
        client.stop(devices)
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
        lines.append(f"station {station}:")
        fits = sorted(solution.tracks + solution.dropped, key=lambda t: t.name)
        for t in fits:
            verdict = f"dropped: {t.why}" if t.why else "kept"
            lines.append(
                f"  {t.name:<18} {t.points:4d} reads  centre "
                f"({t.centre_mm[0]:6.0f}, {t.centre_mm[1]:6.0f}) mm  "
                f"r {t.radius_mm:5.1f} mm  ratio {t.axis_ratio:.3f}  "
                f"rms {t.rms_mm:4.1f} mm  {verdict}"
            )
        lines.append(
            f"  {len(solution.tracks)} of {len(fits)} circles kept, residual "
            f"{solution.residual_mm:.1f} mm"
        )
        if len(solution.tracks) < TRACKS_ADVISED:
            lines.append(
                f"  warning: {len(solution.tracks)} circles; {TRACKS_ADVISED} or "
                "more, spread over the area, hold the frame better"
            )
    for station, why in sorted(unsolved.items()):
        lines.append(f"station {station}: not solved, {why}")
    return lines
