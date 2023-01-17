"""Test module for the main function."""

from unittest.mock import patch
from importlib.metadata import PackageNotFoundError

import serial
from click.testing import CliRunner

from dotbot.main import main


MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  BotController, universal SailBot and DotBot controller.

Options:
  -t, --type [joystick|keyboard]  Type of your controller. Defaults to
                                  'keyboard'
  -p, --port TEXT                 Linux users: path to port in '/dev' folder ;
                                  Windows users: COM port. Defaults to
                                  '/dev/ttyACM0'
  -b, --baudrate INTEGER          Serial baudrate. Defaults to 1000000
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -g, --gw-address TEXT           Gateway address in hex. Defaults to
                                  0000000000000000
  -s, --swarm-id TEXT             Swarm ID in hex. Defaults to 0000
  -w, --webbrowser                Open a web browser automatically
  -v, --verbose                   Run in verbose mode (all payloads received are
                                  printed in terminal)
  --help                          Show this message and exit.
"""


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


def test_main_invalid_controller_type():
    runner = CliRunner()
    result = runner.invoke(main, ["--type", "invalid"])
    assert result.exit_code != 0


@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.version")
@patch("dotbot.controller.ControllerBase.run")
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


@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.controller.ControllerBase.run")
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
