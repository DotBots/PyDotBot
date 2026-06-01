# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Headless tests for the unified config resolver (dotbot/config.py).

Pure {flags, env, file} -> resolved value; no hardware, no network. Covers the
precedence chain, discovery order, deployment selection, and strict validation.
"""

import pytest

import dotbot.config as cfg

# --- discovery --------------------------------------------------------------


def test_discover_explicit_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "given.toml"
    explicit.write_text("")
    monkeypatch.setenv("DOTBOT_CONFIG", str(tmp_path / "env.toml"))
    (tmp_path / cfg.PROJECT_CONFIG_NAME).write_text("")
    assert cfg.discover_config_path(explicit, start_dir=tmp_path) == explicit


def test_discover_env_var(tmp_path, monkeypatch):
    env_file = tmp_path / "env.toml"
    monkeypatch.setenv("DOTBOT_CONFIG", str(env_file))
    assert (
        cfg.discover_config_path(None, environ={"DOTBOT_CONFIG": str(env_file)})
        == env_file
    )


def test_discover_project_cwd_upward(tmp_path):
    root = tmp_path / "exp"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    project = root / cfg.PROJECT_CONFIG_NAME
    project.write_text("")
    found = cfg.discover_config_path(None, environ={}, start_dir=nested)
    assert found == project


def test_discover_stops_at_git_boundary(tmp_path, monkeypatch):
    # A dotbot.toml above a .git boundary must NOT be picked up.
    outer = tmp_path / "outer"
    repo = outer / "repo"
    sub = repo / "sub"
    sub.mkdir(parents=True)
    (outer / cfg.PROJECT_CONFIG_NAME).write_text("")  # above the boundary
    (repo / ".git").mkdir()
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", tmp_path / "nope.toml")
    assert cfg.discover_config_path(None, environ={}, start_dir=sub) is None


def test_discover_user_fallback(tmp_path, monkeypatch):
    user = tmp_path / "home.toml"
    user.write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", user)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cfg.discover_config_path(None, environ={}, start_dir=empty) == user


def test_discover_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", tmp_path / "missing.toml")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cfg.discover_config_path(None, environ={}, start_dir=empty) is None


def test_discover_user_file_skipped(tmp_path, monkeypatch):
    # include_user_file=False ignores ~/.dotbot/config.toml (Phase-2 behavior).
    user = tmp_path / "home.toml"
    user.write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", user)
    empty = tmp_path / "empty"
    empty.mkdir()
    got = cfg.discover_config_path(
        None, environ={}, start_dir=empty, include_user_file=False
    )
    assert got is None


# --- loading + validation ---------------------------------------------------


def test_load_none_is_empty():
    config = cfg.load_config(None)
    assert config.conn is None
    assert config.deployment == {}


def test_load_valid(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text(
        """
default_deployment = "inria"
conn = "mqtts://broker.local:8883"
swarm_id = "0001"

[deployment.inria]
conn = "mqtts://broker.inria.fr:8883"
swarm_id = "0001"
location = "Inria Paris"
bots = 100

[fw]
board = "dotbot-v3"

[run.controller]
http_port = 8000
"""
    )
    config = cfg.load_config(path)
    assert config.default_deployment == "inria"
    assert config.fw.board == "dotbot-v3"
    assert config.run.controller.http_port == 8000
    assert config.deployment["inria"].bots == 100


def test_load_unknown_top_level_key_rejected(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('swrm_id = "0001"\n')  # typo
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


def test_load_unknown_section_key_rejected(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('[fw]\nbord = "x"\n')  # typo in a section
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


def test_load_bad_conn_rejected(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('conn = "ftp://nope"\n')  # unrecognized scheme
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


def test_load_accepts_valid_conn_forms(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text(
        '[deployment.sim]\nconn = "simulator"\n'
        '[deployment.cable]\nconn = "/dev/ttyACM0"\n'
        '[deployment.mqtt]\nconn = "mqtts://h:8883"\n'
    )
    config = cfg.load_config(path)
    assert set(config.deployment) == {"sim", "cable", "mqtt"}


def test_load_bad_type_rejected(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('[run.controller]\nhttp_port = "not-an-int"\n')
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


# --- deployment selection ------------------------------------------------------


def _two_deployments():
    return cfg.DotbotConfig(
        default_deployment="inria",
        deployment={
            "inria": cfg.Deployment(swarm_id="0001"),
            "laposte": cfg.Deployment(swarm_id="002a"),
        },
    )


def test_select_deployment_cli_beats_env_and_default():
    config = _two_deployments()
    tb, name = cfg.select_deployment(
        config, cli_name="laposte", environ={"DOTBOT_DEPLOYMENT": "inria"}
    )
    assert name == "laposte"
    assert tb.swarm_id == "002a"


def test_select_deployment_env_beats_default():
    config = _two_deployments()
    _, name = cfg.select_deployment(config, environ={"DOTBOT_DEPLOYMENT": "laposte"})
    assert name == "laposte"


def test_select_deployment_default():
    config = _two_deployments()
    _, name = cfg.select_deployment(config, environ={})
    assert name == "inria"


def test_select_deployment_none_when_unset():
    config = cfg.DotbotConfig()
    assert cfg.select_deployment(config, environ={}) == (None, None)


def test_select_deployment_unknown_raises():
    config = _two_deployments()
    with pytest.raises(cfg.ConfigError):
        cfg.select_deployment(config, cli_name="nope", environ={})


# --- precedence resolution --------------------------------------------------


def test_resolve_flag_wins():
    config = cfg.DotbotConfig(conn="mqtts://file:8883")
    got = cfg.resolve(
        "conn",
        flag="mqtts://flag:8883",
        config=config,
        environ={"DOTBOT_CONN": "mqtts://env:8883"},
        default="mqtts://default:8883",
    )
    assert got == "mqtts://flag:8883"


def test_resolve_env_beats_file_and_default():
    config = cfg.DotbotConfig(swarm_id="file")
    got = cfg.resolve(
        "swarm_id",
        config=config,
        environ={"DOTBOT_SWARM_ID": "env"},
        default="default",
    )
    assert got == "env"


def test_resolve_sectioned_env_name():
    got = cfg.resolve(
        "board",
        section="fw",
        environ={"DOTBOT_FW_BOARD": "nrf5340dk-app"},
        default="dotbot-v3",
    )
    assert got == "nrf5340dk-app"


def test_resolve_shared_env_alias_for_section_key():
    # A sectioned key falls back to the shared DOTBOT_<KEY> alias.
    got = cfg.resolve(
        "swarm_id", section="swarm", environ={"DOTBOT_SWARM_ID": "abcd"}, default="0000"
    )
    assert got == "abcd"


def test_resolve_file_only_then_default():
    config = cfg.DotbotConfig(log_level="debug")
    assert (
        cfg.resolve("log_level", config=config, environ={}, default="info") == "debug"
    )
    assert (
        cfg.resolve("log_level", config=cfg.DotbotConfig(), environ={}, default="info")
        == "info"
    )


def test_resolve_section_beats_top_level():
    config = cfg.DotbotConfig(
        swarm_id="top", swarm=cfg.SwarmSection(swarm_id="section")
    )
    got = cfg.resolve(
        "swarm_id", section="swarm", config=config, environ={}, default="d"
    )
    assert got == "section"


def test_resolve_deployment_beats_top_level():
    config = cfg.DotbotConfig(conn="mqtts://top:8883")
    tb = cfg.Deployment(conn="mqtts://inria:8883")
    got = cfg.resolve("conn", config=config, deployment=tb, environ={}, default=None)
    assert got == "mqtts://inria:8883"


def test_resolve_section_beats_deployment():
    # Documented order: section value > selected deployment > top-level.
    config = cfg.DotbotConfig(swarm=cfg.SwarmSection(swarm_id="section"))
    tb = cfg.Deployment(swarm_id="deployment")
    got = cfg.resolve(
        "swarm_id",
        section="swarm",
        config=config,
        deployment=tb,
        environ={},
        default="d",
    )
    assert got == "section"


def test_resolve_env_coercion_int():
    got = cfg.resolve(
        "http_port",
        section="run",
        environ={"DOTBOT_RUN_HTTP_PORT": "9000"},
        default=8000,
    )
    assert got == 9000 and isinstance(got, int)


def test_resolve_env_coercion_bool():
    got = cfg.resolve(
        "webbrowser",
        section="run",
        environ={"DOTBOT_RUN_WEBBROWSER": "true"},
        default=False,
    )
    assert got is True


def test_resolve_bad_int_env_raises():
    with pytest.raises(cfg.ConfigError):
        cfg.resolve(
            "http_port", section="run", environ={"DOTBOT_HTTP_PORT": "x"}, default=8000
        )
