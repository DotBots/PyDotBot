# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `swarm calibrate-lh2 push` gating and `reframe`.

The swarmit client is faked at its `status()` / `send_lh2_calibration`
surface; none of this is hardware validation.
"""

import tomllib
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from dotbot.calibration import lighthouse2, push
from dotbot.calibration.lighthouse2 import (
    LH2_CALIBRATION_MESSAGE_BYTES,
    message_site,
    read_calibration_file,
)
from dotbot.calibration.push import PushRefused, check_push, gate_push
from dotbot.cli import swarm_lh2
from dotbot.config import load_discovered
from dotbot.tests.lh2_wire_fixture import FIXTURE_ID, FIXTURE_TOML, MESSAGE_HEX

SITES = {
    "c405-arena": (
        'anchor = "arena top-left corner, against the door wall of C405"\n'
        "extent_mm = [3330, 4000]\n"
    ),
    "inria-aio-c": 'anchor = "floor top-left corner"\nextent_mm = [12000, 20000]\n',
}
LAB = None


@pytest.fixture(autouse=True)
def _lab(tmp_path):
    """A project working in c405-arena, with both sites as packs."""
    global LAB
    lab = tmp_path / "lab"
    for name, text in SITES.items():
        (lab / "sites" / name).mkdir(parents=True)
        (lab / "sites" / name / "site.toml").write_text(text)
    (lab / "dotbot.toml").write_text('site = "c405-arena"\n')
    LAB = load_discovered(environ={}, start_dir=lab)


def _info(version=3, site="", calibration_id="", gen=1):
    info = SimpleNamespace(
        info_version=version, lh2_site_name=site, lh2_calibration_id=calibration_id
    )
    return SimpleNamespace(info_gen=gen, info=info)


class _Fleet:
    """A swarmit client whose robots commit whatever they are sent."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.pushed: list[bytes] = []
        self.pushed_to: list[list[str] | None] = []
        self.refreshed: list[list[str] | None] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def refresh_device_info(self, devices=None):
        self.refreshed.append(devices)

    def status(self):
        return dict(self.nodes)

    def send_lh2_calibration(self, payload, devices=None):
        self.pushed.append(payload)
        self.pushed_to.append(devices)
        for addr, node in self.nodes.items():
            if devices is not None and addr not in devices:
                continue
            if addr == "LAGGARD" or node.info is None:
                continue
            node.info.lh2_site_name, node.info.lh2_calibration_id = message_site(
                payload[:LH2_CALIBRATION_MESSAGE_BYTES]
            )


@pytest.fixture
def calibration_file(tmp_path):
    path = tmp_path / "calibration.toml"
    path.write_text(FIXTURE_TOML, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_rejoin_wait(monkeypatch):
    monkeypatch.setattr(push, "PUSH_REJOIN_TIMEOUT", 0.0)


def _push(monkeypatch, fleet, *args):
    monkeypatch.setattr(swarm_lh2, "_swarmit_client", lambda *a, **k: fleet)
    return CliRunner().invoke(
        swarm_lh2.cmd,
        ["push", *args],
        obj={"config": LAB},
    )


def test_the_check_sorts_the_fleet(calibration_file):
    calibration = read_calibration_file(calibration_file)
    check = check_push(
        {
            "A": _info(1),
            "B": _info(site="c405-arena", calibration_id=FIXTURE_ID),
            "C": _info(site="demo-dcoss-2026", calibration_id="00" * 8),
            "D": SimpleNamespace(info_gen=0, info=None),
            "E": SimpleNamespace(info_gen=3, info=None),
            "F": _info(),
        },
        calibration,
    )
    assert check.old_firmware == ["A", "D"]
    assert check.unanswered == ["E"]
    assert check.other_site == {"C": "demo-dcoss-2026"}
    assert check.stale == ["C", "F"]


def test_a_robot_on_device_info_v1_is_refused_with_a_reflash(calibration_file):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"A": _info(1), "B": _info()})
    with pytest.raises(PushRefused, match="Reflash them with `dotbot device"):
        gate_push(fleet, calibration)
    assert fleet.pushed == []


def test_no_robot_answering_is_refused(calibration_file):
    with pytest.raises(PushRefused, match="no robot answered"):
        gate_push(_Fleet({}), read_calibration_file(calibration_file))


def test_push_sends_the_messages_and_lists_the_worklist(monkeypatch, calibration_file):
    fleet = _Fleet(
        {
            "FRESH": _info(),
            "LAGGARD": _info(site="c405-arena", calibration_id="11" * 8),
        }
    )
    result = _push(monkeypatch, fleet, str(calibration_file))

    assert result.exit_code == 0, result.output
    assert fleet.pushed == [b"".join(bytes.fromhex(h) for h in MESSAGE_HEX)]
    # The whole fleet was checked, so it is one broadcast, not a unicast each.
    assert fleet.pushed_to == [None]
    # Device info is read once for the gate and never polled after the push.
    assert fleet.refreshed == [None]
    assert "2 robot(s) hold another id" in result.output
    assert "Still not on 19ed0cdb (1), push again: LAGGARD" in result.output


def test_a_push_checked_for_named_robots_goes_to_exactly_them(calibration_file):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"A": _info(), "B": _info()})
    check = gate_push(fleet, calibration, devices=["a"])
    assert check.addresses == ["A"]
    assert check.send_to == ["A"]


def test_a_robot_not_heard_after_the_push_is_listed(calibration_file):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"GONE": _info()})
    check = gate_push(fleet, calibration)
    fleet.send_lh2_calibration(
        lighthouse2.calibration_payload(calibration), check.send_to
    )
    del fleet.nodes["GONE"]
    assert push.push_worklist(fleet, calibration, check.addresses) == ["GONE"]


def test_push_to_another_site_is_refused_without_site_changed(
    monkeypatch, calibration_file
):
    fleet = _Fleet({"A": _info(site="demo-dcoss-2026", calibration_id="11" * 8)})

    refused = _push(monkeypatch, fleet, str(calibration_file))
    assert refused.exit_code != 0
    assert "A (demo-dcoss-2026)" in refused.output
    assert "--site-changed" in refused.output
    assert fleet.pushed == []

    moved = _push(monkeypatch, fleet, str(calibration_file), "--site-changed")
    assert moved.exit_code == 0, moved.output
    assert len(fleet.pushed) == 1
    assert "Every robot reports 19ed0cdb." in moved.output


@pytest.mark.parametrize("version", [1, 2])
def test_push_refuses_a_robot_on_older_firmware(monkeypatch, calibration_file, version):
    # Version 2 is a net core that drops calibrations sent as 0xA3.
    fleet = _Fleet({"OLD": _info(version)})
    result = _push(monkeypatch, fleet, str(calibration_file))
    assert result.exit_code != 0
    assert "OLD" in result.output
    assert fleet.pushed == []


def test_reframe_writes_a_new_file_in_the_target_site(
    monkeypatch, tmp_path, calibration_file
):
    pytest.importorskip("cv2")
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    result = CliRunner().invoke(
        swarm_lh2.cmd,
        [
            "reframe",
            str(calibration_file),
            "--site",
            "inria-aio-c",
            "--shift",
            "5000,7000",
        ],
        obj={"config": LAB},
    )
    assert result.exit_code == 0, result.output

    written = list((tmp_path / "home" / "calibrations" / "inria-aio-c").glob("*.toml"))
    assert len(written) == 1
    with open(written[0], "rb") as handle:
        data = tomllib.load(handle)
    assert data["site"] == {"name": "inria-aio-c", "anchor": "floor top-left corner"}
    assert data["validity"]["valid_mm"] == [0, 0, 12000, 20000]
    assert data["placement"][0]["points_mm"][0] == [5047.0, 7018.5]
    assert data["metadata"]["id"] != FIXTURE_ID
    assert data["metadata"]["id"] in result.output
    # The fixture's matrices were not solved from its samples, so only
    # station 0, the one the samples cover, is re-solved.
    assert [s["index"] for s in data["station"]] == [0]


def test_reframe_into_an_undeclared_site_is_refused(calibration_file):
    result = CliRunner().invoke(
        swarm_lh2.cmd,
        ["reframe", str(calibration_file), "--site", "nowhere", "--shift", "1,2"],
        obj={"config": LAB},
    )
    assert result.exit_code != 0
    assert "not declared" in result.output


def test_reframe_takes_two_numbers_for_the_shift(calibration_file):
    result = CliRunner().invoke(
        swarm_lh2.cmd,
        ["reframe", str(calibration_file), "--site", "inria-aio-c", "--shift", "1"],
        obj={"config": LAB},
    )
    assert result.exit_code != 0
    assert "x,y" in result.output


def _running(**kw):
    node = _info(**kw)
    node.status = SimpleNamespace(name="Running")
    return node


def test_a_named_robot_in_its_app_is_refused_with_a_stop(calibration_file):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"A": _info(), "B": _running()})
    with pytest.raises(PushRefused, match="dotbot swarm -d B stop"):
        gate_push(fleet, calibration, devices=["A", "B"])
    assert fleet.pushed == []


def test_a_fleet_push_leaves_robots_in_their_app_out(monkeypatch, calibration_file):
    fleet = _Fleet({"A": _info(), "B": _running()})
    result = _push(monkeypatch, fleet, str(calibration_file))
    assert result.exit_code == 0, result.output
    assert "1 robot(s) in their app are left out" in result.output
    assert "dotbot swarm -d B calibrate-lh2 push" in result.output
    assert "Every robot reports" in result.output


def test_a_collect_push_stops_its_robots_first(calibration_file):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"A": _running(), "B": _info()})

    def stop(devices=None):
        for addr in devices:
            fleet.nodes[addr].status.name = "Bootloader"

    fleet.stop = stop
    swarm_lh2._gated_push(fleet, calibration, devices=["A", "B"], stop=True)
    assert fleet.pushed_to == [["A", "B"]]


def test_a_running_robot_left_out_by_the_device_filter_does_not_stop_a_push(
    calibration_file,
):
    calibration = read_calibration_file(calibration_file)
    fleet = _Fleet({"A": _info(), "B": _running()})
    assert gate_push(fleet, calibration, devices=["A"]).send_to == ["A"]


def test_swarm_d_before_calibrate_lh2_limits_the_push(monkeypatch, calibration_file):
    from dotbot.cli import swarm
    from dotbot.tests.test_cli_swarm_inject import _stub_group

    fleet = _Fleet({"A": _info(), "B": _running()})
    monkeypatch.setattr(swarm_lh2, "_swarmit_client", lambda *a, **k: fleet)
    cmd = swarm._with_config_injection(_stub_group())
    with pytest.raises(SystemExit) as exit_:
        cmd.main(
            args=["-d", "a", "calibrate-lh2", "push", str(calibration_file)],
            obj={"config": LAB},
            standalone_mode=False,
        )
    assert exit_.value.code == 0
    assert fleet.pushed_to == [["A"]]
    assert fleet.refreshed == [["A"]]


@pytest.mark.parametrize("args", [["-b", "9600"], ["-v"]])
def test_calibrate_lh2_refuses_swarm_options_it_cannot_honour(calibration_file, args):
    from dotbot.cli import swarm
    from dotbot.tests.test_cli_swarm_inject import _stub_group

    cmd = swarm._with_config_injection(_stub_group())
    with pytest.raises(click.UsageError, match=f"drop {args[0]}"):
        cmd.main(
            args=[*args, "calibrate-lh2", "push", str(calibration_file)],
            obj={"config": LAB},
            standalone_mode=False,
        )


def test_no_server_before_calibrate_lh2_reaches_the_client(
    monkeypatch, calibration_file
):
    from dotbot.cli import swarm
    from dotbot.tests.test_cli_swarm_inject import _stub_group

    seen = {}
    fleet = _Fleet({"A": _info()})

    def client(ctx, conn, swarm_id):
        seen["no_server"] = swarm_lh2._swarm_option(ctx, "no_server")
        return fleet

    monkeypatch.setattr(swarm_lh2, "_swarmit_client", client)
    cmd = swarm._with_config_injection(_stub_group())
    with pytest.raises(SystemExit):
        cmd.main(
            args=["--no-server", "-dA", "calibrate-lh2", "push", str(calibration_file)],
            obj={"config": LAB},
            standalone_mode=False,
        )
    assert seen == {"no_server": True}
    assert fleet.pushed_to == [["A"]]
