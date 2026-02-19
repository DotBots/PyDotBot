"""Test module for the qrkey client main function."""

import asyncio
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dotbot.qrkey import QrKeyClientSettings
from dotbot.qrkey_app import main

MAIN_HELP_EXPECTED = """Usage: main [OPTIONS]

  DotBot QrKey client.

Options:
  -H, --http-host INTEGER         Controller HTTP host of the REST API. Defaults
                                  to 'localhost'
  -P, --http-port INTEGER         Controller HTTP port of the REST API. Defaults
                                  to '8000'
  -w, --webbrowser                Open a web browser automatically
  -v, --verbose                   Run in verbose mode (all payloads received are
                                  printed in terminal)
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --log-output PATH               Filename where logs are redirected
  --config-path FILE              Path to a .toml configuration file.
  --help                          Show this message and exit.
"""


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.output == MAIN_HELP_EXPECTED


@pytest.fixture
def cli_mock():
    async def fake_cli(settings: QrKeyClientSettings):
        asyncio.sleep(0.1)  # simulate some async work
        return None

    with patch("dotbot.qrkey_app.cli") as cli:
        cli.return_value = fake_cli
        yield cli


def test_main(cli_mock):
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "Welcome to the DotBot QrKey client" in result.output
    cli_mock.assert_called_once()
    args, _ = cli_mock.call_args
    assert isinstance(args[0], QrKeyClientSettings)
    assert args[0].http_host == "localhost"
    assert args[0].http_port == 8000
    assert args[0].webbrowser is False
    assert args[0].verbose is False


def test_main_interrupts(cli_mock):
    runner = CliRunner()
    cli_mock.side_effect = KeyboardInterrupt
    result = runner.invoke(main, [])
    assert result.exit_code == 0

    cli_mock.side_effect = SystemExit
    result = runner.invoke(main, [])
    assert result.exit_code == 0


def test_main_config_path(cli_mock, tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
http_host = "testhost"
http_port = 1234
webbrowser = true
verbose = true
"""
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config-path", str(config_path)])
    assert result.exit_code == 0
    assert "Welcome to the DotBot QrKey client" in result.output
    cli_mock.assert_called_once()
    args, _ = cli_mock.call_args
    assert isinstance(args[0], QrKeyClientSettings)
    assert args[0].http_host == "testhost"
    assert args[0].http_port == 1234
    assert args[0].webbrowser is True
    assert args[0].verbose is True
