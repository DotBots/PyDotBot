# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot run gateway` — the CLI surface, not the live bridge.

The bridge itself (`_run_gateway`) needs a real serial gateway, so it's
mocked here; we check flag parsing and that the command forwards
`--port` / `--mqtt-url` correctly.
"""

from unittest.mock import patch

from click.testing import CliRunner

from dotbot.cli.gateway import cmd as gateway_cmd
from dotbot.cli.main import cli


def _write_config(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


def _bridged(run):
    """The port, broker URL and print flag `_run_gateway` was called with."""
    run.assert_called_once()
    return tuple(run.call_args.args[:3])


def test_gateway_help_mentions_print_and_broker():
    result = CliRunner().invoke(gateway_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--mqtt-url" in result.output
    assert "--no-print" in result.output


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_forwards_port_mqtt_url_and_print(run):
    result = CliRunner().invoke(
        gateway_cmd,
        ["--port", "/dev/ttyACM0", "--mqtt-url", "mqtts://argus:8883"],
    )
    assert result.exit_code == 0, result.output
    # print defaults to True.
    assert _bridged(run) == ("/dev/ttyACM0", "mqtts://argus:8883", True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_no_mqtt_defaults_print_on(run):
    result = CliRunner().invoke(gateway_cmd, ["--port", "/dev/ttyACM0"])
    assert result.exit_code == 0, result.output
    assert _bridged(run) == ("/dev/ttyACM0", None, True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_no_print_flag(run):
    result = CliRunner().invoke(gateway_cmd, ["--port", "/dev/ttyACM0", "--no-print"])
    assert result.exit_code == 0, result.output
    assert _bridged(run) == ("/dev/ttyACM0", None, False)


# --- the site's broker (through the root group) ------------------------------

_LAB = 'site = "lab"\n[sites.lab.connection]\nconn = "mqtts://broker:8883"\n'


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_falls_back_to_the_sites_broker(run, tmp_path):
    """No --mqtt-url -> the active site's broker reaches the bridge, named in
    the banner."""
    cfg = _write_config(tmp_path, _LAB)
    result = CliRunner().invoke(cli, ["-c", str(cfg), "run", "gateway"])
    assert result.exit_code == 0, result.output
    assert _bridged(run) == (None, "mqtts://broker:8883", True)
    assert "site lab (dotbot.toml), conn mqtts://broker:8883 (site lab)" in (
        result.output
    )


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_cli_mqtt_url_beats_the_site(run, tmp_path):
    """An explicit --mqtt-url wins over the site's conn."""
    cfg = _write_config(tmp_path, _LAB)
    result = CliRunner().invoke(
        cli,
        ["-c", str(cfg), "run", "gateway", "--mqtt-url", "mqtts://override:8883"],
    )
    assert result.exit_code == 0, result.output
    assert _bridged(run) == (None, "mqtts://override:8883", True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_non_mqtt_conn_stays_print_only(run, tmp_path):
    """A serial/simulator conn is not a broker -> mqtt_url stays None."""
    cfg = _write_config(tmp_path, 'conn = "simulator"\n')
    result = CliRunner().invoke(cli, ["-c", str(cfg), "run", "gateway"])
    assert result.exit_code == 0, result.output
    assert _bridged(run) == (None, None, True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_withholds_credentials_from_an_unapproved_broker(
    run, tmp_path, monkeypatch
):
    from dotbot import site_packs

    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    monkeypatch.setattr(site_packs, "USER_SITES_DIR", tmp_path / "user-sites")
    pack = tmp_path / "user-sites" / "lab"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text('[connection]\nconn = "mqtts://broker:8883"\n')
    cfg = _write_config(tmp_path, 'site = "lab"\n')
    result = CliRunner().invoke(cli, ["-c", str(cfg), "run", "gateway"])
    assert result.exit_code == 0, result.output
    assert run.call_args.args[3].username is None
    assert "site lab's broker was never approved" in result.output


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_sends_credentials_to_a_broker_you_named(run, monkeypatch):
    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    result = CliRunner().invoke(gateway_cmd, ["--mqtt-url", "mqtts://argus:8883"])
    assert result.exit_code == 0, result.output
    credentials = run.call_args.args[3]
    assert (credentials.username, credentials.password) == ("me", "secret")
