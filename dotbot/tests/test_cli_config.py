# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The root `-c/--config` flag, the `fw`/`device` `--config` ->
`--build-config` rename, `config show`'s sources, `config set` / `unset` /
`login`, and the site `config init` writes. Headless (CliRunner)."""

import os
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli
from dotbot.config import load_config


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """A scratch ~/.dotbot: the user file and the added packs."""
    home = tmp_path / "home" / ".dotbot"
    home.mkdir(parents=True)
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", home / "dotbot.toml")
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", home / "sites")
    for name in list(os.environ):
        if name.startswith("DOTBOT_"):
            monkeypatch.delenv(name)
    return home


def _site_of(pack: Path):
    from dotbot.site import site_from_table
    from dotbot.site_packs import read_pack

    return site_from_table(pack.name, read_pack(pack), pack)


def _write(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


# --- root config loading ----------------------------------------------------


def test_root_accepts_valid_config(runner, tmp_path):
    cfg = _write(tmp_path, 'swarm_id = "0001"\nconn = "mqtts://h:8883"\n')
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
def test_the_active_sites_area_roles_are_checked(runner, tmp_path, areas, error):
    cfg = _write(tmp_path, 'site = "hall"\n')
    (tmp_path / "sites" / "hall").mkdir(parents=True)
    (tmp_path / "sites" / "hall" / "site.toml").write_text(f"[areas]\n{areas}")
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


def test_a_user_config_under_its_former_name_is_refused(runner, home):
    (home / "config.toml").write_text('site = "x"\n')
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code != 0
    assert (
        f"{home / 'config.toml'} is the user config's former name; "
        f"rename it to {home / 'dotbot.toml'}"
    ) in result.output


def test_root_no_config_is_fine(runner):
    # No -c, no dotbot.toml, no user file -> empty config, no error.
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code == 0, result.output


def test_root_names_every_file_in_use(runner, tmp_path, home):
    (home / "dotbot.toml").write_text("")
    cfg = _write(tmp_path, "")
    (tmp_path / "dotbot.local.toml").write_text("")
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "list"])
    assert "Using config " in result.output
    assert "dotbot.toml + " in result.output
    assert result.output.count(" + ") == 2


def test_root_warns_about_an_env_variable_nothing_reads(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_SWARMID", "0042")
    cfg = _write(tmp_path, "")
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "list"])
    assert (
        "warning: nothing reads DOTBOT_SWARMID (did you mean DOTBOT_SWARM_ID?)"
        in result.output
    )


@pytest.mark.skipif(os.name == "nt", reason="no POSIX file modes")
def test_root_warns_when_others_can_read_a_login(runner, tmp_path, home):
    user = home / "dotbot.toml"
    user.write_text('[login."argus"]\nuser = "me"\npassword = "x"\n')
    user.chmod(0o644)
    cfg = _write(tmp_path, "")
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "list"])
    assert f"chmod 600 {user}" in result.output
    user.chmod(0o600)
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "list"])
    assert "chmod" not in result.output


# --- config show: each value's source ----------------------------------------


def _arena(tmp_path, local=None):
    cfg = _write(tmp_path, 'site = "c405-arena"\nswarm_id = "1234"\n')
    pack = tmp_path / "sites" / "c405-arena"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        '[connection]\nconn = "mqtts://argus.example:8883"\n'
    )
    if local is not None:
        (tmp_path / "dotbot.local.toml").write_text(local)
    return cfg


def test_config_show_names_each_source_and_what_it_hides(
    runner, tmp_path, monkeypatch, home
):
    (home / "dotbot.toml").write_text('site = "lab"\n')
    cfg = _arena(tmp_path, local='conn = "mqtt://localhost:1883"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOTBOT_SWARM_ID", "0A1B")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == (
        "files:     ~/.dotbot/dotbot.toml (user)  dotbot.toml (project)  "
        "dotbot.local.toml (local)"
    ) or lines[0].endswith("dotbot.toml (project)  dotbot.local.toml (local)")
    assert lines[1].startswith("site:      c405-arena  from dotbot.toml  project pack")
    assert "           hides " in lines[2] and 'site = "lab"' in lines[2]
    assert "conn:      mqtt://localhost:1883  from dotbot.local.toml" in lines
    assert (
        '           hides site c405-arena conn = "mqtts://argus.example:8883"' in lines
    )
    assert "swarm_id:  0A1B  from DOTBOT_SWARM_ID" in lines
    assert '           hides dotbot.toml swarm_id = "1234"' in lines
    assert "login:     localhost: none" in lines


def test_config_show_says_which_login_the_broker_gets(
    runner, tmp_path, monkeypatch, home
):
    pack = home / "sites" / "c405-arena"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        '[connection]\nconn = "mqtts://argus.example:8883"\n'
    )
    cfg = _write(tmp_path, 'site = "c405-arena"\nswarm_id = "1234"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert (
        "login:     argus.example: none (save one with "
        "`dotbot config login argus.example`)" in result.output
    )
    monkeypatch.setenv("DOTBOT_MQTT_USER", "me")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "secret")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert "withheld" in result.output
    assert "site c405-arena's broker was never approved" in result.output
    from dotbot import site_packs

    site_packs.write_approval(pack, "mqtts://argus.example:8883")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert "login:     argus.example: approved at site add" in result.output
    monkeypatch.delenv("DOTBOT_MQTT_USER")
    monkeypatch.delenv("DOTBOT_MQTT_PASS")
    (home / "dotbot.toml").write_text(
        '[login."argus.example"]\nuser = "me"\npassword = "hunter2"\n'
    )
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    assert "login:     argus.example: your [login] for argus.example" in result.output
    assert "hunter2" not in result.output
    assert 'password = "********"' in result.output


def test_config_show_lists_env_variables_nothing_reads(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_SWARMID", "0042")
    result = runner.invoke(cli, ["-c", str(_write(tmp_path, "")), "config", "show"])
    assert (
        "unknown:   DOTBOT_SWARMID (did you mean DOTBOT_SWARM_ID?): nothing reads it"
        in result.output
    )


def test_config_show_json(runner, tmp_path):
    import json

    cfg = _arena(tmp_path)
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["conn"] == {
        "value": "mqtts://argus.example:8883",
        "source": "site c405-arena",
        "hides": [],
    }
    assert report["swarm_id"]["source"].endswith("dotbot.toml")
    assert report["site"]["name"] == "c405-arena"
    assert report["files"] == [{"kind": "project", "path": str(cfg)}]
    assert report["merged"] == {"site": "c405-arena", "swarm_id": "1234"}


def test_config_path_lists_the_files_in_use(runner, tmp_path, home):
    (home / "dotbot.toml").write_text("")
    cfg = _write(tmp_path, "")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "path"])
    assert result.output.splitlines() == [
        f"user     {home / 'dotbot.toml'}",
        f"project  {cfg}",
    ]


# --- config set / unset / login ----------------------------------------------


def _read(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def test_set_writes_your_overlay_in_a_project_and_the_user_file_outside(
    runner, tmp_path, home
):
    cfg = _write(tmp_path, 'site = "team"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "config", "set", "swarm_id", "0042"])
    assert result.exit_code == 0, result.output
    local = tmp_path / "dotbot.local.toml"
    assert f'wrote swarm_id = "0042" to {local}' in result.output
    assert _read(local) == {"swarm_id": "0042"}
    assert cfg.read_text() == 'site = "team"\n'
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "set", "swarm_id", "1200"])
    assert result.exit_code == 0, result.output
    assert _read(home / "dotbot.toml") == {"swarm_id": "1200"}


def test_set_sends_a_machine_key_to_the_user_file_from_a_project(
    runner, tmp_path, home
):
    cfg = _write(tmp_path, "")
    result = runner.invoke(
        cli, ["-c", str(cfg), "config", "set", "fw.segger_dir", "/opt/segger"]
    )
    assert result.exit_code == 0, result.output
    assert _read(home / "dotbot.toml") == {"fw": {"segger_dir": "/opt/segger"}}
    assert not (tmp_path / "dotbot.local.toml").exists()


def test_set_project_writes_the_committed_file_and_says_so(runner, tmp_path):
    cfg = _write(tmp_path, "# team\n")
    result = runner.invoke(
        cli, ["-c", str(cfg), "config", "set", "site", "lab", "--project"]
    )
    assert result.exit_code == 0, result.output
    assert cfg.read_text() == '# team\nsite = "lab"\n'
    assert "shows in git status" in result.output


def test_set_types_the_value_by_the_schema_and_refuses_a_bad_one(
    runner, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    cfg = _write(tmp_path, "")
    local = tmp_path / "dotbot.local.toml"
    for key, value in (
        ("run.controller.lh2_calibration_max_age_days", "14"),
        ("run.controller.camera_detect", "false"),
        ("fw.sources.dotbot-firmware", "repos/wt-x"),
    ):
        result = runner.invoke(cli, ["-c", str(cfg), "config", "set", key, value])
        assert result.exit_code == 0, result.output
    assert _read(local) == {
        "run": {
            "controller": {
                "lh2_calibration_max_age_days": 14,
                "camera_detect": False,
            }
        },
        "fw": {"sources": {"dotbot-firmware": "repos/wt-x"}},
    }
    for key, value, error in (
        ("swarmid", "1", "Invalid value for 'KEY': swarmid is not a config key"),
        ("swarmid", "1", "did you mean swarm_id?"),
        ("site_dirs", "x", "site_dirs is gone"),
        ("run.conn", "simulator", "[run] conn is now the top-level conn"),
        ("deployment.lab.conn", "simulator", "[deployment.*] is gone"),
        ("fw", "x", "is a table"),
        ("run.controller.lh2_calibration_max_age_days", "soon", "whole number"),
        ("conn", "ftp://nope", "invalid config"),
    ):
        result = runner.invoke(cli, ["-c", str(cfg), "config", "set", key, value])
        assert result.exit_code != 0
        assert error in result.output


def test_set_writes_a_path_as_the_file_reads_it(runner, tmp_path, monkeypatch):
    cfg = _write(tmp_path, "")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    result = runner.invoke(
        cli, ["-c", str(cfg), "config", "set", "fw.sources.mari", "../repos/mari"]
    )
    assert result.exit_code == 0, result.output
    assert _read(tmp_path / "dotbot.local.toml") == {
        "fw": {"sources": {"mari": "repos/mari"}}
    }


def test_set_warns_when_a_higher_layer_hides_the_value(
    runner, tmp_path, monkeypatch, home
):
    cfg = _write(tmp_path, "")
    (tmp_path / "dotbot.local.toml").write_text('swarm_id = "A001"\n')
    monkeypatch.setenv("DOTBOT_SWARM_ID", "1200")
    result = runner.invoke(
        cli, ["-c", str(cfg), "config", "set", "swarm_id", "0042", "--user"]
    )
    assert result.exit_code == 0, result.output
    assert "dotbot.local.toml sets swarm_id, which overrides it" in result.output
    assert "DOTBOT_SWARM_ID is set, which overrides it" in result.output


def test_set_refuses_a_password(runner, tmp_path):
    result = runner.invoke(cli, ["config", "set", 'login."argus".password', "hunter2"])
    assert result.exit_code != 0
    assert "dotbot config login argus" in result.output


def test_set_refuses_a_conn_carrying_a_login(runner, tmp_path, home):
    result = runner.invoke(
        cli, ["config", "set", "conn", "mqtts://me:hunter2@broker.example:8883"]
    )
    assert result.exit_code != 0
    assert "dotbot config login broker.example" in result.output
    assert not (home / "dotbot.toml").exists()


def test_unset_removes_the_key_and_any_table_it_empties(runner, tmp_path):
    cfg = _write(tmp_path, "")
    local = tmp_path / "dotbot.local.toml"
    local.write_text(
        '# mine\nconn = "mqtt://localhost:1883"\n[fw.sources]\nmari = "m"\n'
    )
    result = runner.invoke(cli, ["-c", str(cfg), "config", "unset", "conn"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["-c", str(cfg), "config", "unset", "fw.sources.mari"])
    assert result.exit_code == 0, result.output
    assert local.read_text().strip() == "# mine"
    result = runner.invoke(cli, ["-c", str(cfg), "config", "unset", "conn"])
    assert result.exit_code != 0 and "conn is not set in" in result.output


def test_unset_names_the_file_that_does_set_the_key(runner, tmp_path):
    cfg = _write(tmp_path, 'conn = "simulator"\n')
    result = runner.invoke(cli, ["-c", str(cfg), "config", "unset", "conn"])
    assert result.exit_code != 0
    assert "it is set in" in result.output and "dotbot.toml" in result.output


def test_login_saves_a_host_bound_login_readable_by_you_alone(runner, home):
    result = runner.invoke(
        cli,
        ["config", "login", "mqtts://Argus.Example:8883"],
        input="me\nhunter2\n",
    )
    assert result.exit_code == 0, result.output
    user = home / "dotbot.toml"
    assert _read(user) == {
        "login": {"argus.example": {"user": "me", "password": "hunter2"}}
    }
    if os.name != "nt":
        assert user.stat().st_mode & 0o077 == 0
    assert "hunter2" not in result.output


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


def test_config_init_writes_the_default_site_and_selects_it(runner, home):
    with runner.isolated_filesystem():
        _init(runner)
        assert not Path("dotbot.toml").exists()
    assert load_config(home / "dotbot.toml").site == "default"
    site = _site_of(home / "sites" / "default")
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


def test_config_init_keeps_the_rest_of_the_user_file(runner, home):
    (home / "dotbot.toml").write_text('# mine\n[fw]\nsegger_dir = "/opt/ses"\n')
    with runner.isolated_filesystem():
        _init(runner, "--site", "lab", "--swarm-id", "0042")
    text = (home / "dotbot.toml").read_text()
    assert "# mine" in text
    assert _read(home / "dotbot.toml") == {
        "fw": {"segger_dir": "/opt/ses"},
        "site": "lab",
        "swarm_id": "0042",
    }


@pytest.mark.parametrize(
    "field, extent, area",
    [
        ("1000x1000", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1m", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1.5x2m", (4500, 5000), (1500, 1500, 1500, 2000)),
    ],
)
def test_config_init_field_sizes_the_site(runner, home, field, extent, area):
    with runner.isolated_filesystem():
        _init(runner, "--field", field)
    site = _site_of(home / "sites" / "default")
    assert site.extent_mm == extent
    f = site.field
    assert (f.x, f.y, f.w, f.h) == area
    staging = site.areas["staging"]
    assert (staging.y, staging.w) == (f.y_max, f.w)


def test_config_init_warns_about_coverage_only_on_a_large_field(runner):
    with runner.isolated_filesystem():
        assert "Warning" not in _init(runner, "--field", "5m").output
        assert "one LH2 base station" in _init(runner, "--field", "6000x6000").output


def test_config_init_refuses_a_bare_metre_value(runner, home):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--field", "1.5"])
        assert result.exit_code != 0
        assert "did you mean 1.5m?" in result.output
    assert not (home / "dotbot.toml").exists()


def test_config_init_keeps_an_existing_pack_unless_forced(runner, home):
    with runner.isolated_filesystem():
        _init(runner, "--field", "1m")
        kept = runner.invoke(cli, ["config", "init", "--field", "3m"])
    assert "Kept the site pack" in kept.output
    assert _site_of(home / "sites" / "default").field.w == 1000


@pytest.mark.parametrize("name", ["my lab", "lab\n", ""])
def test_config_init_refuses_a_site_name_toml_cannot_hold(runner, home, name):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--site", name])
        assert result.exit_code != 0
        assert "--site" in result.output
    assert not (home / "dotbot.toml").exists()


def test_config_init_project_writes_the_project_and_keeps_yours_out_of_git(
    runner, home
):
    import subprocess

    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        result = _init(runner, "--project", "--site", "lab", "--conn", "/dev/ttyACM0")
        assert load_config("dotbot.toml").site == "lab"
        assert _site_of(Path("sites/lab").resolve()).field is not None
        assert _read(Path("dotbot.local.toml")) == {"conn": "/dev/ttyACM0"}
        assert Path(".gitignore").read_text() == "dotbot.local.toml\n"
        _init(runner, "--project", "--site", "lab")
        assert Path(".gitignore").read_text() == "dotbot.local.toml\n"
    assert "added dotbot.local.toml" in result.output
    assert not (home / "dotbot.toml").exists()


def test_config_init_project_refuses_to_overwrite(runner):
    with runner.isolated_filesystem():
        Path("dotbot.toml").write_text("# mine\n")
        result = runner.invoke(cli, ["config", "init", "--project"])
        assert result.exit_code != 0 and "--force" in result.output
        assert Path("dotbot.toml").read_text() == "# mine\n"


def test_config_init_puts_a_broker_in_the_site_and_swarm_id_in_your_file(runner, home):
    with runner.isolated_filesystem():
        _init(runner, "--conn", "mqtts://broker:8883", "--swarm-id", "0100")
    loaded = load_config(home / "dotbot.toml")
    assert (loaded.conn, loaded.swarm_id) == (None, "0100")
    from dotbot.site_packs import read_pack

    connection = read_pack(home / "sites" / "default").connection
    assert (connection.conn, connection.swarm_id) == ("mqtts://broker:8883", None)
    from dotbot.site_packs import broker_trust, resolve_site_entry

    entry = resolve_site_entry(None, "default")
    assert broker_trust(entry) == ("approved at site add", None)


def _keep(runner, *args):
    result = runner.invoke(cli, ["config", "init", *args])
    assert result.exit_code == 0, result.output
    return result


def test_config_init_puts_a_broker_in_a_kept_pack(runner, home):
    from dotbot.site_packs import broker_trust, read_pack, resolve_site_entry

    pack = home / "sites" / "default"
    with runner.isolated_filesystem():
        _init(runner, "--field", "1m")
        (pack / "site.toml").write_text(
            "# measured\n"
            + (pack / "site.toml").read_text()
            + '\n[connection]\n# the lab\'s\nswarm_id = "0B0B"\n'
        )
        result = _keep(runner, "--conn", "mqtts://broker:8883", "--swarm-id", "A001")
    assert "Kept the site pack" in result.output
    assert f'conn = "mqtts://broker:8883" to {pack / "site.toml"}' in result.output
    assert (pack / "site.toml").read_text().startswith("# measured\n")
    assert "# the lab's" in (pack / "site.toml").read_text()
    assert read_pack(pack).connection.swarm_id == "0B0B"
    assert _site_of(pack).field.w == 1000
    assert read_pack(pack).connection.conn == "mqtts://broker:8883"
    assert load_config(home / "dotbot.toml").conn is None
    assert broker_trust(resolve_site_entry(None, "default")) == (
        "approved at site add",
        None,
    )


def test_config_init_replaces_a_kept_packs_broker_and_says_so(runner, home):
    from dotbot.site_packs import broker_trust, read_pack, resolve_site_entry

    pack = home / "sites" / "default"
    with runner.isolated_filesystem():
        _init(runner, "--conn", "mqtts://old:8883")
        result = _keep(runner, "--conn", "mqtts://new:8883")
        same = _keep(runner, "--conn", "mqtts://new:8883")
    assert "(was mqtts://old:8883)" in result.output
    assert "already names mqtts://new:8883" in same.output
    assert read_pack(pack).connection.conn == "mqtts://new:8883"
    assert broker_trust(resolve_site_entry(None, "default"))[0] is not None


def test_config_init_warns_when_your_conn_hides_the_broker(runner, home):
    (home / "dotbot.toml").write_text('conn = "/dev/ttyACM0"\n')
    with runner.isolated_filesystem():
        result = _init(runner, "--conn", "mqtts://broker:8883")
    assert "sets conn, which hides default's conn" in result.output


def test_config_init_does_not_warn_about_the_same_broker(runner, home, monkeypatch):
    (home / "dotbot.toml").write_text('conn = "mqtts://broker:8883"\n')
    monkeypatch.setenv("DOTBOT_CONN", "mqtts://broker:8883")
    with runner.isolated_filesystem():
        result = _init(runner, "--conn", "mqtts://broker:8883")
    assert "hides" not in result.output


def test_config_init_warns_about_dotbot_conn(runner, home, monkeypatch):
    monkeypatch.setenv("DOTBOT_CONN", "/dev/ttyACM0")
    with runner.isolated_filesystem():
        result = _init(runner, "--conn", "mqtts://broker:8883")
    assert "DOTBOT_CONN is set, which hides default's conn" in result.output


def test_config_init_project_force_does_not_warn_about_the_file_it_replaces(
    runner, home
):
    with runner.isolated_filesystem():
        Path("dotbot.toml").write_text('conn = "/dev/ttyACM0"\n')
        result = _init(runner, "--project", "--conn", "mqtts://broker:8883")
        assert "conn" not in load_config(Path("dotbot.toml")).model_fields_set
    assert "hides" not in result.output


def test_config_init_force_rewrites_the_pack_with_the_broker(runner, home):
    from dotbot.site_packs import read_pack

    pack = home / "sites" / "default"
    with runner.isolated_filesystem():
        _init(runner, "--field", "1m", "--conn", "mqtts://old:8883")
        _init(runner, "--field", "3m", "--conn", "mqtts://new:8883")
    assert _site_of(pack).field.w == 3000
    assert read_pack(pack).connection.conn == "mqtts://new:8883"


@pytest.mark.parametrize("conn", ["/dev/ttyACM0", "simulator"])
def test_config_init_keeps_a_serial_conn_out_of_a_kept_pack(runner, home, conn):
    from dotbot.site_packs import read_pack

    with runner.isolated_filesystem():
        _init(runner)
        _keep(runner, "--conn", conn)
    assert load_config(home / "dotbot.toml").conn == conn
    assert read_pack(home / "sites" / "default").connection is None


@pytest.mark.parametrize("conn", ["/dev/ttyACM0", "simulator"])
def test_config_init_keeps_a_serial_path_or_the_simulator_yours(runner, home, conn):
    with runner.isolated_filesystem():
        _init(runner, "--conn", conn)
    assert load_config(home / "dotbot.toml").conn == conn
    from dotbot.site_packs import read_pack

    assert read_pack(home / "sites" / "default").connection is None


def test_config_init_refuses_a_broker_url_carrying_a_login(runner, home):
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["config", "init", "--conn", "mqtts://me:secret@broker.example:8883"]
        )
        assert result.exit_code != 0
        assert "carries no credentials" in result.output
    assert not (home / "dotbot.toml").exists()


def test_example_config_is_what_init_project_writes(runner):
    """The example config in the repository root is what `config init
    --project` writes."""
    example = Path(__file__).parents[2] / "dotbot.example.toml"
    with runner.isolated_filesystem():
        _init(runner, "--project")
        assert example.read_text() == Path("dotbot.toml").read_text()
