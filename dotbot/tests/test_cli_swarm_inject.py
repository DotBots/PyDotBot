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
    for var in ("DOTBOT_CONN", "DOTBOT_SWARM_ID"):
        monkeypatch.delenv(var, raising=False)


def _obj(**kw):
    return {"config": DotbotConfig(**kw)}


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
        ["-vs", "A001", "status"],
        ["-vsA001", "status"],
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
    from dotbot.firmware.fetch import DOTBOT_FIRMWARE_VERSION

    fw = tmp_path / f"dotbot-firmware-{DOTBOT_FIRMWARE_VERSION}"
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


# --- the active site's connection, the banner and the credentials ------------


def _project_obj(folder, **kw):
    """A project in `folder` working in site arena, a pack beside it whose
    broker is argus; `kw` are top-level keys of its dotbot.toml."""
    from dotbot.config import load_discovered

    pack = folder / "sites" / "arena"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "site.toml").write_text(
        '[connection]\nconn = "mqtts://argus.example:8883"\n'
    )
    lines = ['site = "arena"', *(f'{key} = "{value}"' for key, value in kw.items())]
    (folder / "dotbot.toml").write_text("\n".join(lines) + "\n")
    return {"config": load_discovered(environ={}, start_dir=folder)}


def test_injects_the_sites_broker_under_your_swarm_id(tmp_path):
    out = inject_config(["status"], _project_obj(tmp_path, swarm_id="A001"))
    assert out == [
        "--conn",
        "mqtts://argus.example:8883",
        "--swarm-id",
        "A001",
        "status",
    ]


def _settle(args, obj, monkeypatch, capsys):
    ctx = click.Context(click.Command("swarm"), obj=obj)
    swarm._settle_connection(ctx, args, _stub_group())
    return capsys.readouterr().err


def _unapproved_obj(tmp_path, monkeypatch, **kw):
    """The same site, from a pack in ~/.dotbot/sites that was never approved."""
    from dotbot import site_packs
    from dotbot.config import load_discovered

    monkeypatch.setattr(site_packs, "USER_SITES_DIR", tmp_path / "home-sites")
    pack = tmp_path / "home-sites" / "arena"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        '[connection]\nconn = "mqtts://argus.example:8883"\n'
    )
    lines = ['site = "arena"', *(f'{key} = "{value}"' for key, value in kw.items())]
    (tmp_path / "dotbot.toml").write_text("\n".join(lines) + "\n")
    return {"config": load_discovered(environ={}, start_dir=tmp_path)}


def test_credentials_withheld_from_an_unapproved_broker_leave_the_env(
    monkeypatch, capsys, tmp_path
):
    import os

    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    obj = _unapproved_obj(tmp_path, monkeypatch, swarm_id="A001")
    err = _settle(["status"], obj, monkeypatch, capsys)
    assert "site arena's broker was never approved" in err
    assert "DOTBOT_MQTT_USER" not in os.environ
    assert "DOTBOT_MQTT_PASS" not in os.environ


@pytest.mark.parametrize(
    "args",
    [["status"], ["--conn", "mqtts://argus.example:8883", "status"]],
    ids=["a pack beside your project", "--conn"],
)
def test_credentials_kept_for_a_trusted_or_named_broker(
    monkeypatch, capsys, tmp_path, args
):
    import os

    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    err = _settle(args, _project_obj(tmp_path, swarm_id="A001"), monkeypatch, capsys)
    assert "warning" not in err
    assert os.environ["DOTBOT_MQTT_USER"] == "me"


def test_a_saved_login_for_the_broker_reaches_swarmit_through_the_env(
    monkeypatch, capsys, tmp_path
):
    import os

    from dotbot.config import Login

    monkeypatch.delenv("DOTBOT_MQTT_USER", raising=False)
    monkeypatch.delenv("DOTBOT_MQTT_PASS", raising=False)
    obj = _unapproved_obj(tmp_path, monkeypatch, swarm_id="A001")
    obj["config"].login["argus.example"] = Login(user="me", password="s3cret")
    err = _settle(["status"], obj, monkeypatch, capsys)
    assert "warning" not in err
    assert (os.environ["DOTBOT_MQTT_USER"], os.environ["DOTBOT_MQTT_PASS"]) == (
        "me",
        "s3cret",
    )
    obj["config"].login.clear()
    obj["config"].login["other.example"] = Login(user="me", password="s3cret")
    _settle(["status"], obj, monkeypatch, capsys)
    assert "DOTBOT_MQTT_USER" not in os.environ


def test_a_conn_inside_a_short_cluster_is_the_one_judged(monkeypatch, capsys):
    import os

    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    args = ["-vn", "mqtt://remote.example:1883", "status"]
    obj = _obj(conn="mqtts://mine.example:8883", swarm_id="A001")
    assert inject_config(args, obj) == ["--swarm-id", "A001", *args]
    err = _settle(args, obj, monkeypatch, capsys)
    assert "plain mqtt://" in err
    assert "DOTBOT_MQTT_USER" not in os.environ


def test_the_banner_prints_for_commands_that_act_on_robots(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.delenv("DOTBOT_MQTT_USER", raising=False)
    monkeypatch.chdir(tmp_path)
    obj = _project_obj(tmp_path, swarm_id="A001")
    assert _settle(["status"], obj, monkeypatch, capsys) == ""
    err = _settle(["flash", "app.bin"], obj, monkeypatch, capsys)
    assert err.strip() == (
        "site arena (dotbot.toml), conn mqtts://argus.example:8883 "
        "(site arena), swarm A001 (dotbot.toml)"
    )
