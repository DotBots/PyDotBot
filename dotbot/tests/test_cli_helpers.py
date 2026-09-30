# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The `dotbot config` management commands.

Inspectors over the config the root group already resolved onto `ctx.obj`,
and the starter file `init` writes. Headless (CliRunner), invoked through the root so the context is
populated (a bare `runner.invoke(show)` would have `ctx.obj is None`).
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import dotbot.config as cfg
from dotbot.cli.main import cli

# A small config naming a site with a broker.
_CONFIG = """\
site = "inria"
swarm_id = "0001"

[fw]
board = "dotbot-v3"

[sites.inria.connection]
conn = "mqtts://broker.local:8883"
"""


@pytest.fixture(autouse=True)
def _no_user_config(tmp_path, monkeypatch):
    """Keep the developer's ~/.dotbot/dotbot.toml out of the "no config" cases."""
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", tmp_path / "no-user.toml")
    monkeypatch.delenv("DOTBOT_CONFIG", raising=False)


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
    # The active site and the conn it brings are reported.
    assert "site:      inria  from dotbot.toml  inline" in result.output
    assert "conn:      mqtts://broker.local:8883  from site inria" in result.output
    # A top-level scalar and a nested section both render.
    assert "swarm_id" in result.output
    assert "[fw]" in result.output
    assert "board" in result.output


def test_config_show_skips_none_values(runner, tmp_path):
    cfg = _write(tmp_path, 'swarm_id = "0001"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert result.exit_code == 0, result.output
    # `log_level` is unset (None) and must not appear.
    assert "log_level" not in result.output


def test_config_show_without_config(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "conn:      (unset)" in result.output
    assert "built-in defaults" in result.output


# --- config init ------------------------------------------------------------


def test_config_init_writes_valid_starter(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code == 0, result.output
        written = Path("dotbot.toml")
        assert written.is_file()
        loaded = cfg.load_config(written)
        assert loaded.conn is None
        assert loaded.site == "default"


def test_config_init_refuses_overwrite_without_force(runner):
    with runner.isolated_filesystem():
        assert runner.invoke(cli, ["config", "init"]).exit_code == 0
        again = runner.invoke(cli, ["config", "init"])
        assert again.exit_code != 0
        assert "already exists" in again.output
        forced = runner.invoke(cli, ["config", "init", "--force"])
        assert forced.exit_code == 0, forced.output


def test_config_init_global(runner, tmp_path, monkeypatch):
    user = tmp_path / "home" / ".dotbot" / "dotbot.toml"
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", user)
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--global"])
    assert result.exit_code == 0, result.output
    assert user.is_file()


def test_config_show_without_config_hints_init(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "show"])
    assert "config init" in result.output


def test_config_init_prefills_conn_and_swarm_id(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["config", "init", "--conn", "mqtts://broker:8883", "--swarm-id", "0001"],
        )
        assert result.exit_code == 0, result.output
        loaded = cfg.load_config(Path("dotbot.toml"))
        assert loaded.sites["default"].connection.conn == "mqtts://broker:8883"
        assert loaded.swarm_id == "0001"


def test_config_init_conn_only_leaves_swarm_id_unset(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--conn", "simulator"])
        assert result.exit_code == 0, result.output
        loaded = cfg.load_config(Path("dotbot.toml"))
        assert loaded.conn == "simulator"
        assert loaded.swarm_id is None


def test_config_init_rejects_bad_conn(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--conn", "http://nope"])
        assert result.exit_code != 0
        assert "invalid --conn" in result.output
        assert not Path("dotbot.toml").exists()
