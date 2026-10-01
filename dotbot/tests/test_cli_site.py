# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the site resolution ladder.

A site names a physical place, so the package must not ship one: the neutral
default is what a fresh install gets, and a real name comes from the config.
"""

import tomllib

import pytest

from dotbot.area import Area
from dotbot.cli._site import resolve_site_name
from dotbot.config import SiteSection, load_config_text
from dotbot.site import (
    FIELD_FALLBACK_MM,
    SITE_DEFAULT,
    Site,
    field_or_fallback,
    site_from_table,
)


def test_no_config_falls_back_to_a_neutral_package_site():
    assert SITE_DEFAULT == "default"
    assert resolve_site_name(environ={}) == ("default", "the default")


def test_the_config_names_the_site():
    config = load_config_text('site = "inria-aio-c"')
    assert resolve_site_name(config=config, environ={}) == (
        "inria-aio-c",
        "the config file",
    )


def test_the_flag_wins_over_the_config():
    config = load_config_text('site = "inria-aio-c"')
    assert resolve_site_name(config=config, flag="taped-square", environ={}) == (
        "taped-square",
        "--site",
    )


def test_the_environment_wins_over_the_config_and_loses_to_the_flag():
    config = load_config_text('site = "inria-aio-c"')
    environ = {"DOTBOT_SITE": "bench"}
    assert resolve_site_name(config=config, environ=environ) == (
        "bench",
        "DOTBOT_SITE",
    )
    assert resolve_site_name(config=config, flag="taped", environ=environ)[0] == "taped"


def _table(text: str) -> SiteSection:
    return SiteSection.model_validate(tomllib.loads(text))


def test_a_site_table_becomes_its_anchor_extent_and_areas():
    table = _table(
        'anchor = "the arena top-left corner, C405"\n'
        "extent_mm = [2000, 4000]\n"
        "[areas.field]\n"
        "x = 0\ny = 0\nw = 2000\nh = 2000\n"
    )
    site = site_from_table("c405-arena", table)
    assert site.anchor == "the arena top-left corner, C405"
    assert site.extent_mm == (2000, 4000)
    assert site.valid_mm == (0, 0, 2000, 4000)
    assert site.registry().resolve("field").as_dict() == {
        "x": 0,
        "y": 0,
        "w": 2000,
        "h": 2000,
        "name": "field",
        "role": "field",
    }


def test_a_named_site_with_no_table_is_empty_rather_than_an_error():
    """The default site is exactly this: a name, and nothing measured yet."""
    site = site_from_table("bench", None)
    assert (site.name, site.anchor, site.extent_mm, site.areas) == (
        "bench",
        "",
        None,
        {},
    )


def _site(areas: str, extent: str = "") -> Site:
    return site_from_table("hall", _table(f"{extent}[areas]\n{areas}"))


def test_an_area_named_after_a_role_has_it_unless_it_declares_another():
    site = _site(
        "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
        'field = { x = 0, y = 0, w = 10, h = 10, role = "corner" }\n'
        "pen = { x = 0, y = 0, w = 10, h = 10 }\n"
    )
    assert {name: a.role for name, a in site.areas.items()} == {
        "staging": "staging",
        "field": "corner",
        "pen": None,
    }


@pytest.mark.parametrize(
    "areas, field",
    [
        # the field, wherever it is declared
        (
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
            'main = { x = 5, y = 5, w = 10, h = 10, role = "field" }\n',
            "main",
        ),
        # no field: the first area that is neither staging nor a corner
        (
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
            'bench = { x = 0, y = 0, w = 5, h = 5, role = "corner" }\n'
            "pen = { x = 0, y = 0, w = 10, h = 10 }\n",
            "pen",
        ),
        # only staging and corners: the first area
        (
            'bench = { x = 0, y = 0, w = 5, h = 5, role = "corner" }\n'
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n",
            "bench",
        ),
    ],
)
def test_the_field_falls_back_in_order(areas, field):
    assert _site(areas).field.name == field


def test_a_site_with_no_areas_takes_its_extent_as_the_field():
    field = _site("", "extent_mm = [5000, 4000]\n").field
    assert (field.x, field.y, field.w, field.h) == (0, 0, 5000, 4000)
    assert field.name == "0,0,5000,4000"


def test_a_site_that_declares_nothing_has_no_field():
    assert Site().field is None


def test_staging_is_the_first_staging_area():
    site = Site(
        areas={
            "field": Area(0, 0, 10, 10, "field", "field"),
            "dock": Area(0, 10, 10, 5, "dock", "staging"),
            "staging": Area(0, 15, 10, 5, "staging", "staging"),
        }
    )
    assert site.staging.name == "dock"
    assert Site(areas={"field": Area(0, 0, 1, 1, "field", "field")}).staging is None


def test_field_or_fallback():
    assert (
        field_or_fallback(_site("field = { x = 1, y = 1, w = 10, h = 10 }\n")).name
        == "field"
    )
    fallback = Area(0, 0, FIELD_FALLBACK_MM, FIELD_FALLBACK_MM)
    assert field_or_fallback(Site()) == fallback
    assert field_or_fallback(None) == fallback


# --- site use / list / show, and site add's connection prompt ---------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A scratch home holding the user config and the added packs."""
    from dotbot import site_packs

    home = tmp_path / "home" / ".dotbot"
    home.mkdir(parents=True)
    monkeypatch.setattr(site_packs, "USER_SITES_DIR", home / "sites")
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", home / "dotbot.toml")
    monkeypatch.setattr(
        "dotbot.calibration.lighthouse2.CALIBRATION_DIR", tmp_path / "calibrations"
    )
    for name in ("DOTBOT_CONFIG", "DOTBOT_SITE", "DOTBOT_CONN"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.fixture
def runner():
    from click.testing import CliRunner

    return CliRunner()


def _pack(root, name, connection=""):
    pack = root / name
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        'anchor = "the door"\nextent_mm = [2000, 3000]\n'
        "[areas]\nfield = { x = 0, y = 0, w = 2000, h = 2000 }\n"
        '"bench" = { x = 0, y = 2000, w = 500, h = 500, role = "corner" }\n'
        + connection
    )
    return pack


_ARGUS = '[connection]\nconn = "mqtts://argus.example:8883"\n'


def _invoke(runner, *args, input=None):
    from dotbot.cli.main import cli

    return runner.invoke(cli, list(args), input=input)


def test_use_writes_the_site_to_your_overlay_and_keeps_comments(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "team"\n')
    local = tmp_path / "dotbot.local.toml"
    local.write_text('# mine\nsite = "old"  # the old one\n[fw]\nboard = "x"\n')
    _pack(home / "sites", "arena")
    result = _invoke(runner, "-c", str(config), "site", "use", "arena")
    assert result.exit_code == 0, result.output
    assert f'wrote site = "arena" to {local}' in result.output
    text = local.read_text()
    assert "# mine" in text and 'site = "arena"' in text and "[fw]" in text
    assert config.read_text() == 'site = "team"\n'


def test_use_project_changes_the_team_default_and_says_so(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "team"\n')
    _pack(home / "sites", "arena")
    result = _invoke(runner, "-c", str(config), "site", "use", "arena", "--project")
    assert result.exit_code == 0, result.output
    assert config.read_text() == 'site = "arena"\n'
    assert "shows in git status" in result.output


def test_use_accepts_a_pack_path(runner, tmp_path, home):
    pack = _pack(tmp_path / "elsewhere", "hall-b")
    with runner.isolated_filesystem():
        result = _invoke(runner, "site", "use", str(pack))
    assert result.exit_code == 0, result.output
    assert tomllib.loads((home / "dotbot.toml").read_text()) == {"site": str(pack)}


def test_use_project_with_a_pack_path_and_no_project_is_refused(runner, tmp_path, home):
    pack = _pack(tmp_path / "elsewhere", "hall-b")
    with runner.isolated_filesystem():
        result = _invoke(runner, "site", "use", str(pack), "--project")
    assert result.exit_code == 1, result.output
    assert "no project dotbot.toml is in use here" in result.output


def test_use_warns_when_your_file_hides_the_sites_connection(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('conn = "mqtts://mine:8883"\n')
    _pack(home / "sites", "arena", _ARGUS)
    result = _invoke(runner, "-c", str(config), "site", "use", "arena")
    assert result.exit_code == 0, result.output
    assert (
        "dotbot.toml sets conn, which hides arena's conn; "
        "`dotbot config unset conn` to follow the site" in result.output
    )


def test_use_says_nothing_about_a_site_with_no_connection(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('conn = "mqtts://mine:8883"\n')
    _pack(home / "sites", "arena")
    result = _invoke(runner, "-c", str(config), "site", "use", "arena")
    assert "warning" not in result.output


def test_use_refuses_an_unknown_site(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text("")
    result = _invoke(runner, "-c", str(config), "site", "use", "nope")
    assert result.exit_code != 0
    assert "unknown site 'nope'" in result.output
    assert not (tmp_path / "dotbot.local.toml").exists()


def test_use_with_no_config_in_use_creates_the_user_config(runner, home):
    _pack(home / "sites", "arena")
    with runner.isolated_filesystem():
        result = _invoke(runner, "site", "use", "arena")
    assert result.exit_code == 0, result.output
    assert (home / "dotbot.toml").read_text() == 'site = "arena"\n'


def test_add_shows_the_broker_and_asks(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    declined = _invoke(runner, "site", "add", str(pack), input="n\n")
    assert declined.exit_code != 0
    assert "broker:    mqtts://argus.example:8883" in declined.output
    assert "swarm id:  (none; set swarm_id yourself)" in declined.output
    assert not (home / "sites" / "arena").exists()
    accepted = _invoke(runner, "site", "add", str(pack), input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert (home / "sites" / "arena" / "site.toml").is_file()


def test_add_yes_skips_the_question(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    result = _invoke(runner, "site", "add", str(pack), "--yes")
    assert result.exit_code == 0, result.output
    assert "Add site arena?" not in result.output


def test_a_pack_with_no_connection_is_never_asked_about(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena")
    result = _invoke(runner, "site", "add", str(pack))
    assert result.exit_code == 0, result.output
    assert "Add site" not in result.output


def test_a_pack_on_the_simulator_is_never_asked_about(runner, tmp_path, home):
    pack = tmp_path / "src" / "lab"
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text('[connection]\nconn = "simulator"\n')
    result = _invoke(runner, "site", "add", str(pack))
    assert result.exit_code == 0, result.output
    assert "Add site" not in result.output


def _approved(pack):
    from dotbot.site_packs import write_approval

    write_approval(pack, "mqtts://argus.example:8883")
    return pack


def test_add_records_the_approved_broker(runner, tmp_path, home):
    from dotbot.site_packs import read_approval

    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    result = _invoke(runner, "site", "add", str(pack), input="y\n")
    assert result.exit_code == 0, result.output
    assert read_approval(home / "sites" / "arena") == "mqtts://argus.example:8883"
    assert "send it DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS" in result.output


def test_add_says_a_plain_mqtt_broker_never_gets_the_login(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena", '[connection]\nconn = "mqtt://lab:1883"\n')
    result = _invoke(runner, "site", "add", str(pack), input="n\n")
    assert "never send it DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS" in result.output


def test_a_readd_that_changes_the_broker_asks_again_with_old_and_new(
    runner, tmp_path, home
):
    _approved(_pack(home / "sites", "arena", _ARGUS))
    pack = _pack(
        tmp_path / "src",
        "arena",
        '[connection]\nconn = "mqtts://other.example:8883"\nswarm_id = "0A1B"\n',
    )
    result = _invoke(runner, "site", "add", str(pack), "--force", input="n\n")
    assert result.exit_code != 0
    assert "changes its connection" in result.output
    assert (
        "broker:    mqtts://argus.example:8883 -> mqtts://other.example:8883"
        in result.output
    )
    assert "swarm id:  (none) -> 0A1B" in result.output
    assert "argus" in (home / "sites" / "arena" / "site.toml").read_text()


def test_a_readd_with_the_same_broker_is_not_asked_about(runner, tmp_path, home):
    _approved(_pack(home / "sites", "arena", _ARGUS))
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    result = _invoke(runner, "site", "add", str(pack), "--force")
    assert result.exit_code == 0, result.output
    assert "Add site" not in result.output


def test_a_broker_edited_in_place_is_asked_about_against_the_approved_one(
    runner, tmp_path, home
):
    from dotbot.site_packs import read_approval

    installed = _approved(_pack(home / "sites", "arena", _ARGUS))
    toml = installed / "site.toml"
    toml.write_text(toml.read_text().replace("argus", "evil"))
    result = _invoke(runner, "site", "add", str(installed), "--force", input="y\n")
    assert result.exit_code == 0, result.output
    assert (
        "broker:    mqtts://argus.example:8883 -> mqtts://evil.example:8883"
        in result.output
    )
    assert read_approval(installed) == "mqtts://evil.example:8883"


def test_an_installed_pack_never_approved_is_asked_about(runner, tmp_path, home):
    _pack(home / "sites", "arena", _ARGUS)
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    result = _invoke(runner, "site", "add", str(pack), "--force", input="n\n")
    assert result.exit_code != 0
    assert "names its connection" in result.output


def test_add_use_with_no_config_creates_the_user_config(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    with runner.isolated_filesystem():
        result = _invoke(runner, "site", "add", str(pack), "--use", "--yes")
    assert result.exit_code == 0, result.output
    assert (home / "dotbot.toml").read_text() == 'site = "arena"\n'
    assert f'wrote site = "arena" to {home / "dotbot.toml"}' in result.output


def test_add_use_writes_into_your_overlay(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('swarm_id = "A001"\n')
    pack = _pack(tmp_path / "src", "arena")
    result = _invoke(runner, "-c", str(config), "site", "add", str(pack), "--use")
    assert result.exit_code == 0, result.output
    assert config.read_text() == 'swarm_id = "A001"\n'
    assert (tmp_path / "dotbot.local.toml").read_text() == 'site = "arena"\n'
    assert not (home / "dotbot.toml").exists()


def test_add_says_how_to_save_a_login_for_its_broker(runner, tmp_path, home):
    pack = _pack(tmp_path / "src", "arena", _ARGUS)
    result = _invoke(runner, "site", "add", str(pack), "--yes")
    assert "dotbot config login argus.example" in result.output
    home.joinpath("dotbot.toml").write_text(
        '[login."argus.example"]\nuser = "me"\npassword = "x"\n'
    )
    again = _invoke(runner, "site", "add", str(pack), "--yes", "--force")
    assert "config login" not in again.output


def test_add_from_stdin_asks_on_the_terminal_or_needs_yes(
    runner, tmp_path, home, monkeypatch
):
    import builtins
    import io
    import zipfile

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as opened:
        opened.writestr("arena/site.toml", _ARGUS)
    real_open = builtins.open

    def no_tty(path, *args, **kwargs):
        if path == "/dev/tty":
            raise OSError("no terminal")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", no_tty)
    result = _invoke(runner, "site", "add", "-", input=archive.getvalue())
    assert result.exit_code != 0
    assert "pass --yes" in result.output
    result = _invoke(runner, "site", "add", "-", "--yes", input=archive.getvalue())
    assert result.exit_code == 0, result.output


def test_list_marks_the_active_site_and_shows_each_connection(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "lab"\n')
    lab = _pack(tmp_path / "sites", "lab", '[connection]\nconn = "simulator"\n')
    _pack(home / "sites", "arena", _ARGUS)
    result = _invoke(runner, "-c", str(config), "site", "list")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert f"* lab    simulator                   {lab.resolve()}" in lines
    assert f"  arena  mqtts://argus.example:8883  {home / 'sites' / 'arena'}" in lines


def test_show_prints_the_site_its_connection_areas_and_calibrations(
    runner, tmp_path, home
):
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "arena"\n')
    _pack(home / "sites", "arena", _ARGUS)
    result = _invoke(runner, "-c", str(config), "site", "show")
    assert result.exit_code == 0, result.output
    assert "site:        arena (active)" in result.output
    assert "anchor:      the door" in result.output
    assert "extent:      2000 x 3000 mm" in result.output
    assert "connection:  mqtts://argus.example:8883" in result.output
    assert "swarm id:    (none in the pack)" in result.output
    assert "yours: none; `dotbot config set swarm_id <id>`" in result.output
    assert "field  field (from its name)" in result.output
    assert "bench  corner" in result.output
    assert "0 calibration files" in result.output


def test_show_and_list_follow_an_active_pack_named_by_its_path(runner, tmp_path, home):
    pack = _pack(tmp_path / "elsewhere", "arena", '[connection]\nconn = "simulator"\n')
    _pack(home / "sites", "arena", _ARGUS)
    config = tmp_path / "dotbot.toml"
    config.write_text(f"site = {str(pack)!r}\n")
    result = _invoke(runner, "-c", str(config), "site", "show")
    assert result.exit_code == 0, result.output
    assert "site:        arena (active)" in result.output
    assert "connection:  simulator" in result.output
    result = _invoke(runner, "-c", str(config), "site", "list")
    assert result.exit_code == 0, result.output
    assert not any(line.startswith("*") for line in result.output.splitlines())


def test_show_names_your_swarm_id_beside_a_pack_that_has_none(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "arena"\n')
    (tmp_path / "dotbot.local.toml").write_text('swarm_id = "A001"\n')
    _pack(home / "sites", "arena", _ARGUS)
    result = _invoke(runner, "-c", str(config), "site", "show")
    assert result.exit_code == 0, result.output
    assert "yours: A001 (from " in result.output
    assert "dotbot.local.toml)" in result.output


def test_show_with_no_site_active_says_so(runner, home):
    with runner.isolated_filesystem():
        result = _invoke(runner, "site", "show")
    assert result.exit_code == 1
    assert "no site is active; `dotbot site use <name>`" in result.output
