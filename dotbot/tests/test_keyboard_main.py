"""Test module for the keyboard main function."""

from unittest.mock import patch

from click.testing import CliRunner

from dotbot.keyboard import main

MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  DotBot keyboard controller.

Options:
  -h, --hostname TEXT             Hostname of the controller. Defaults to
                                  'localhost'
  -p, --port INTEGER              HTTP port. Defaults to '8000'
  -s, --https                     Use HTTPS protocol instead of HTTP
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -a, --application [dotbot|sailbot]
                                  Application to control. Defaults to dotbot
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --help                          Show this message and exit.
"""


def test_keyboard_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


@patch("dotbot.version")
@patch("dotbot.keyboard.KeyboardController.start")
def test_main(start, version):
    version.return_value = "test"
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Welcome to the DotBots keyboard interface (version: test)." in result.output
    start.assert_called_once()
