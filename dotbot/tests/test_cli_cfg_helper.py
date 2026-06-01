# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `from_config` option/config bridge (Phase 3).

`from_config` decides, per Click option, whether the value came from the
command line (user wins) or should fall through the config resolver
(config > env > the option's default). These tests drive it through a tiny
throwaway Click command so the parameter-source machinery is exercised for
real, plus one integration check via `dotbot fw artifacts --print-path` that
a config-set `[fw].board` reaches the printed artifact path.
"""

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from dotbot.cli._cfg import from_config
from dotbot.cli.fw import cmd as fw_cmd
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
        obj={"config": cfg, "testbed": None},
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "from-flag"


def test_no_flag_falls_to_config(runner):
    """No `--board` on the command line -> the config value is used."""
    cfg = DotbotConfig.model_validate({"fw": {"board": "from-config"}})
    result = runner.invoke(
        _probe_command(),
        [],
        obj={"config": cfg, "testbed": None},
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
    result = runner.invoke(_probe_command(), [], obj={"config": cfg, "testbed": None})
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "from-env"


# --- integration: config-set [fw].board reaches the artifact path -----------


@pytest.fixture
def fake_firmware_repo(tmp_path, monkeypatch):
    """Point `DOTBOT_FIRMWARE_REPO` at a tmp dir with a Makefile so
    `artifact_path` can resolve a repo without a real DotBot-firmware clone."""
    repo = tmp_path / "fake-dotbot-firmware"
    repo.mkdir()
    (repo / "Makefile").write_text("# fake\n")
    monkeypatch.setenv("DOTBOT_FIRMWARE_REPO", str(repo))
    return repo


def test_fw_artifacts_print_path_reflects_config_board(runner, fake_firmware_repo):
    """`fw artifacts --print-path --app dotbot` with `-t` omitted uses the
    config-set `[fw].board` in the printed path; `-t` overrides it."""
    cfg = DotbotConfig.model_validate({"fw": {"board": "nrf5340dk-app"}})

    # -t omitted: the config board lands in the path.
    from_cfg = runner.invoke(
        fw_cmd,
        ["artifacts", "--print-path", "--app", "dotbot"],
        obj={"config": cfg, "testbed": None},
    )
    assert from_cfg.exit_code == 0, from_cfg.output
    expected = str(
        Path("Output")
        / "nrf5340dk-app"
        / "Release"
        / "Exe"
        / "dotbot-nrf5340dk-app.hex"
    )
    assert from_cfg.output.strip().endswith(expected)

    # -t overrides the config board.
    overridden = runner.invoke(
        fw_cmd,
        ["artifacts", "--print-path", "--app", "dotbot", "-t", "dotbot-v3"],
        obj={"config": cfg, "testbed": None},
    )
    assert overridden.exit_code == 0, overridden.output
    expected_override = str(
        Path("Output") / "dotbot-v3" / "Release" / "Exe" / "dotbot-dotbot-v3.hex"
    )
    assert overridden.output.strip().endswith(expected_override)
