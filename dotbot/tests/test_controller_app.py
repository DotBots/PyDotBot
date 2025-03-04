"""Test module for the main function."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import serial
from click.testing import CliRunner

from dotbot.controller_app import main
from dotbot.serial_interface import get_default_port

MAIN_HELP_EXPECTED = f"""Usage: main [OPTIONS]

  DotBotController, universal SailBot and DotBot controller.

Options:
  -p, --port TEXT                 Virtual com port. Defaults to '{get_default_port()}'
  -b, --baudrate INTEGER          Serial baudrate. Defaults to 1000000
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -g, --gw-address TEXT           Gateway address in hex. Defaults to
                                  0000000000000000
  -s, --swarm-id TEXT             Swarm ID in hex. Defaults to 0000
  -c, --controller-port INTEGER   Controller port. Defaults to '8000'
  -w, --webbrowser                Open a web browser automatically
  -v, --verbose                   Run in verbose mode (all payloads received are
                                  printed in terminal)
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --log-output PATH               Filename where logs are redirected
  --handshake                     Perform a basic handshake with the gateway
                                  board on startup
  --edge                          Connect to the edge gateway via MQTT instead
                                  of local serial connection
  --help                          Show this message and exit.
"""


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.controller.QrkeyController")
@patch("dotbot.version")
@patch("dotbot.controller.Controller.run")
def test_main(run, version, _, __):
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


@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.controller.QrkeyController")
@patch("dotbot.controller.Controller.run")
def test_main_interrupts(run, _, __):
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
