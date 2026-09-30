# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The root `-c/--config` flag, the `fw`/`device` `--config` ->
`--build-config` rename, `config show`'s sources, and the site `config init`
writes. Headless (CliRunner)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli
from dotbot.config import load_config


@pytest.fixture
def runner():
    return CliRunner()


def _write(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


# --- root config loading ----------------------------------------------------


def test_root_accepts_valid_config(runner, tmp_path):
    cfg = _write(
        tmp_path,
        'swarm_id = "0001"\n[sites.inria.connection]\nconn = "mqtts://h:8883"\n',
    )
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code == 0, result.output


def test_root_bad_config_errors(runner, tmp_path):
    cfg = _write(tmp_path, 'swrm_id = "x"\n')  # unknown key -> extra=forbid
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code != 0
    assert "config" in result.output.lower()


@pytest.mark.parametrize(
    "areas, error",
    [
        ("field = { x = 0, y = 0, w = 10, h = 10 }\n", None),
        ('pen = { x = 0, y = 0, w = 10, h = 10, role = "staging" }\n', None),
        ('pen = { x = 0, y = 0, w = 10, h = 10, role = "main" }\n', "role"),
        (
            "field = { x = 0, y = 0, w = 10, h = 10 }\n"
            'pen = { x = 0, y = 0, w = 10, h = 10, role = "field" }\n',
            "field and pen are both one",
        ),
    ],
)
def test_root_checks_area_roles(runner, tmp_path, areas, error):
    cfg = _write(tmp_path, f"[sites.hall.areas]\n{areas}")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    if error is None:
        assert result.exit_code == 0, result.output
    else:
        assert result.exit_code != 0
        assert error in result.output


def test_root_missing_config_errors(runner, tmp_path):
    result = runner.invoke(cli, ["-c", str(tmp_path / "nope.toml"), "fw", "--help"])
    assert result.exit_code != 0


def test_root_has_no_deployment_flag(runner, tmp_path):
    result = runner.invoke(cli, ["--deployment", "inria", "fw", "--help"])
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_an_old_deployment_config_fails_with_a_pointer(runner, tmp_path):
    cfg = _write(tmp_path, '[deployment.inria]\nconn = "simulator"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code != 0
    assert "[deployment.*] is gone" in result.output
    assert "validation error" not in result.output


def test_a_user_config_under_its_former_name_is_refused(runner, tmp_path, monkeypatch):
    home = tmp_path / "home" / ".dotbot"
    home.mkdir(parents=True)
    (home / "config.toml").write_text('site = "x"\n')
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", home / "dotbot.toml")
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code != 0
    assert f"rename {home / 'config.toml'} to {home / 'dotbot.toml'}" in result.output


def test_root_no_config_is_fine(runner):
    # No -c, no dotbot.toml, user-file fallback off -> empty config, no error.
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code == 0, result.output


# --- config show: each value's source ----------------------------------------

_ARENA = (
    'site = "c405-arena"\n'
    'swarm_id = "1234"\n'
    "[sites.c405-arena.connection]\n"
    'conn = "mqtts://argus.example:8883"\n'
)


def test_config_show_names_each_source_and_what_it_hides(runner, tmp_path, monkeypatch):
    cfg = _write(tmp_path, _ARENA)
    monkeypatch.setenv("DOTBOT_SWARM_ID", "0A1B")
    monkeypatch.delenv("DOTBOT_MQTT_USER", raising=False)
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "site:      c405-arena  from dotbot.toml  inline" in lines
    assert "conn:      mqtts://argus.example:8883  from site c405-arena" in lines
    assert "swarm_id:  0A1B  from DOTBOT_SWARM_ID" in lines
    assert '           hides dotbot.toml swarm_id = "1234"' in lines
    assert "creds:     none (DOTBOT_MQTT_USER unset)" in lines


def test_config_show_says_where_credentials_go(runner, tmp_path, monkeypatch):
    from dotbot import site_packs

    monkeypatch.setattr(site_packs, "USER_SITES_DIR", tmp_path / "user-sites")
    pack = tmp_path / "user-sites" / "c405-arena"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        '[connection]\nconn = "mqtts://argus.example:8883"\n'
    )
    cfg = _write(tmp_path, 'site = "c405-arena"\nswarm_id = "1234"\n')
    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert "withheld" in result.output
    assert "site c405-arena's broker was never approved" in result.output
    site_packs.write_approval(pack, "mqtts://argus.example:8883")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert (
        "creds:     DOTBOT_MQTT_USER set; sent to this conn's broker: approved "
        "at site add" in result.output
    )
    assert "secret" not in result.output


def test_config_show_json(runner, tmp_path, monkeypatch):
    import json

    cfg = _write(tmp_path, _ARENA)
    monkeypatch.delenv("DOTBOT_SWARM_ID", raising=False)
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["conn"] == {
        "value": "mqtts://argus.example:8883",
        "source": "site c405-arena",
        "hides": [],
    }
    assert report["swarm_id"]["source"] == "dotbot.toml"
    assert report["site"]["name"] == "c405-arena"


# --- build-config rename ----------------------------------------------------


def test_fw_build_uses_build_config(runner):
    result = runner.invoke(cli, ["fw", "build", "--help"])
    assert result.exit_code == 0
    assert "--build-config" in result.output


def test_fw_build_rejects_old_short_flag(runner):
    # Clean break: `-c` no longer sets the build config (it's the root flag now).
    result = runner.invoke(cli, ["fw", "build", "-c", "Debug"])
    assert result.exit_code != 0


def test_device_flash_selects_a_set_and_never_builds(runner):
    result = runner.invoke(cli, ["device", "flash", "--help"])
    assert result.exit_code == 0
    assert "--fw-version" in result.output
    assert "--build-config" not in result.output


# --- config init: the default site ------------------------------------------


@pytest.mark.parametrize(
    "spec, size",
    [
        ("1000x1000", (1000, 1000)),
        ("1000", (1000, 1000)),
        ("1000mm", (1000, 1000)),
        ("1m", (1000, 1000)),
        ("1.5m", (1500, 1500)),
        ("1500", (1500, 1500)),
        ("1.5x2m", (1500, 2000)),
        ("2000x3000", (2000, 3000)),
        ("1.5mx2000mm", (1500, 2000)),
        ("2M", (2000, 2000)),
    ],
)
def test_parse_field_size(spec, size):
    from dotbot.cli.config_cmd import parse_field_size

    assert parse_field_size(spec) == size


@pytest.mark.parametrize(
    "spec, error",
    [
        ("1.5", "a 1.5 mm field is too small; did you mean 1.5m?"),
        ("1.5x2", "did you mean 1.5x2m?"),
        ("1.5mm", "did you mean 1.5m?"),
        ("50", "a 50 mm field is too small"),
        ("2000m", "a 2000 m field is too large; did you mean 2000mm?"),
        ("150cm", "units are mm or m, not cm"),
        ("1500.5", "whole numbers"),
        ("2x3x4", "WxH"),
        ("big", "a size is a number"),
    ],
)
def test_parse_field_size_refuses(spec, error):
    import click

    from dotbot.cli.config_cmd import parse_field_size

    with pytest.raises(click.BadParameter, match=error.replace("?", r"\?")):
        parse_field_size(spec)


def _init(runner, *args):
    result = runner.invoke(cli, ["config", "init", "--force", *args])
    assert result.exit_code == 0, result.output
    return result


def test_config_init_writes_the_default_site(runner):
    from dotbot.site import site_from_config

    with runner.isolated_filesystem():
        _init(runner)
        loaded = load_config("dotbot.toml")
    assert loaded.site == "default"
    site = site_from_config(loaded, "default")
    assert site.extent_mm == (5000, 5000)
    assert site.field.as_dict() == {
        "x": 1500,
        "y": 1500,
        "w": 2000,
        "h": 2000,
        "name": "field",
        "role": "field",
    }
    staging = site.areas["staging"]
    assert (staging.x, staging.y, staging.w, staging.h) == (1500, 3500, 2000, 600)
    assert staging.role == "staging"


@pytest.mark.parametrize(
    "field, extent, area",
    [
        ("1000x1000", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1m", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1.5x2m", (4500, 5000), (1500, 1500, 1500, 2000)),
    ],
)
def test_config_init_field_sizes_the_site(runner, field, extent, area):
    from dotbot.site import site_from_config

    with runner.isolated_filesystem():
        _init(runner, "--field", field)
        site = site_from_config(load_config("dotbot.toml"), "default")
    assert site.extent_mm == extent
    f = site.field
    assert (f.x, f.y, f.w, f.h) == area
    staging = site.areas["staging"]
    assert (staging.y, staging.w) == (f.y_max, f.w)


def test_config_init_warns_about_coverage_only_on_a_large_field(runner):
    with runner.isolated_filesystem():
        assert "Warning" not in _init(runner, "--field", "5m").output
        assert "one LH2 base station" in _init(runner, "--field", "6000x6000").output


def test_config_init_refuses_a_bare_metre_value(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--field", "1.5"])
        assert result.exit_code != 0
        assert "did you mean 1.5m?" in result.output
        assert not Path("dotbot.toml").exists()


def test_config_init_names_the_site(runner):
    with runner.isolated_filesystem():
        _init(runner, "--site", "demo-dcoss-2026")
        loaded = load_config("dotbot.toml")
    assert loaded.site == "demo-dcoss-2026"
    assert set(loaded.sites) == {"demo-dcoss-2026"}


@pytest.mark.parametrize("name", ["my lab", "lab\n", ""])
def test_config_init_refuses_a_site_name_toml_cannot_hold(runner, name):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--site", name])
        assert result.exit_code != 0
        assert "--site" in result.output
        assert not Path("dotbot.toml").exists()


def test_config_init_global_writes_the_default_site(runner, tmp_path, monkeypatch):
    user = tmp_path / "home" / ".dotbot" / "dotbot.toml"
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", user)
    with runner.isolated_filesystem():
        _init(runner, "--global")
    assert "default" in load_config(user).sites


def test_config_init_puts_a_broker_in_the_site_and_swarm_id_in_your_file(runner):
    with runner.isolated_filesystem():
        _init(runner, "--conn", "mqtts://broker:8883", "--swarm-id", "0100")
        loaded = load_config("dotbot.toml")
    assert loaded.conn is None
    assert loaded.swarm_id == "0100"
    assert loaded.sites["default"].connection.conn == "mqtts://broker:8883"
    assert loaded.sites["default"].connection.swarm_id is None


@pytest.mark.parametrize("conn", ["/dev/ttyACM0", "simulator"])
def test_config_init_keeps_a_serial_path_or_the_simulator_top_level(runner, conn):
    with runner.isolated_filesystem():
        _init(runner, "--conn", conn)
        loaded = load_config("dotbot.toml")
    assert loaded.conn == conn
    assert loaded.sites["default"].connection is None


def test_config_init_refuses_a_broker_url_carrying_a_login(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["config", "init", "--conn", "mqtts://me:secret@broker.example:8883"]
        )
        assert result.exit_code != 0
        assert "carries no credentials" in result.output
        assert not Path("dotbot.toml").exists()


def test_example_config_is_what_init_writes(runner):
    """The example config in the repository root is what `config init` writes."""
    example = Path(__file__).parents[2] / "dotbot.example.toml"
    with runner.isolated_filesystem():
        _init(runner)
        assert example.read_text() == Path("dotbot.toml").read_text()
