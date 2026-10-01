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


def _kinds(files):
    return [(kind, path) for kind, path in files]


def test_discover_explicit_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "given.toml"
    explicit.write_text("")
    monkeypatch.setenv("DOTBOT_CONFIG", str(tmp_path / "env.toml"))
    (tmp_path / cfg.PROJECT_CONFIG_NAME).write_text("")
    assert cfg.discover_files(explicit, start_dir=tmp_path) == [("project", explicit)]


def test_discover_env_var(tmp_path):
    env_file = tmp_path / "env.toml"
    assert cfg.discover_files(None, environ={"DOTBOT_CONFIG": str(env_file)}) == [
        ("project", env_file)
    ]


def test_discover_project_cwd_only(tmp_path):
    project = tmp_path / cfg.PROJECT_CONFIG_NAME
    project.write_text("")
    assert cfg.discover_files(None, environ={}, start_dir=tmp_path) == [
        ("project", project)
    ]


def test_discover_ignores_parent_dirs(tmp_path):
    (tmp_path / cfg.PROJECT_CONFIG_NAME).write_text("")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert cfg.discover_files(None, environ={}, start_dir=nested) == []


def test_discover_stacks_the_user_project_and_local_files(tmp_path, monkeypatch):
    user = tmp_path / "home" / "dotbot.toml"
    user.parent.mkdir()
    user.write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", user)
    project = tmp_path / cfg.PROJECT_CONFIG_NAME
    project.write_text("")
    local = tmp_path / "dotbot.local.toml"
    local.write_text("")
    assert cfg.discover_files(None, environ={}, start_dir=tmp_path) == [
        ("user", user),
        ("project", project),
        ("local", local),
    ]


def test_the_overlay_of_a_c_file_is_its_stem_local_toml(tmp_path):
    explicit = tmp_path / "lab.toml"
    explicit.write_text("")
    (tmp_path / "lab.local.toml").write_text("")
    (tmp_path / "dotbot.local.toml").write_text("")
    assert cfg.discover_files(explicit, environ={}) == [
        ("project", explicit),
        ("local", tmp_path / "lab.local.toml"),
    ]


def test_the_user_file_is_not_also_the_project_file(tmp_path, monkeypatch):
    home = tmp_path / ".dotbot"
    home.mkdir()
    user = home / "dotbot.toml"
    user.write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", user)
    assert cfg.discover_files(None, environ={}, start_dir=home) == [("user", user)]


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
        cfg.discover_files(None, environ={}, start_dir=empty)
    assert str(excinfo.value) == (
        f"{home / 'config.toml'} is the user config's former name; "
        f"rename it to {home / 'dotbot.toml'}"
    )


def test_the_former_name_is_ignored_once_renamed(tmp_path, monkeypatch):
    home = tmp_path / ".dotbot"
    home.mkdir()
    (home / "config.toml").write_text("")
    (home / "dotbot.toml").write_text("")
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", home / "dotbot.toml")
    assert cfg.discover_files(None, environ={}, start_dir=tmp_path) == [
        ("user", home / "dotbot.toml")
    ]


# --- loading, merging + validation -------------------------------------------


def _stack(tmp_path, monkeypatch, user="", project=None, local=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / "dotbot.toml").write_text(user)
    monkeypatch.setattr(cfg, "USER_CONFIG_PATH", home / "dotbot.toml")
    if project is not None:
        (tmp_path / "dotbot.toml").write_text(project)
    if local is not None:
        (tmp_path / "dotbot.local.toml").write_text(local)
    return cfg.load_discovered(environ={}, start_dir=tmp_path)


def test_every_layer_merges_key_by_key(tmp_path, monkeypatch):
    config = _stack(
        tmp_path,
        monkeypatch,
        user='swarm_id = "0042"\n[fw]\nsegger_dir = "/opt/ses"\nboard = "dotbot-v3"\n',
        project='site = "c405-arena"\n[fw]\nboard = "nrf5340dk"\n'
        '[fw.sources]\nmari = "repos/mari"\n',
        local='swarm_id = "A001"\n[fw.sources]\nswarmit = "../swarmit"\n',
    )
    assert config.fw.segger_dir == "/opt/ses"
    assert config.fw.board == "nrf5340dk"
    assert (config.fw.sources.mari, config.fw.sources.swarmit) == (
        "repos/mari",
        "../swarmit",
    )
    assert config.swarm_id == "A001"
    assert config.site == "c405-arena"
    assert [item.kind for item in config.files] == ["user", "project", "local"]
    assert config.origin("fw", "segger_dir").kind == "user"
    assert config.origin("fw", "sources", "swarmit").kind == "local"
    assert config.project_dir == tmp_path.resolve()


def test_a_typo_names_the_file_it_is_in(tmp_path, monkeypatch):
    with pytest.raises(cfg.ConfigError, match="dotbot.local.toml"):
        _stack(tmp_path, monkeypatch, project="", local='swrm_id = "1"\n')


def test_a_login_is_refused_outside_the_user_file(tmp_path, monkeypatch):
    with pytest.raises(cfg.ConfigError, match=r"\[login\] belongs only in"):
        _stack(
            tmp_path,
            monkeypatch,
            project='[login."argus"]\nuser = "me"\npassword = "x"\n',
        )


def test_a_login_in_the_user_file_loads(tmp_path, monkeypatch):
    config = _stack(
        tmp_path, monkeypatch, user='[login."argus"]\nuser = "me"\npassword = "x"\n'
    )
    assert config.login["argus"].user == "me"


def test_resolve_relative_reads_from_the_file_that_set_it(tmp_path, monkeypatch):
    config = _stack(
        tmp_path, monkeypatch, project='[fw.sources]\nmari = "repos/mari"\n'
    )
    origin = config.origin("fw", "sources", "mari")
    assert cfg.resolve_relative("repos/mari", origin) == tmp_path / "repos" / "mari"


def test_load_none_is_empty():
    config = cfg.load_config(None)
    assert config.conn is None
    assert config.files == ()


@pytest.mark.parametrize(
    "text, needle",
    [
        ('[deployment.inria]\nconn = "simulator"\n', "[deployment.*] is gone"),
        ('default_deployment = "inria"\n', "default_deployment is gone"),
        ('[sites.lab]\nanchor = "x"\n', "sites/<name>/site.toml"),
        ('site_dirs = ["sites"]\n', "site_dirs is gone"),
        ('log_level = "debug"\n', "--log-level"),
        ('[swarm]\nswarm_id = "1"\n', "top-level keys"),
        ('[run]\nconn = "simulator"\n', "[run] conn is now the top-level conn"),
        ('[run.gateway]\nserial_port = "x"\n', "[run.gateway] is gone"),
        ('[run.controller]\nbackground_map = "x"\n', "--background-map"),
    ],
)
def test_a_removed_key_names_where_it_went(tmp_path, text, needle):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_config(path)
    message = str(excinfo.value)
    assert needle in message
    assert "\n" not in message


def test_load_valid(tmp_path):
    path = tmp_path / "dotbot.toml"
    path.write_text(
        """
conn = "mqtts://broker.local:8883"
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


@pytest.mark.parametrize("conn", ["simulator", "/dev/ttyACM0", "mqtts://h:8883"])
def test_load_accepts_valid_conn_forms(conn):
    assert cfg.load_config_text(f'conn = "{conn}"\n').conn == conn


@pytest.mark.parametrize(
    "table, needle",
    [
        ('conn = "/dev/ttyACM0"', "serial port belongs to one machine"),
        ('conn = "mqtts://me:secret@h:8883"', "carries no credentials"),
    ],
)
def test_a_site_connection_is_a_bare_broker(table, needle):
    with pytest.raises(cfg.ValidationError) as excinfo:
        cfg.SiteSection.model_validate(
            {"connection": dict([table.replace('"', "").split(" = ")])}
        )
    assert needle in str(excinfo.value)


def test_a_site_may_name_the_simulator():
    site = cfg.SiteSection.model_validate({"connection": {"conn": "simulator"}})
    assert site.connection.conn == "simulator"


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
    import tomllib

    try:
        return cfg.SiteSection.model_validate(tomllib.loads(f"[areas]\n{body}")).areas
    except cfg.ValidationError as exc:
        raise cfg.ConfigError(str(exc)) from exc


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
        "board", section="fw", environ={"DOTBOT_BOARD": "abcd"}, default="0000"
    )
    assert got == "abcd"


def test_resolve_file_only_then_default():
    config = cfg.DotbotConfig(swarm_id="1234")
    assert cfg.resolve("swarm_id", config=config, environ={}, default="d") == "1234"
    assert (
        cfg.resolve("swarm_id", config=cfg.DotbotConfig(), environ={}, default="d")
        == "d"
    )


SITE = cfg.SiteLayer(
    "c405-arena", cfg.ConnectionSection(conn="mqtts://site:8883", swarm_id="5173")
)


@pytest.mark.parametrize(
    "flag, environ, config, kind, source, value",
    [
        (
            "mqtts://flag:8883",
            {"DOTBOT_CONN": "mqtts://env:8883"},
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "flag",
            "--conn",
            "mqtts://flag:8883",
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
            cfg.DotbotConfig(conn="mqtts://top:8883"),
            "file",
            "dotbot.toml",
            "mqtts://top:8883",
        ),
        (None, {}, cfg.DotbotConfig(), "site", "site c405-arena", "mqtts://site:8883"),
    ],
    ids=["flag", "DOTBOT_CONN", "file", "site"],
)
def test_resolve_source_names_each_rung(flag, environ, config, kind, source, value):
    got = cfg.resolve_source(
        "conn",
        flag=flag,
        flag_name="--conn",
        config=config,
        config_label="dotbot.toml",
        site=SITE,
        environ=environ,
    )
    assert (got.kind, got.source, got.value) == (kind, source, value)


def test_resolve_source_names_each_file_of_a_stack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = _stack(
        tmp_path,
        monkeypatch,
        user='conn = "mqtts://user:8883"\n',
        project='conn = "mqtts://project:8883"\n',
        local='conn = "mqtt://localhost:1883"\n',
    )
    got = cfg.resolve_source("conn", config=config, site=SITE, environ={})
    assert (got.source, got.value) == ("dotbot.local.toml", "mqtt://localhost:1883")
    assert [value for _, value in got.hidden] == [
        "mqtts://project:8883",
        "mqtts://user:8883",
        "mqtts://site:8883",
    ]
    assert got.hidden[0][0] == "dotbot.toml"
    assert got.hidden[1][0].endswith("home/dotbot.toml")


def test_resolve_source_falls_to_the_default():
    got = cfg.resolve_source("conn", environ={}, default="simulator")
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


@pytest.mark.parametrize("trust", ["approved at site add", None])
def test_a_site_connection_carries_the_sites_trust(trust):
    site = cfg.SiteLayer(SITE.name, SITE.connection, trust, None if trust else "no")
    got = cfg.resolve_source("conn", site=site, environ={})
    assert (got.kind, got.trust) == ("site", trust)
    assert got.site_distrust == (None if trust else "no")


def test_your_file_beats_the_site_connection():
    config = cfg.DotbotConfig(conn="mqtts://mine:8883")
    got = cfg.resolve_source("conn", config=config, site=SITE, environ={})
    assert got.value == "mqtts://mine:8883"
    assert got.trust == "you named it (the config file)"
    assert got.hidden == (("site c405-arena", "mqtts://site:8883"),)


def test_the_site_connection_counts_only_for_conn_and_swarm_id():
    got = cfg.resolve("board", section="fw", site=SITE, environ={}, default="d")
    assert got == "d"


def test_resolve_env_coercion_int():
    got = cfg.resolve(
        "http_port",
        section="run.controller",
        environ={"DOTBOT_RUN_CONTROLLER_HTTP_PORT": "9000"},
        default=8000,
    )
    assert got == 9000 and isinstance(got, int)


def test_resolve_env_coercion_bool():
    got = cfg.resolve(
        "headless",
        section="run.controller",
        environ={"DOTBOT_RUN_CONTROLLER_HEADLESS": "true"},
        default=False,
    )
    assert got is True


def test_resolve_bad_int_env_raises():
    with pytest.raises(cfg.ConfigError):
        cfg.resolve(
            "http_port",
            section="run.controller",
            environ={"DOTBOT_HTTP_PORT": "x"},
            default=8000,
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


def test_unknown_env_names_a_close_known_name():
    environ = {
        "DOTBOT_SWARMID": "1",
        "DOTBOT_SWARM_ID": "1",
        "DOTBOT_FW_SEGGER_DIR": "/x",
        "DOTBOT_MQTT_USER": "me",
        "DOTBOT_RUN_CONN": "simulator",
        "SEGGER_DIR": "/x",
    }
    assert cfg.unknown_env(environ) == [
        ("DOTBOT_RUN_CONN", "DOTBOT_CONN"),
        ("DOTBOT_SWARMID", "DOTBOT_SWARM_ID"),
    ]


def test_every_schema_key_has_its_env_names():
    known = cfg.known_env_names()
    for name in (
        "DOTBOT_SITE",
        "DOTBOT_FW_ARTIFACTS_DIR",
        "DOTBOT_ARTIFACTS_DIR",
        "DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE",
        "DOTBOT_RUN_CONTROLLER_LH2_CALIBRATION",
        "DOTBOT_DEVICE_PROBE",
    ):
        assert name in known
    for name in ("DOTBOT_LOGIN", "DOTBOT_SEGGER_DIR", "DOTBOT_SWARMIT", "DOTBOT_MARI"):
        assert name not in known


def test_every_toml_example_in_the_configuration_reference_loads():
    import re
    import tomllib
    from pathlib import Path

    doc = Path(__file__).parents[2] / "doc" / "reference" / "configuration.md"
    if not doc.is_file():
        pytest.skip("the docs are not beside this checkout")
    for block in re.findall(r"```toml\n(.*?)```", doc.read_text(), re.S):
        data = tomllib.loads(block)
        if {"anchor", "areas", "connection"} & set(data):
            cfg.SiteSection.model_validate(data)
        else:
            cfg.load_config_text(block)
