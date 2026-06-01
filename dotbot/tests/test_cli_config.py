# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Phase-2 wiring: the root `-c/--config` + `--testbed` flags, and the
`fw`/`device` `--config` -> `--build-config` rename. Headless (CliRunner)."""

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _write(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


# --- root config loading ----------------------------------------------------


def test_root_accepts_valid_config(runner, tmp_path):
    cfg = _write(tmp_path, 'swarm_id = "0001"\n[testbed.inria]\nconn = "simulator"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code == 0, result.output


def test_root_bad_config_errors(runner, tmp_path):
    cfg = _write(tmp_path, 'swrm_id = "x"\n')  # unknown key -> extra=forbid
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code != 0
    assert "config" in result.output.lower()


def test_root_missing_config_errors(runner, tmp_path):
    result = runner.invoke(cli, ["-c", str(tmp_path / "nope.toml"), "fw", "--help"])
    assert result.exit_code != 0


def test_root_selects_testbed(runner, tmp_path):
    cfg = _write(tmp_path, '[testbed.inria]\nconn = "simulator"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "--testbed", "inria", "fw", "--help"])
    assert result.exit_code == 0, result.output


def test_root_unknown_testbed_errors(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--testbed", "nope", "fw", "--help"])
    assert result.exit_code != 0
    assert "testbed" in result.output.lower()


def test_root_no_config_is_fine(runner):
    # No -c, no dotbot.toml, user-file fallback off -> empty config, no error.
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code == 0, result.output


# --- build-config rename ----------------------------------------------------


def test_fw_build_uses_build_config(runner):
    result = runner.invoke(cli, ["fw", "build", "--help"])
    assert result.exit_code == 0
    assert "--build-config" in result.output


def test_fw_build_rejects_old_short_flag(runner):
    # Clean break: `-c` no longer sets the build config (it's the root flag now).
    result = runner.invoke(cli, ["fw", "build", "-c", "Debug"])
    assert result.exit_code != 0


def test_device_flash_uses_build_config(runner):
    result = runner.invoke(cli, ["device", "flash", "--help"])
    assert result.exit_code == 0
    assert "--build-config" in result.output
