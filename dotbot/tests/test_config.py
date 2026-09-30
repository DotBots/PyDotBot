# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Headless tests for the unified config resolver (dotbot/config.py).

Pure {flags, env, file} -> resolved value; no hardware, no network. Covers the
precedence chain with each value's source, discovery order, and strict
validation.
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


def test_discover_project_cwd_only(tmp_path):
    # A dotbot.toml in the cwd is discovered.
    project = tmp_path / cfg.PROJECT_CONFIG_NAME
    project.write_text("")
    assert cfg.discover_config_path(None, environ={}, start_dir=tmp_path) == project


def test_discover_ignores_parent_dirs(tmp_path, monkeypatch):
    # A dotbot.toml in a PARENT is NOT discovered - the cwd only, no walking up.
    (tmp_path / cfg.PROJECT_CONFIG_NAME).write_text("")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", tmp_path / "nope.toml")
    assert cfg.discover_config_path(None, environ={}, start_dir=nested) is None


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


def test_the_user_config_is_dotbot_toml_under_home():
    assert cfg.PROJECT_CONFIG_NAME == "dotbot.toml"
    assert cfg.USER_CONFIG_PATH.name == "dotbot.toml"


def test_a_user_config_under_its_former_name_is_refused(tmp_path, monkeypatch):
    home = tmp_path / ".dotbot"
    home.mkdir()
    (home / "config.toml").write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", home / "dotbot.toml")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.discover_config_path(None, environ={}, start_dir=empty)
    assert str(excinfo.value) == (
        f"rename {home / 'config.toml'} to {home / 'dotbot.toml'}"
    )


def test_the_former_name_is_ignored_once_renamed_or_pointed_past(tmp_path, monkeypatch):
    home = tmp_path / ".dotbot"
    home.mkdir()
    (home / "config.toml").write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", home / "dotbot.toml")
    explicit = tmp_path / "given.toml"
    assert cfg.discover_config_path(explicit, environ={}) == explicit
    (home / "dotbot.toml").write_text("")
    assert cfg.discover_config_path(None, environ={}, start_dir=tmp_path) == (
        home / "dotbot.toml"
    )


# --- loading + validation ---------------------------------------------------


def test_load_none_is_empty():
    config = cfg.load_config(None)
    assert config.conn is None
    assert config.sites == {}


@pytest.mark.parametrize(
    "text, key",
    [
        ('[deployment.inria]\nconn = "simulator"\n', "[deployment.*]"),
        ('default_deployment = "inria"\n', "default_deployment"),
    ],
)
def test_an_old_deployment_file_names_where_its_keys_went(tmp_path, text, key):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_config(path)
    message = str(excinfo.value)
    assert f"{key} is gone" in message
    assert "[connection]" in message
    assert "dotbot site use" in message


def test_load_valid(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text(
        """
conn = "mqtts://broker.local:8883"
swarm_id = "0001"

[sites.inria.connection]
conn = "mqtts://broker.inria.fr:8883"
swarm_id = "0001"

[fw]
board = "dotbot-v3"

[run.controller]
http_port = 8000
"""
    )
    config = cfg.load_config(path)
    assert config.fw.board == "dotbot-v3"
    assert config.run.controller.http_port == 8000
    assert config.sites["inria"].connection.swarm_id == "0001"


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
        '[run]\nconn = "simulator"\n'
        '[swarm]\nconn = "/dev/ttyACM0"\n'
        '[sites.lab.connection]\nconn = "mqtts://h:8883"\n'
    )
    config = cfg.load_config(path)
    assert config.run.conn == "simulator"
    assert config.swarm.conn == "/dev/ttyACM0"
    assert config.sites["lab"].connection.conn == "mqtts://h:8883"


@pytest.mark.parametrize(
    "table, needle",
    [
        ('conn = "/dev/ttyACM0"', "serial port belongs to one machine"),
        ('conn = "mqtts://me:secret@h:8883"', "carries no credentials"),
    ],
)
def test_a_site_connection_is_a_bare_broker(tmp_path, table, needle):
    path = tmp_path / "dotbot.toml"
    path.write_text(f"[sites.lab.connection]\n{table}\n")
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_config(path)
    assert needle in str(excinfo.value)


def test_a_site_may_name_the_simulator(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('[sites.sim.connection]\nconn = "simulator"\n')
    assert cfg.load_config(path).sites["sim"].connection.conn == "simulator"


def test_load_bad_type_rejected(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text('[run.controller]\nhttp_port = "not-an-int"\n')
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


@pytest.mark.parametrize(
    "line",
    ["camera_max_robots = 0", "camera_detect_share = 0.0", "camera_detect_share = 1.5"],
)
def test_load_camera_limit_out_of_range_rejected(tmp_path, line):
    path = tmp_path / "dotbot.toml"
    path.write_text(f"[run.controller]\n{line}\n")
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(path)


# --- site areas and their roles ----------------------------------------------


def _areas(body: str) -> dict:
    return cfg.load_config_text(f"[sites.hall.areas]\n{body}").sites["hall"].areas


def test_an_area_role_is_optional_and_checked():
    areas = _areas(
        "field = { x = 0, y = 0, w = 2000, h = 2000 }\n"
        'bench = { x = 0, y = 0, w = 500, h = 500, role = "corner" }\n'
    )
    assert areas["field"].role is None
    assert areas["bench"].role == "corner"
    with pytest.raises(cfg.ConfigError, match="role"):
        _areas('pen = { x = 0, y = 0, w = 1, h = 1, role = "arena" }\n')


def test_two_fields_are_refused_naming_both():
    with pytest.raises(cfg.ConfigError, match="field and main are both one"):
        _areas(
            "field = { x = 0, y = 0, w = 2000, h = 2000 }\n"
            'main = { x = 0, y = 0, w = 500, h = 500, role = "field" }\n'
        )


def test_an_explicit_role_frees_a_role_name_for_another_area():
    areas = _areas(
        'field = { x = 0, y = 0, w = 2000, h = 2000, role = "staging" }\n'
        'main = { x = 0, y = 0, w = 500, h = 500, role = "field" }\n'
    )
    assert set(areas) == {"field", "main"}


def test_a_site_with_staging_and_no_field_loads():
    assert set(_areas("staging = { x = 0, y = 0, w = 2000, h = 600 }\n")) == {"staging"}


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


SITE = cfg.SiteLayer(
    "c405-arena", cfg.ConnectionSection(conn="mqtts://site:8883", swarm_id="5173")
)


@pytest.mark.parametrize(
    "flag, environ, config, kind, source, value",
    [
        (
            "mqtts://flag:8883",
            {"DOTBOT_RUN_CONN": "mqtts://env:8883"},
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "flag",
            "--conn",
            "mqtts://flag:8883",
        ),
        (
            None,
            {"DOTBOT_RUN_CONN": "mqtts://run-env:8883", "DOTBOT_CONN": "mqtts://e"},
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "env",
            "DOTBOT_RUN_CONN",
            "mqtts://run-env:8883",
        ),
        (
            None,
            {"DOTBOT_CONN": "mqtts://env:8883"},
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "env",
            "DOTBOT_CONN",
            "mqtts://env:8883",
        ),
        (
            None,
            {},
            cfg.DotbotConfig(
                conn="mqtts://top:8883",
                run=cfg.RunSection(conn="mqtts://run:8883"),
            ),
            "file",
            "dotbot.toml [run]",
            "mqtts://run:8883",
        ),
        (
            None,
            {},
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "file",
            "dotbot.toml",
            "mqtts://top:8883",
        ),
        (None, {}, cfg.DotbotConfig(), "site", "site c405-arena", "mqtts://site:8883"),
    ],
    ids=["flag", "DOTBOT_RUN_CONN", "DOTBOT_CONN", "[run]", "top level", "site"],
)
def test_resolve_source_names_each_rung(flag, environ, config, kind, source, value):
    got = cfg.resolve_source(
        "conn",
        section="run",
        flag=flag,
        flag_name="--conn",
        config=config,
        config_label="dotbot.toml",
        site=SITE,
        environ=environ,
    )
    assert (got.kind, got.source, got.value) == (kind, source, value)


def test_resolve_source_falls_to_the_default():
    got = cfg.resolve_source("conn", section="run", environ={}, default="simulator")
    assert (got.kind, got.source, got.value, got.hidden) == (
        "default",
        "the default",
        "simulator",
        (),
    )


def test_resolve_source_hidden_names_the_shadowed_values():
    config = cfg.DotbotConfig(swarm_id="1234")
    got = cfg.resolve_source(
        "swarm_id",
        config=config,
        config_label="dotbot.toml",
        site=SITE,
        environ={"DOTBOT_SWARM_ID": "0A1B"},
    )
    assert got.value == "0A1B"
    assert got.source == "DOTBOT_SWARM_ID"
    assert got.hidden == (("dotbot.toml", "1234"), ("site c405-arena", "5173"))


@pytest.mark.parametrize("inline", [True, False], ids=["inline table", "site pack"])
def test_only_an_inline_site_connection_counts_as_set_by_you(inline):
    site = cfg.SiteLayer(SITE.name, SITE.connection, inline=inline)
    got = cfg.resolve_source("conn", site=site, environ={})
    assert (got.kind, got.user_set) == ("site", inline)


def test_your_file_beats_the_site_connection():
    config = cfg.DotbotConfig(conn="mqtts://mine:8883")
    got = cfg.resolve_source("conn", config=config, site=SITE, environ={})
    assert got.value == "mqtts://mine:8883"
    assert got.user_set
    assert got.hidden == (("site c405-arena", "mqtts://site:8883"),)


def test_the_site_connection_counts_only_for_conn_and_swarm_id():
    got = cfg.resolve("board", section="fw", site=SITE, environ={}, default="d")
    assert got == "d"


def test_resolve_section_beats_top_level_and_the_site():
    config = cfg.DotbotConfig(swarm=cfg.SwarmSection(swarm_id="section"))
    got = cfg.resolve(
        "swarm_id", section="swarm", config=config, site=SITE, environ={}, default="d"
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
        "headless",
        section="run",
        environ={"DOTBOT_RUN_HEADLESS": "true"},
        default=False,
    )
    assert got is True


def test_resolve_bad_int_env_raises():
    with pytest.raises(cfg.ConfigError):
        cfg.resolve(
            "http_port", section="run", environ={"DOTBOT_HTTP_PORT": "x"}, default=8000
        )


def test_resolve_nested_section_from_file():
    config = cfg.DotbotConfig(
        run=cfg.RunSection(
            controller=cfg.ControllerSection(swarmit_url="http://lab:9001")
        )
    )
    got = cfg.resolve(
        "swarmit_url",
        section="run.controller",
        config=config,
        environ={},
        default="http://localhost:8001",
    )
    assert got == "http://lab:9001"


def test_resolve_nested_section_env_name():
    got = cfg.resolve(
        "swarmit_url",
        section="run.controller",
        environ={"DOTBOT_RUN_CONTROLLER_SWARMIT_URL": "http://env:9001"},
        default="http://localhost:8001",
    )
    assert got == "http://env:9001"


def test_resolve_nested_section_shared_env_alias():
    got = cfg.resolve(
        "swarmit_url",
        section="run.controller",
        environ={"DOTBOT_SWARMIT_URL": "http://env:9001"},
        default="http://localhost:8001",
    )
    assert got == "http://env:9001"


def test_resolve_nested_section_missing_falls_to_default():
    got = cfg.resolve(
        "swarmit_url",
        section="run.controller",
        config=cfg.DotbotConfig(),
        environ={},
        default="http://localhost:8001",
    )
    assert got == "http://localhost:8001"


@pytest.mark.parametrize(
    "old, new",
    [
        ("firmware_repo", "dotbot-firmware"),
        ("swarmit_repo", "swarmit"),
        ("mari_repo", "mari"),
    ],
)
def test_fw_repo_keys_name_their_fw_sources_key(tmp_path, old, new):
    path = tmp_path / "dotbot.toml"
    path.write_text(f'[fw]\n{old} = "x"\n')
    with pytest.raises(cfg.ConfigError, match=rf"\[fw\]\.{old} is now the {new} key"):
        cfg.load_config(path)


def test_fw_sources_takes_only_the_hyphenated_key():
    cfg.DotbotConfig.model_validate({"fw": {"sources": {"dotbot-firmware": "x"}}})
    with pytest.raises(cfg.ValidationError):
        cfg.DotbotConfig.model_validate({"fw": {"sources": {"dotbot_firmware": "x"}}})
