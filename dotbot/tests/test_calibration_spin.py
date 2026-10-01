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

from dotbot.calibration import conics, lighthouse2, push
from dotbot.calibration import spin as spin_module
from dotbot.calibration.lighthouse2 import counts_for_camera_point, load_calibration
from dotbot.calibration.spin import (
    SPIN_CHUNK_RECORDS,
    SPIN_TAG,
    SpinAssembler,
    check_spin_robots,
    parse_spin_payload,
)
from dotbot.cli import site_cmd, swarm_lh2
from dotbot.config import load_discovered
from dotbot.robots import robot_geometry
from dotbot.site import Site
from dotbot.site_packs import site_catalog
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
    samples = [s for spin in assembler.spins.values() for s in spin.samples(RADIUS)]
    calibration, _, _ = conics.solve_calibration(samples, Site(name="lab"))
    rms, S = similarity_error(calibration.stations[0].matrix)
    assert rms < 1.0
    assert np.sqrt(abs(np.linalg.det(S[:2, :2]))) == pytest.approx(1.0, abs=0.002)


# Two events 8C176EB10C21D115 sent on the bench with the calibrate-spin app:
# the first of a run's 17 chunks, and its last.
APP_FIRST_CHUNK = bytes.fromhex(
    "cc3100110031750000270f01000035750000260f010000387500001d0f0100003b750000140f"
    "01000045750000070f01000049750000f70e0100004f750000e60e01000051750000d20e0100"
    "0051750000bc0e01000053750000aa0e01000050750000930e0100004b750000800e01000049"
    "750000680e0100"
)
APP_LAST_CHUNK = bytes.fromhex(
    "cc31101100ec740000310f010000f9740000260f010000057500001a0f010000107500000f0f"
    "0100001b750000020f01000024750000f30e01000023750000ea0e01000024750000ec0e0100"
)


def test_the_apps_events_decode():
    first = parse_spin_payload(APP_FIRST_CHUNK)
    assert (first.run, first.chunk, first.chunks) == (0x31, 0, 17)
    assert len(first.records) == SPIN_CHUNK_RECORDS
    r = first.records[0]
    assert (r.lh_index, r.count1, r.count2) == (0, 30001, 69415)
    last = parse_spin_payload(APP_LAST_CHUNK)
    assert (last.chunk, last.chunks, len(last.records)) == (16, 17, 8)


def test_an_event_longer_than_the_app_sends_is_not_a_spin():
    assert parse_spin_payload(APP_FIRST_CHUNK + APP_FIRST_CHUNK[4:13]) is None


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
        """A snapshot; a robot seen stopping is in its bootloader by the next."""
        out = {
            addr: SimpleNamespace(
                status=SimpleNamespace(name=node.status.name),
                info=node.info,
                info_gen=getattr(node, "info_gen", 1),
            )
            for addr, node in self.nodes.items()
        }
        for node in self.nodes.values():
            if node.status.name == "Stopping":
                node.status.name = "Bootloader"
        return out

    def stop(self, devices=None):
        self.calls.append(("stop", devices))
        for addr in devices or self.nodes:
            self.nodes[addr].status.name = "Stopping"

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
    monkeypatch.setattr(push, "STOP_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(push, "PUSH_REJOIN_TIMEOUT", 0.0)
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


def test_spins_end_to_end_into_a_self_defined_site(monkeypatch, lab):
    addrs, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet)
    assert result.exit_code == 0, result.output
    assert f"spin radius {RADIUS:g} mm" in result.output
    assert f"{len(CENTRES)} of {len(CENTRES)} circles kept" in result.output
    assert "warning: 6 circles" in result.output
    # started once, stopped after, so a push reaches them
    assert [c for c, _ in fleet.calls] == ["info", "start", "stop"]
    free_id = re.search(r"--from-calibration (\w+)", result.output).group(1)

    result = CliRunner().invoke(
        site_cmd.cmd,
        ["init", "spun", "--from-calibration", free_id, "--size", "3000x4000"],
        obj={"config": lab},
    )
    assert result.exit_code == 0, result.output
    pack = lab.project_dir / "sites" / "spun"
    assert (pack / "site.toml").is_file()
    site = site_catalog(lab)["spun"].site()
    assert site.extent_mm == (3000, 4000)
    placed_id = re.search(
        r"push (\w+) --site spun --site-changed", result.output
    ).group(1)

    # what `run controller --site spun --lh2-calibration <id>` loads
    calibration = load_calibration(placed_id, site=site)
    cam = conics.apply(FLOOR_TO_CAM, np.array(CENTRES, dtype=float))
    placed = conics.apply(calibration.stations[0].matrix, cam)
    truth = np.array(CENTRES, dtype=float)
    d_placed = np.linalg.norm(placed[:, None] - placed[None], axis=2)
    d_truth = np.linalg.norm(truth[:, None] - truth[None], axis=2)
    assert np.max(np.abs(d_placed - d_truth)) < 1.0
    field = site.field
    reach = robot_geometry().axle_reach_mm
    assert np.all(placed[:, 0] >= field.x + reach - 1) and np.all(
        placed[:, 0] <= field.x + field.w - reach + 1
    )
    assert np.all(placed[:, 1] >= field.y + reach - 1) and np.all(
        placed[:, 1] <= field.y + field.h - reach + 1
    )
    assert (field.x * 2 + field.w, field.y * 2 + field.h) == pytest.approx(
        (3000, 4000), abs=1
    )


def test_site_init_refuses_an_existing_name(monkeypatch, lab):
    _, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet)
    free_id = re.search(r"--from-calibration (\w+)", result.output).group(1)
    result = CliRunner().invoke(
        site_cmd.cmd,
        ["init", "c405", "--from-calibration", free_id],
        obj={"config": lab},
    )
    assert result.exit_code != 0 and "already exists" in result.output


def test_site_init_refuses_a_corner_calibration(lab, tmp_path):
    from dotbot.tests.lh2_wire_fixture import FIXTURE_TOML

    path = tmp_path / "corner.toml"
    path.write_text(FIXTURE_TOML, encoding="utf-8")
    result = CliRunner().invoke(
        site_cmd.cmd,
        ["init", "spun", "--from-calibration", str(path)],
        obj={"config": lab},
    )
    assert result.exit_code != 0 and "not a free-mode spin calibration" in result.output


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


def test_a_spin_push_waits_for_the_robots_to_leave_the_app(monkeypatch, lab):
    _, fleet = _fleet()
    sent = []
    fleet.send_lh2_calibration = lambda payload, devices=None: sent.append(devices)
    for node in fleet.nodes.values():
        node.info.info_version = 3
        node.info.lh2_site_name = "c405"
        node.info.lh2_calibration_id = ""
        node.info_gen = 1
    result = _collect(monkeypatch, lab, fleet, "--push")
    assert result.exit_code == 0, result.output
    assert sent == [sorted(fleet.nodes)]


class _FailingEvents(_SpinFleet):
    def watch_log_events(self):
        raise ConnectionError("broker said no")
        yield  # pragma: no cover


def test_losing_the_log_events_stops_the_robots_and_says_why(monkeypatch, lab):
    addrs, fleet = _fleet()
    fleet.__class__ = _FailingEvents
    result = _collect(monkeypatch, lab, fleet)
    assert result.exit_code != 0
    assert "lost the robots' log events: broker said no" in result.output
    assert fleet.calls[-1] == ("stop", sorted(addrs))


def test_a_failed_start_still_stops_the_robots(lab):
    addrs, fleet = _fleet()

    def start(devices=None):
        fleet.calls.append(("start", devices))
        raise RuntimeError("gateway gone")

    fleet.start = start
    robots = check_spin_robots(fleet.status())
    with pytest.raises(RuntimeError, match="gateway gone"):
        spin_module.capture_spins(fleet, robots, echo=lambda _: None)
    assert fleet.calls[-1] == ("stop", sorted(addrs))


def test_a_lost_chunk_ends_the_wait_once_the_others_stop_coming(monkeypatch, lab):
    addrs, fleet = _fleet()
    fleet.events[addrs[0]] = fleet.events[addrs[0]][1:]
    monkeypatch.setattr(spin_module, "SPIN_QUIET_TIMEOUT", 0.2)
    robots = check_spin_robots(fleet.status())
    spins = spin_module.capture_spins(fleet, robots, timeout=30, echo=lambda _: None)
    assert not spins[addrs[0]].complete
    assert all(spins[a].complete for a in addrs[1:])


def test_site_init_refuses_a_calibration_it_already_placed(monkeypatch, lab):
    _, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet)
    free_id = re.search(r"--from-calibration (\w+)", result.output).group(1)
    result = CliRunner().invoke(
        site_cmd.cmd,
        ["init", "spun", "--from-calibration", free_id],
        obj={"config": lab},
    )
    placed_id = re.search(r"push (\w+) --site spun", result.output).group(1)
    result = CliRunner().invoke(
        site_cmd.cmd,
        ["init", "again", "--from-calibration", placed_id],
        obj={"config": lab},
    )
    assert result.exit_code != 0 and "not a free-mode spin calibration" in result.output


def test_site_init_force_replaces_the_site(monkeypatch, lab):
    _, fleet = _fleet()
    result = _collect(monkeypatch, lab, fleet)
    free_id = re.search(r"--from-calibration (\w+)", result.output).group(1)
    for size in ("3000x4000", "5000x5000"):
        result = CliRunner().invoke(
            site_cmd.cmd,
            ["init", "spun", "--from-calibration", free_id, "--size", size, "--force"],
            obj={"config": lab},
        )
        assert result.exit_code == 0, result.output
    assert site_catalog(lab)["spun"].site().extent_mm == (5000, 5000)
