"""Test module for the main function."""

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest
import serial
from click.testing import CliRunner

from dotbot.controller_app import main

MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  DotBotController, universal SailBot and DotBot controller.

Options:
  -a, --adapter [serial|edge|cloud|dotbot-simulator|sailbot-simulator]
                                  Controller interface adapter. Defaults to
                                  serial
  -p, --port TEXT                 Serial port used by 'serial' and 'edge'
                                  adapters. Defaults to '/dev/ttyACM0'
  -b, --baudrate INTEGER          Serial baudrate used by 'serial' and 'edge'
                                  adapters. Defaults to 1000000
  -H, --mqtt-host TEXT            MQTT host used by cloud adapter. Default:
                                  localhost.
  -P, --mqtt-port INTEGER         MQTT port used by cloud adapter. Default:
                                  1883.
  -T, --mqtt-use_tls              Use TLS with MQTT (for cloud adapter).
  -g, --gw-address TEXT           Gateway address in hex. Defaults to
                                  0000000000000000
  -s, --network-id TEXT           Network ID in hex. Defaults to 0000
  -c, --controller-http-port INTEGER
                                  Controller HTTP port of the REST API. Defaults
                                  to '8000'
  -w, --webbrowser                Open a web browser automatically
  -v, --verbose                   Run in verbose mode (all payloads received are
                                  printed in terminal)
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --log-output PATH               Filename where logs are redirected
  --config-path FILE              Path to a .toml configuration file.
  -m, --map-size TEXT             Map size in mm. Defaults to '2000x2000'
  --help                          Show this message and exit.
"""


@pytest.mark.skipif(sys.platform != "linux", reason="Serial port is different")
def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.version")
@patch("dotbot.controller.Controller.run")
def test_main(run, version, _):
    version.return_value = "test"
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: test)." in result.output
    run.assert_called_once()

    version.side_effect = PackageNotFoundError
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: unknown)." in result.output


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller.Controller.run")
def test_main_interrupts(run, _):
    runner = CliRunner()
    run.side_effect = KeyboardInterrupt
    result = runner.invoke(main)
    assert result.exit_code == 0

    runner = CliRunner()
    run.side_effect = SystemExit
    result = runner.invoke(main)
    assert result.exit_code == 0

    run.side_effect = serial.serialutil.SerialException("serial test error")
    result = runner.invoke(main)
    assert result.exit_code != 0
    assert "Serial error: serial test error" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller_app.Controller")
def test_main_with_config(controller, _, tmp_path):
    log_file = tmp_path / "logfile.log"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f"""
adapter = "serial"
network_id = "AA26"
log_level = "debug"
log_output = "{log_file}"
"""
    )

    runner = CliRunner()
    runner.invoke(main, ["--config-path", config_file.as_posix()])
    assert controller.call_args.args[0].network_id == "AA26"
    assert controller.call_args.args[0].adapter == "serial"
    assert controller.call_args.args[0].log_level == "debug"
    assert controller.call_args.args[0].log_output == str(log_file)
