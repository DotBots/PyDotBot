# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` config -> swarmit flag injection.

Tests the pure helper (`_swarm_inject`) so swarmit itself is never imported -
its protocol registry collides with PyDotBot's in a shared test process (the
full `dotbot swarm` invocation is covered by the subprocess test in
`test_cli_dispatcher`).
"""

import click
import pytest

from dotbot.cli import _swarm_inject, swarm
from dotbot.config import DotbotConfig


def _stub_group():
    """A Click group shaped like swarmit's: its group options and subcommands."""

    @click.group()
    @click.option("-c", "--config-path")
    @click.option("-n", "--conn", "--connection")
    @click.option("-s", "--swarm-id")
    @click.option("-b", "--baudrate")
    @click.option("-d", "--devices")
    @click.option("-v", "--verbose", is_flag=True)
    @click.option("--no-server", is_flag=True)
    def group(**_):
        pass

    @group.command()
    @click.option("-y", "--yes", is_flag=True)
    @click.option("-s", "--start", is_flag=True)
    @click.option("-t", "--ota-timeout")
    @click.argument("firmware")
    def flash(**_):
        pass

    @group.command()
    def status():
        pass

    return group


def inject_config(args, obj):
    return _swarm_inject.inject_config(args, obj, _stub_group())


@pytest.fixture(autouse=True)
def _clean_conn_env(monkeypatch):
    # The resolver also reads env; clear the swarm/conn vars for determinism.
    for var in (
        "DOTBOT_CONN",
        "DOTBOT_SWARM_CONN",
        "DOTBOT_SWARM_ID",
        "DOTBOT_SWARM_SWARM_ID",
    ):
        monkeypatch.delenv(var, raising=False)


def _obj(**kw):
    return {"config": DotbotConfig(**kw), "deployment": None}


def test_injects_conn_and_swarm_id():
    out = inject_config(["status"], _obj(conn="mqtts://b:8883", swarm_id="1234"))
    assert out == ["--conn", "mqtts://b:8883", "--swarm-id", "1234", "status"]


def test_swarm_id_only():
    out = inject_config(["status"], _obj(swarm_id="1234"))
    assert out == ["--swarm-id", "1234", "status"]


def test_explicit_conn_flag_wins():
    out = inject_config(
        ["--conn", "mqtts://x:1", "status"],
        _obj(conn="mqtts://b:8883", swarm_id="1234"),
    )
    # conn not re-injected; swarm_id still filled in.
    assert out.count("--conn") == 1
    assert out[-3:] == ["--conn", "mqtts://x:1", "status"]
    assert "--swarm-id" in out and "1234" in out


def test_short_conn_flag_wins():
    out = inject_config(["-n", "simulator", "status"], _obj(conn="mqtts://b:8883"))
    assert "mqtts://b:8883" not in out


def test_config_path_flag_skips_injection():
    out = inject_config(
        ["-c", "other.toml", "status"],
        _obj(conn="mqtts://b:8883", swarm_id="1234"),
    )
    assert out == ["-c", "other.toml", "status"]


def test_help_skips_injection():
    assert inject_config(["--help"], _obj(conn="mqtts://b:8883")) == ["--help"]
    assert inject_config(["status", "-h"], _obj(conn="mqtts://b:8883")) == [
        "status",
        "-h",
    ]


def test_no_config_is_noop():
    assert inject_config(["status"], None) == ["status"]
    assert inject_config(["status"], _obj()) == ["status"]


@pytest.mark.parametrize(
    "args",
    [
        ["flash", "x.bin", "-y", "-s"],
        ["-d", "ABC", "flash", "-y", "-s", "x.bin"],
        ["-d", "ABC", "flash", "--swarm-id", "x.bin"],
        ["-vd", "ABC", "flash", "x.bin", "-ys"],
    ],
)
def test_subcommand_flags_do_not_block_swarm_id(args):
    assert inject_config(args, _obj(swarm_id="1234")) == ["--swarm-id", "1234", *args]


@pytest.mark.parametrize(
    "args",
    [
        ["-s", "A001", "flash", "x.bin", "-ys"],
        ["--swarm-id", "A001", "flash", "x.bin", "-ys"],
        ["--swarm-id=A001", "-d", "ABC", "flash", "x.bin", "-y", "-s"],
        ["-sA001", "status"],
    ],
)
def test_explicit_group_swarm_id_wins(args):
    assert inject_config(args, _obj(swarm_id="1234")) == args


def test_group_value_matching_subcommand_name_is_skipped():
    group = _stub_group()
    assert _swarm_inject.subcommand_index(["-d", "flash", "status"], group) == 2
    assert _swarm_inject.subcommand_index(["-v"], group) is None


def test_flash_name_resolved_after_group_options(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    fw = tmp_path / "dotbot-firmware-1.22.0"
    fw.mkdir()
    (fw / "spin-sandbox-dotbot-v3.bin").write_bytes(b"\x00")
    seen = []
    monkeypatch.setattr(swarm, "_run_swarmit", lambda _group, args: seen.append(args))

    cmd = swarm._with_config_injection(_stub_group())
    cmd.main(
        args=["-d", "ABC", "flash", "spin", "-ys"],
        obj=_obj(swarm_id="1234"),
        standalone_mode=False,
    )

    bin_path = str(fw / "spin-sandbox-dotbot-v3.bin")
    assert seen == [["--swarm-id", "1234", "-d", "ABC", "flash", bin_path, "-ys"]]
