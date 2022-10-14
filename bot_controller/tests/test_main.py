"""Test module for the main function."""

from unittest.mock import patch
from importlib.metadata import PackageNotFoundError

import serial
from click.testing import CliRunner

from bot_controller.main import main


MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  BotController, universal SailBot and DotBot controller.

Options:
  -t, --type [joystick|keyboard]  Type of your controller. Defaults to
                                  'keyboard'
  -p, --port TEXT                 Linux users: path to port in '/dev' folder ;
                                  Windows users: COM port. Defaults to
                                  '/dev/ttyACM0'
  -b, --baudrate INTEGER          Serial baudrate. Defaults to 1000000
  -d, --dotbot-address TEXT       Address of the DotBot to control. Defaults to
                                  0xFFFFFFFFFFFFFFFF
  -g, --gw-address TEXT           Gateway address. Defaults to
                                  0x0000000000000000
  -s, --swarm-id TEXT             Swarm ID. Defaults to 0x0000
  -S, --scan                      Run the dotbot-controller in scan mode
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


@patch("bot_controller.serial_interface.serial.Serial.open")
@patch("bot_controller.main.version")
@patch("bot_controller.keyboard.KeyboardController.start")
def test_main(start, version, _):
    version.return_value = "test"
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert (
        "Welcome to BotController (version: test), the universal SailBot and DotBot controller."
        in result.output
    )
    start.assert_called_once()

    version.side_effect = PackageNotFoundError
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert (
        "Welcome to BotController (version: unknown), the universal SailBot and DotBot controller."
        in result.output
    )


@patch("bot_controller.serial_interface.serial.Serial.open")
@patch("bot_controller.keyboard.KeyboardController.start")
def test_main_interrupts(start, _):
    runner = CliRunner()
    start.side_effect = KeyboardInterrupt
    result = runner.invoke(main)
    assert result.exit_code != 0
    assert "Exiting" in result.output

    start.side_effect = serial.serialutil.SerialException("serial test error")
    result = runner.invoke(main)
    assert result.exit_code != 0
    assert "Serial error: serial test error" in result.output
