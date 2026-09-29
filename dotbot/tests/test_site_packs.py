# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Site packs: discovery and the inline-wins rule. Every folder is a
temporary one."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.calibration import lighthouse2
from dotbot.cli.main import cli
from dotbot.config import ConfigError, load_config, load_config_text
from dotbot.site_packs import (
    find_packs,
    resolve_site_entry,
    site_catalog,
    site_dirs,
)
from dotbot.tests.lh2_wire_fixture import FIXTURE_ID, FIXTURE_TOML

ANCHOR = "arena top-left corner, against the door wall of C405"
CALIBRATION_NAME = f"calibration-2026-09-10T09-12-00Z-{FIXTURE_ID[:8]}.toml"


def _pack(folder: Path, name: str, anchor: str = ANCHOR, calibration=False) -> Path:
    pack = folder / name
    pack.mkdir(parents=True)
    (pack / "site.toml").write_text(
        f'anchor = "{anchor}"\n'
        "extent_mm = [2000, 4000]\n\n"
        "[areas]\n"
        "field   = { x = 0, y = 0, w = 2000, h = 2000 }\n"
        "staging = { x = 0, y = 2000, w = 2000, h = 2000 }\n"
    )
    if calibration:
        (pack / "calibrations").mkdir()
        (pack / "calibrations" / CALIBRATION_NAME).write_text(FIXTURE_TOML)
    return pack


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A scratch home: packs, calibrations and the user config live under it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", home / ".dotbot")
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", home / "nope.toml")
    return home


@pytest.fixture
def runner():
    return CliRunner()


# --- discovery --------------------------------------------------------------


def test_site_dirs_default_and_relative_entries_read_from_the_config_folder(
    tmp_path, home
):
    config_path = tmp_path / "lab" / "dotbot.toml"
    assert site_dirs(load_config_text(""), config_path) == [
        tmp_path / "lab" / "sites",
        home / ".dotbot" / "sites",
    ]
    config = load_config_text('site_dirs = ["packs", "/abs/packs"]')
    assert site_dirs(config, config_path) == [
        tmp_path / "lab" / "packs",
        Path("/abs/packs"),
    ]


def test_the_first_site_dir_wins_a_name_clash(tmp_path):
    first = _pack(tmp_path / "a", "c405-arena")
    _pack(tmp_path / "b", "c405-arena")
    _pack(tmp_path / "b", "aio")
    (tmp_path / "b" / "not-a-pack").mkdir()
    packs = find_packs([tmp_path / "missing", tmp_path / "a", tmp_path / "b"])
    assert packs == {"c405-arena": first, "aio": tmp_path / "b" / "aio"}


def test_a_pack_is_a_site(tmp_path):
    pack = _pack(tmp_path / "sites", "c405-arena")
    config_path = tmp_path / "dotbot.toml"
    entry = resolve_site_entry(load_config_text(""), config_path, "c405-arena")
    site = entry.site()
    assert (site.name, site.anchor, site.extent_mm) == (
        "c405-arena",
        ANCHOR,
        (2000, 4000),
    )
    assert site.field.name == "field" and site.staging.name == "staging"
    assert site.pack == pack
    assert entry.source == str(pack)


def test_an_inline_table_wins_over_a_pack_and_names_it(tmp_path):
    pack = _pack(tmp_path / "sites", "c405-arena")
    config = load_config_text(
        "[sites.c405-arena.areas]\nfield = { x = 0, y = 0, w = 10, h = 10 }\n"
    )
    entry = resolve_site_entry(config, tmp_path / "dotbot.toml", "c405-arena")
    assert entry.pack is None and entry.shadows == pack
    assert entry.site().field.w == 10
    assert entry.source == f"inline, shadowing {pack}"


def test_an_invalid_pack_fails_loud(tmp_path):
    pack = _pack(tmp_path / "sites", "broken")
    (pack / "site.toml").write_text("extent = [1, 2]\n")
    with pytest.raises(ConfigError, match="invalid site pack"):
        site_catalog(load_config_text(""), tmp_path / "dotbot.toml")


def test_the_active_site_comes_from_a_pack_with_a_notice_when_shadowed(
    runner, tmp_path, home
):
    _pack(tmp_path / "sites", "c405-arena")
    config = tmp_path / "dotbot.toml"
    config.write_text('site = "c405-arena"\n')
    result = runner.invoke(cli, ["-c", str(config), "config", "show"])
    assert result.exit_code == 0, result.output
    assert f"c405-arena  {tmp_path / 'sites' / 'c405-arena'}" in result.output

    from dotbot.cli._site import site_from_context

    class Ctx:
        obj = {"config": load_config(config), "config_path": config}

    site, _ = site_from_context(Ctx())
    assert site.pack == tmp_path / "sites" / "c405-arena"

    config.write_text('site = "c405-arena"\n[sites.c405-arena]\nanchor = "elsewhere"\n')
    Ctx.obj = {"config": load_config(config), "config_path": config}
    site, _ = site_from_context(Ctx())
    assert site.anchor == "elsewhere" and site.pack is None
