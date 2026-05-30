# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot gateway` — the CLI surface, not the live bridge.

The bridge itself (`_run_gateway`) needs a real serial gateway, so it's
mocked here; we check flag parsing and that the command forwards
`--port` / `--mqtt-url` correctly.
"""

from unittest.mock import patch

from click.testing import CliRunner

from dotbot.cli.gateway import cmd as gateway_cmd


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
    run.assert_called_once_with("/dev/ttyACM0", "mqtts://argus:8883", True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_no_mqtt_defaults_print_on(run):
    result = CliRunner().invoke(gateway_cmd, ["--port", "/dev/ttyACM0"])
    assert result.exit_code == 0, result.output
    run.assert_called_once_with("/dev/ttyACM0", None, True)


@patch("dotbot.cli.gateway._run_gateway")
def test_gateway_no_print_flag(run):
    result = CliRunner().invoke(gateway_cmd, ["--port", "/dev/ttyACM0", "--no-print"])
    assert result.exit_code == 0, result.output
    run.assert_called_once_with("/dev/ttyACM0", None, False)
