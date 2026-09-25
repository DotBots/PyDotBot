# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `from_config` option/config bridge (Phase 3).

`from_config` decides, per Click option, whether the value came from the
command line (user wins) or should fall through the config resolver
(config > env > the option's default). These tests drive it through a tiny
throwaway Click command so the parameter-source machinery is exercised for
real.
"""

import click
import pytest
from click.testing import CliRunner

from dotbot.cli._cfg import from_config
from dotbot.config import DotbotConfig


@pytest.fixture
def runner():
    return CliRunner()


def _probe_command():
    """A throwaway command whose single option reads through `from_config`."""

    @click.command()
    @click.option("--board", "-b", default="dotbot-v3")
    @click.pass_context
    def probe(ctx, board):
        resolved = from_config(ctx, "board", "board", "fw")
        click.echo(resolved)

    return probe


def test_flag_on_commandline_wins_over_config(runner):
    """An explicit `--board` beats a config that sets `[fw].board`."""
    cfg = DotbotConfig.model_validate({"fw": {"board": "from-config"}})
    result = runner.invoke(
        _probe_command(),
        ["--board", "from-flag"],
        obj={"config": cfg, "deployment": None},
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "from-flag"


def test_no_flag_falls_to_config(runner):
    """No `--board` on the command line -> the config value is used."""
    cfg = DotbotConfig.model_validate({"fw": {"board": "from-config"}})
    result = runner.invoke(
        _probe_command(),
        [],
        obj={"config": cfg, "deployment": None},
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "from-config"


def test_no_config_falls_to_option_default(runner):
    """No flag and no config -> the option's own default flows through."""
    result = runner.invoke(_probe_command(), [], obj={"config": DotbotConfig()})
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "dotbot-v3"


def test_no_ctx_obj_falls_to_option_default(runner):
    """`ctx.obj` is None when a command runs without the root group -> default."""
    result = runner.invoke(_probe_command(), [])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "dotbot-v3"


def test_env_beats_config(runner, monkeypatch):
    """Env var (`DOTBOT_FW_BOARD`) beats the file layer, loses to the flag."""
    monkeypatch.setenv("DOTBOT_FW_BOARD", "from-env")
    cfg = DotbotConfig.model_validate({"fw": {"board": "from-config"}})
    result = runner.invoke(
        _probe_command(), [], obj={"config": cfg, "deployment": None}
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "from-env"

