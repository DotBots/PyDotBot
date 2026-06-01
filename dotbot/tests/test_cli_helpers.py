# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Phase-5 management commands: `dotbot config` + `dotbot deployment`.

Read-only inspectors over the config the root group already resolved onto
`ctx.obj`. Headless (CliRunner), invoked through the root so the context is
populated (a bare `runner.invoke(show)` would have `ctx.obj is None`).
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import dotbot.config as cfg
from dotbot.cli.main import cli

# A small config with two named deployments and a default selection.
_CONFIG = """\
default_deployment = "inria"
swarm_id = "0001"
conn = "simulator"

[fw]
board = "dotbot-v3"

[deployment.inria]
conn = "simulator"
swarm_id = "0001"
location = "Inria Paris"
bots = 100

[deployment.laposte]
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
    # The selected (default) deployment is reported.
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
    assert "(none)" in result.output  # no deployment selected
    assert "built-in defaults" in result.output


# --- deployment list -----------------------------------------------------------


def test_deployment_list_shows_names_and_active_marker(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "deployment", "list"])
    assert result.exit_code == 0, result.output
    assert "inria" in result.output
    assert "laposte" in result.output
    # The active (default_deployment) one is marked with `*`.
    active_line = next(line for line in result.output.splitlines() if "inria" in line)
    assert active_line.lstrip().startswith("*")
    # Descriptive fields render.
    assert "Inria Paris" in result.output
    assert "1000" in result.output


def test_deployment_list_honors_deployment_flag(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(
        cli, ["-c", str(cfg), "--deployment", "laposte", "deployment", "list"]
    )
    assert result.exit_code == 0, result.output
    active_line = next(line for line in result.output.splitlines() if "laposte" in line)
    assert active_line.lstrip().startswith("*")


def test_deployment_list_empty(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["deployment", "list"])
    assert result.exit_code == 0, result.output
    assert "no deployments configured" in result.output.lower()


# --- deployment show -----------------------------------------------------------


def test_deployment_show_known(runner, tmp_path):
    cfg = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "deployment", "show", "inria"])
    assert result.exit_code == 0, result.output
    assert "inria" in result.output
    assert "Inria Paris" in result.output
    assert "conn" in result.output
    # It is the active deployment.
    assert "active" in result.output


def test_deployment_show_unknown_errors(runner, tmp_path):
    cfg_file = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "show", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output
    # Lists the defined deployments in the error.
    assert "inria" in result.output


# --- deployment use ----------------------------------------------------------


def test_deployment_use_sets_default(runner, tmp_path):
    # _CONFIG defaults to "inria"; switch it to "laposte".
    cfg_file = _write(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "use", "laposte"])
    assert result.exit_code == 0, result.output
    assert "laposte" in result.output
    assert cfg.load_config(cfg_file).default_deployment == "laposte"


def test_deployment_use_preserves_comments(runner, tmp_path):
    text = (
        "# my deployments\n"
        '# default_deployment = "old"\n'
        "\n"
        "[deployment.inria]\n"
        'conn = "simulator"\n'
    )
    cfg_file = _write(tmp_path, text)
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "use", "inria"])
    assert result.exit_code == 0, result.output
    written = cfg_file.read_text()
    assert "# my deployments" in written  # comment survives
    assert 'default_deployment = "inria"' in written
    assert cfg.load_config(cfg_file).default_deployment == "inria"


def test_deployment_use_inserts_when_absent(runner, tmp_path):
    # No default_deployment line at all -> the key is inserted before the table.
    text = '[deployment.inria]\nconn = "simulator"\n'
    cfg_file = _write(tmp_path, text)
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "use", "inria"])
    assert result.exit_code == 0, result.output
    assert cfg.load_config(cfg_file).default_deployment == "inria"


def test_deployment_use_unknown_leaves_file_untouched(runner, tmp_path):
    cfg_file = _write(tmp_path)
    before = cfg_file.read_text()
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "use", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output
    assert "inria" in result.output  # lists known deployments
    assert cfg_file.read_text() == before


def test_deployment_use_without_config_hints_init(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["deployment", "use", "inria"])
    assert result.exit_code != 0
    assert "config init" in result.output


def test_deployment_use_then_list_marks_it_active(runner, tmp_path):
    cfg_file = _write(tmp_path)
    runner.invoke(cli, ["-c", str(cfg_file), "deployment", "use", "laposte"])
    result = runner.invoke(cli, ["-c", str(cfg_file), "deployment", "list"])
    active_line = next(line for line in result.output.splitlines() if "laposte" in line)
    assert active_line.lstrip().startswith("*")


# --- config init ------------------------------------------------------------


def test_config_init_writes_valid_starter(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code == 0, result.output
        written = Path("dotbot.toml")
        assert written.is_file()
        # The starter is all-commented, so it loads as a valid empty config.
        loaded = cfg.load_config(written)
        assert loaded.conn is None
        assert loaded.deployment == {}


def test_config_init_refuses_overwrite_without_force(runner):
    with runner.isolated_filesystem():
        assert runner.invoke(cli, ["config", "init"]).exit_code == 0
        again = runner.invoke(cli, ["config", "init"])
        assert again.exit_code != 0
        assert "already exists" in again.output
        forced = runner.invoke(cli, ["config", "init", "--force"])
        assert forced.exit_code == 0, forced.output


def test_config_init_global(runner, tmp_path, monkeypatch):
    import dotbot.cli.config_cmd as ccmd

    user = tmp_path / "home" / ".dotbot" / "config.toml"
    monkeypatch.setattr(ccmd, "USER_CONFIG_PATH", user)
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
        assert loaded.conn == "mqtts://broker:8883"
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
