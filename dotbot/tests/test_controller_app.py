"""Test module for the main function."""

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest
import serial
from click.testing import CliRunner

from dotbot.controller_app import main


def test_main_help():
    """Help advertises the new `--conn` / `--swarm-id` surface and no
    longer the dropped `--adapter` / `-H/-P/-T` flags."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--conn" in result.output
    assert "--swarm-id" in result.output
    assert "--sailbot" in result.output
    # Dropped flags must be gone.
    assert "--adapter" not in result.output
    assert "--mqtt-host" not in result.output
    assert "--network-id" not in result.output


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.version")
@patch("dotbot.controller.Controller.run")
def test_main(run, version, _):
    version.return_value = "test"
    runner = CliRunner()
    # A connection is now required; `simulator` needs no hardware/swarm-id.
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: test)." in result.output
    run.assert_called_once()

    version.side_effect = PackageNotFoundError
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: unknown)." in result.output


def test_main_without_conn_errors():
    """No `--conn` → a clear error listing the connection forms."""
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0
    assert "mqtts://" in result.output and "simulator" in result.output


def test_main_mqtt_without_swarm_id_errors():
    runner = CliRunner()
    result = runner.invoke(main, ["--conn", "mqtts://argus:8883"])
    assert result.exit_code != 0
    assert "swarm-id" in result.output


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller.Controller.run")
def test_main_interrupts(run, _):
    runner = CliRunner()
    run.side_effect = KeyboardInterrupt
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0

    runner = CliRunner()
    run.side_effect = SystemExit
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0

    run.side_effect = serial.serialutil.SerialException("serial test error")
    result = runner.invoke(main, ["--conn", "/dev/ttyACM0"])
    assert result.exit_code != 0
    assert "Serial error: serial test error" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller_app.Controller")
def test_main_with_config(controller, _, tmp_path):
    """Config file carries `conn` + `swarm_id` (new keys); CLI absent."""
    log_file = tmp_path / "logfile.log"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f"""
conn = "mqtts://argus:8883"
swarm_id = "AA26"
log_level = "debug"
log_output = "{log_file}"
"""
    )

    runner = CliRunner()
    runner.invoke(main, ["--config-path", config_file.as_posix()])
    settings = controller.call_args.args[0]
    assert settings.network_id == "AA26"
    assert settings.adapter == "cloud"
    assert settings.mqtt_host == "argus"
    assert settings.log_level == "debug"
    assert settings.log_output == str(log_file)


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller_app.Controller")
def test_main_warns_on_legacy_config_keys(controller, _, tmp_path):
    """A config file with old transport keys (adapter/mqtt_host/...) gets a
    warning, and those keys are dropped (conn/swarm_id drive it)."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text(
        'conn = "simulator"\nadapter = "serial"\nmqtt_host = "stale"\n'
    )
    runner = CliRunner()
    result = runner.invoke(main, ["--config-path", config_file.as_posix()])
    assert "legacy config key" in result.output
    settings = controller.call_args.args[0]
    # conn=simulator wins; the stale adapter/mqtt_host are ignored.
    assert settings.adapter == "dotbot-simulator"
    assert settings.mqtt_host != "stale"
