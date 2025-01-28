"""Test module for the joystick main function."""

from unittest.mock import patch

from click.testing import CliRunner

from dotbot.joystick import main

MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  DotBot joystick controller.

Options:
  -j, --joystick INTEGER          Index of the joystick to use. Defaults to 0
  -h, --hostname TEXT             Hostname of the controller. Defaults to
                                  'localhost'
  -p, --port INTEGER              HTTP port. Defaults to '8000'
  -s, --https                     Use HTTPS protocol instead of HTTP
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -a, --application [dotbot|sailbot]
                                  Application to control. Defaults to sailbot
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --help                          Show this message and exit.
"""


def test_joystick_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


@patch("dotbot.version")
@patch("dotbot.joystick.JoystickController.start")
def test_main_no_joystick(start, version):
    version.return_value = "test"
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 1
    assert "Error: No joystick connected." in result.output
    start.assert_not_called()
