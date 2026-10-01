"""Tests for decoding the calibrate-spin app's log events into tracks.

The payloads are packed the way apps-sandbox/calibrate-spin/main.c packs
them, from counts derived from a synthetic station, so a spin's bytes can be
followed all the way to a solved homography.
"""

import queue
import re
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from click.testing import CliRunner

from dotbot.calibration import conics, lighthouse2
from dotbot.calibration import spin as spin_module
from dotbot.calibration.lighthouse2 import counts_for_camera_point
from dotbot.calibration.spin import (
    SPIN_TAG,
    SpinAssembler,
    check_spin_robots,
    parse_spin_payload,
)
from dotbot.cli import swarm_lh2
from dotbot.config import load_discovered
from dotbot.tests.test_calibration_conics import (
    CENTRES,
    FLOOR_TO_CAM,
    RADIUS,
    circle,
    similarity_error,
)

CHUNK_RECORDS = 13


def spin_records(centre, station=0):
    cam = conics.apply(FLOOR_TO_CAM, circle(centre, n=200))
    out = []
    for x, y in cam:
        counts = counts_for_camera_point(x, y, station)
        out.append((station, round(counts.count1), round(counts.count2)))
    return out


def payloads(records, run=7):
    chunks = (len(records) + CHUNK_RECORDS - 1) // CHUNK_RECORDS
    out = []
    for k in range(chunks):
        body = b"".join(
            struct.pack("<BII", *r)
            for r in records[k * CHUNK_RECORDS : (k + 1) * CHUNK_RECORDS]
        )
        out.append(bytes([SPIN_TAG, run, k, chunks]) + body)
    return out


def test_parse_rejects_other_payloads():
    assert parse_spin_payload(b"\xcbhello") is None
    assert parse_spin_payload(bytes([SPIN_TAG, 1, 3, 3])) is None


def test_a_chunk_round_trips():
    records = spin_records((500, 500))[:13]
    chunk = parse_spin_payload(payloads(records)[0])
    assert chunk.run == 7 and chunk.chunk == 0 and chunk.chunks == 1
    assert [(r.lh_index, r.count1, r.count2) for r in chunk.records] == records


def test_copies_and_order_do_not_matter():
    records = spin_records((500, 500))
    events = payloads(records)
    assembler = SpinAssembler()
    for event in list(reversed(events)) + events:
        spin = assembler.add("8c176eb10c21d115", parse_spin_payload(event))
    assert spin.complete
    assert [(r.lh_index, r.count1, r.count2) for r in spin.reads()] == records


def test_spins_from_several_robots_solve_the_station():
    assembler = SpinAssembler()
    for i, centre in enumerate(CENTRES):
        for event in payloads(spin_records(centre)):
            assembler.add(f"robot{i}", parse_spin_payload(event))
    tracks = [t for spin in assembler.spins.values() for t in spin.tracks(RADIUS)]
    sol = conics.solve(tracks)
    rms, S = similarity_error(sol.homography)
    assert rms < 1.0
    assert np.sqrt(abs(np.linalg.det(S[:2, :2]))) == pytest.approx(1.0, abs=0.002)


# --- collect --spin and site init, end to end over a faked swarm -------------

SPIN_BIN = "calibrate-spin-sandbox-dotbot-v3.bin"


def _node(image=SPIN_BIN, status="Bootloader"):
    return SimpleNamespace(
        status=SimpleNamespace(name=status),
        info=SimpleNamespace(image_name=image),
    )


class _SpinFleet:
    """A swarmit client whose robots, once started, send a spin each.

    `events` maps an address to the log payloads its spin sends.
    """

    def __init__(self, nodes, events):
        self.nodes = nodes
        self.events = events
        self.queue: queue.Queue = queue.Queue()
        self.calls: list[tuple[str, list[str] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def refresh_device_info(self, devices=None):
        self.calls.append(("info", devices))

    def status(self):
        return dict(self.nodes)

    def stop(self, devices=None):
        self.calls.append(("stop", devices))
        for addr in devices or self.nodes:
            self.nodes[addr].status.name = "Bootloader"

    def start(self, devices=None):
        self.calls.append(("start", devices))
        for addr in devices or self.nodes:
            self.nodes[addr].status.name = "Running"
            for payload in self.events.get(addr, []):
                self.queue.put({"addr": addr, "data_hex": payload.hex()})

    def watch_log_events(self):
        while True:
            yield self.queue.get()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A project working in site c405, its calibrations under tmp_path."""
    folder = tmp_path / "lab"
    (folder / "sites" / "c405").mkdir(parents=True)
    (folder / "sites" / "c405" / "site.toml").write_text(
        'anchor = "the door corner"\nextent_mm = [2000, 4000]\n'
    )
    (folder / "dotbot.toml").write_text('site = "c405"\n')
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    monkeypatch.setattr(spin_module, "SPIN_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(spin_module, "SPIN_CAPTURE_TIMEOUT", 5.0)
    monkeypatch.delenv("DOTBOT_SITE", raising=False)
    return load_discovered(environ={}, start_dir=folder)


def _fleet(centres=CENTRES):
    addrs = [f"{0xB0 + i:02X}" * 8 for i in range(len(centres))]
    events = {
        a: payloads(spin_records(c), run=i)
        for i, (a, c) in enumerate(zip(addrs, centres))
    }
    return addrs, _SpinFleet({a: _node() for a in addrs}, events)


def _collect(monkeypatch, lab, fleet, *args, devices=None):
    monkeypatch.setattr(swarm_lh2, "_swarmit_client", lambda *a, **k: fleet)
    obj = {"config": lab}
    if devices:
        obj[swarm_lh2.SWARM_OPTIONS] = {"devices": devices}
    return CliRunner().invoke(swarm_lh2.cmd, ["collect", "--spin", *args], obj=obj)


def test_robots_without_the_spin_app_are_refused_with_the_flash_line():
    robots = check_spin_robots(
        {"A": _node(), "B": _node(image="dotbot-sandbox-dotbot-v3.bin")}
    )
    assert robots.ready == ["A"]
    assert "dotbot swarm -d B flash -y calibrate-spin" in robots.refusal()


def test_a_robot_already_in_the_app_is_stopped_before_it_spins(monkeypatch, lab):
    addrs, fleet = _fleet()
    fleet.nodes[addrs[0]].status.name = "Running"
    result = _collect(monkeypatch, lab, fleet)
    assert result.exit_code == 0, result.output
    assert fleet.calls[1] == ("stop", [addrs[0]])


def test_two_spinning_robots_are_refused_without_a_file(monkeypatch, lab):
    addrs, fleet = _fleet(CENTRES[:2])
    result = _collect(monkeypatch, lab, fleet)
    assert result.exit_code != 0
    assert "no calibration written" in result.output
    assert not (lab.project_dir.parent / "home").exists()


def test_the_device_filter_picks_the_robots_that_spin(monkeypatch, lab):
    addrs, fleet = _fleet()
    fleet.nodes["FFFFFFFFFFFFFFFF"] = _node(image="dotbot-sandbox-dotbot-v3.bin")
    result = _collect(
        monkeypatch, lab, fleet, devices=",".join(a.lower() for a in addrs)
    )
    assert result.exit_code == 0, result.output
    assert ("start", sorted(addrs)) in fleet.calls


def test_the_spin_radius_flag_is_recorded_in_the_tracks(monkeypatch, lab):
    _, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet, "--spin-radius", "53.5")
    assert result.exit_code == 0, result.output
    saved = re.search(r"Calibration saved to (\S+)", result.output).group(1)
    assert {
        t.radius_mm for t in lighthouse2.read_calibration_file(Path(saved)).tracks
    } == {53.5}


def test_spin_takes_no_corner_options(monkeypatch, lab):
    _, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet, "--square", "1000")
    assert result.exit_code != 0 and "--spin takes no --square" in result.output
