# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Phase-5 management commands: `dotbot config` + `dotbot testbed`.

Read-only inspectors over the config the root group already resolved onto
`ctx.obj`. Headless (CliRunner), invoked through the root so the context is
populated (a bare `runner.invoke(show)` would have `ctx.obj is None`).
"""

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli

# A small config with two named testbeds and a default selection.
_CONFIG = """\
default_testbed = "inria"
swarm_id = "0001"
conn = "simulator"

[fw]
board = "dotbot-v3"

[testbed.inria]
conn = "simulator"
swarm_id = "0001"
location = "Inria Paris"
bots = 100

[testbed.laposte]
conn = "mqtts://broker.local:8883"
location = "La Poste"
bots = 1000
"""


@pytest.fixture
def runner():
    return CliRunner()


def _write(tmp_path, text=_CONFIG):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


# --- config path ------------------------------------------------------------


def test_config_path_with_config(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "config", "path"])
    assert result.exit_code == 0, result.output
    assert str(cfg) in result.output


def test_config_path_without_config(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "path"])
    assert result.exit_code == 0, result.output
    assert "none" in result.output.lower()
    assert "built-in defaults" in result.output


# --- config show ------------------------------------------------------------


def test_config_show_with_config(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert result.exit_code == 0, result.output
    assert str(cfg) in result.output
    # The selected (default) testbed is reported.
    assert "inria" in result.output
    # A top-level scalar and a nested section both render.
    assert "swarm_id" in result.output
    assert "[fw]" in result.output
    assert "board" in result.output


def test_config_show_skips_none_values(runner, tmp_path):
    cfg = _write(tmp_path, 'swarm_id = "0001"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert result.exit_code == 0, result.output
    # `artifacts_dir`/`log_level` are unset (None) and must not appear.
    assert "artifacts_dir" not in result.output
    assert "log_level" not in result.output


def test_config_show_without_config(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "(none)" in result.output  # no testbed selected
    assert "built-in defaults" in result.output


# --- testbed list -----------------------------------------------------------


def test_testbed_list_shows_names_and_active_marker(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "testbed", "list"])
    assert result.exit_code == 0, result.output
    assert "inria" in result.output
    assert "laposte" in result.output
    # The active (default_testbed) one is marked with `*`.
    active_line = next(line for line in result.output.splitlines() if "inria" in line)
    assert active_line.lstrip().startswith("*")
    # Descriptive fields render.
    assert "Inria Paris" in result.output
    assert "1000" in result.output


def test_testbed_list_honors_testbed_flag(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(
        cli, ["-c", str(cfg), "--testbed", "laposte", "testbed", "list"]
    )
    assert result.exit_code == 0, result.output
    active_line = next(line for line in result.output.splitlines() if "laposte" in line)
    assert active_line.lstrip().startswith("*")


def test_testbed_list_empty(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["testbed", "list"])
    assert result.exit_code == 0, result.output
    assert "no testbeds configured" in result.output.lower()


# --- testbed show -----------------------------------------------------------


def test_testbed_show_known(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "testbed", "show", "inria"])
    assert result.exit_code == 0, result.output
    assert "inria" in result.output
    assert "Inria Paris" in result.output
    assert "conn" in result.output
    # It is the active testbed.
    assert "active" in result.output


def test_testbed_show_unknown_errors(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "testbed", "show", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output
    # Lists the defined testbeds in the error.
    assert "inria" in result.output
