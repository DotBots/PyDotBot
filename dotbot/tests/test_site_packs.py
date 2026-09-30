# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Site packs: discovery, the inline-wins rule, pack-first calibration lookup,
and `dotbot site add` / `export`. Every folder is a temporary one."""

import subprocess
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot import site_packs
from dotbot.calibration import lighthouse2
from dotbot.calibration.lighthouse2 import load_calibration, resolve_calibration_path
from dotbot.cli import site_cmd
from dotbot.cli.main import cli
from dotbot.config import ConfigError, load_config, load_config_text
from dotbot.site import Site
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
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", home / ".dotbot")
    monkeypatch.setattr(site_packs, "USER_SITES_DIR", home / ".dotbot" / "sites")
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
    absolute = tmp_path / "abs" / "packs"
    config = load_config_text(f'site_dirs = ["packs", "{absolute.as_posix()}"]')
    assert site_dirs(config, config_path) == [tmp_path / "lab" / "packs", absolute]


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
    result = runner.invoke(cli, ["-c", str(config), "site", "list"])
    assert result.exit_code == 0, result.output
    assert f"* c405-arena  -  {tmp_path / 'sites' / 'c405-arena'}" in result.output

    from dotbot.cli._site import site_from_context

    class Ctx:
        obj = {"config": load_config(config), "config_path": config}

    site, _ = site_from_context(Ctx())
    assert site.pack == tmp_path / "sites" / "c405-arena"

    config.write_text('site = "c405-arena"\n[sites.c405-arena]\nanchor = "elsewhere"\n')
    Ctx.obj = {"config": load_config(config), "config_path": config}
    site, _ = site_from_context(Ctx())
    assert site.anchor == "elsewhere" and site.pack is None


# --- calibrations -----------------------------------------------------------


def test_a_calibration_is_looked_for_in_the_pack_first(tmp_path, home):
    pack = _pack(tmp_path / "sites", "c405-arena", calibration=True)
    home_copy = home / ".dotbot" / "calibrations" / "c405-arena" / CALIBRATION_NAME
    home_copy.parent.mkdir(parents=True)
    home_copy.write_text(FIXTURE_TOML)
    site = Site(name="c405-arena", anchor=ANCHOR, pack=pack)

    in_pack = pack / "calibrations" / CALIBRATION_NAME
    assert resolve_calibration_path(FIXTURE_ID[:8], site=site) == in_pack
    assert resolve_calibration_path("arena-relay", site=site) == in_pack
    # By name alone, only the home folder is searched.
    assert resolve_calibration_path(FIXTURE_ID[:8], site="c405-arena") == home_copy
    # Without the pack's copy, the home one is found.
    in_pack.unlink()
    assert resolve_calibration_path(FIXTURE_ID[:8], site=site) == home_copy


def test_a_calibration_from_another_site_or_anchor_is_refused(tmp_path, home):
    pack = _pack(tmp_path / "sites", "c405-arena", calibration=True)
    site = Site(name="c405-arena", anchor=ANCHOR, pack=pack)
    assert load_calibration(FIXTURE_ID[:8], site=site).id == FIXTURE_ID

    moved = Site(name="c405-arena", anchor="the window wall", pack=pack)
    with pytest.raises(ValueError, match="records the anchor"):
        load_calibration(FIXTURE_ID[:8], site=moved)

    path = str(pack / "calibrations" / CALIBRATION_NAME)
    with pytest.raises(ValueError, match="made in site 'c405-arena', not 'aio'"):
        load_calibration(path, site=Site(name="aio"))
    # A site with no recorded anchor does not compare anchors.
    assert load_calibration(path, site=Site(name="c405-arena")).id == FIXTURE_ID


# --- dotbot site add / export ------------------------------------------------


def test_export_an_inline_site_with_its_calibrations_then_add_it(
    runner, tmp_path, home
):
    calibrations = home / ".dotbot" / "calibrations" / "c405-arena"
    calibrations.mkdir(parents=True)
    (calibrations / CALIBRATION_NAME).write_text(FIXTURE_TOML)
    config = tmp_path / "dotbot.toml"
    config.write_text(
        '[sites.c405-arena]\nanchor = "a corner"\nextent_mm = [2000, 4000]\n'
        "[sites.c405-arena.areas]\n"
        "field = { x = 0, y = 0, w = 2000, h = 2000 }\n"
        'bench = { x = 1000, y = 0, w = 1000, h = 1000, role = "corner" }\n'
    )
    archive = tmp_path / "out" / "c405.zip"
    result = runner.invoke(
        cli,
        [
            "-c",
            str(config),
            "site",
            "export",
            "c405-arena",
            "--out",
            str(archive),
            "--with-calibrations",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "and 1 calibration file\n" in result.output
    with zipfile.ZipFile(archive) as opened:
        assert sorted(opened.namelist()) == [
            f"c405-arena/calibrations/{CALIBRATION_NAME}",
            "c405-arena/site.toml",
        ]

    result = runner.invoke(cli, ["-c", str(config), "site", "add", str(archive)])
    assert result.exit_code == 0, result.output
    added = home / ".dotbot" / "sites" / "c405-arena"
    assert (added / "calibrations" / CALIBRATION_NAME).is_file()

    # The added pack is a site the next config finds, bench role and all.
    other = tmp_path / "elsewhere" / "dotbot.toml"
    other.parent.mkdir()
    other.write_text("")
    result = runner.invoke(cli, ["-c", str(other), "site", "list"])
    assert f"c405-arena  -  {added}" in result.output
    site = resolve_site_entry(load_config(other), other, "c405-arena").site()
    assert site.areas["bench"].role == "corner"
    assert site.extent_mm == (2000, 4000)

    again = runner.invoke(cli, ["-c", str(config), "site", "add", str(archive)])
    assert again.exit_code != 0 and "--force" in again.output
    forced = runner.invoke(
        cli, ["-c", str(config), "site", "add", str(archive), "--force"]
    )
    assert forced.exit_code == 0, forced.output


def test_add_a_pack_folder_and_a_git_repository(runner, tmp_path, home):
    pack = _pack(tmp_path / "shared", "demo-dcoss-2026")
    result = runner.invoke(cli, ["site", "add", str(pack)])
    assert result.exit_code == 0, result.output
    assert (home / ".dotbot" / "sites" / "demo-dcoss-2026" / "site.toml").is_file()

    repo = _pack(tmp_path / "repos", "aio")
    for command in (
        ["init", "-q"],
        ["add", "site.toml"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "pack"],
    ):
        subprocess.run(["git", "-C", str(repo), *command], check=True)
    result = runner.invoke(cli, ["site", "add", f"git+{repo.as_uri()}"])
    assert result.exit_code == 0, result.output
    added = home / ".dotbot" / "sites" / "aio"
    assert (added / "site.toml").is_file() and not (added / ".git").exists()


def test_a_failed_forced_add_keeps_the_old_pack(runner, tmp_path, home, monkeypatch):
    runner.invoke(cli, ["site", "add", str(_pack(tmp_path / "v1", "lab"))])
    sites = home / ".dotbot" / "sites"
    newer = _pack(tmp_path / "v2", "lab", anchor="moved", calibration=True)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(site_cmd.shutil, "copytree", fail)
    result = runner.invoke(cli, ["site", "add", str(newer), "--force"])
    assert result.exit_code != 0
    assert ANCHOR in (sites / "lab" / "site.toml").read_text()
    assert [path.name for path in sites.iterdir()] == ["lab"]


def test_a_hidden_folder_is_not_a_pack(tmp_path):
    _pack(tmp_path, ".lab-x1y2")
    assert find_packs([tmp_path]) == {}


def _zipped(pack: Path, root: Path) -> bytes:
    archive = pack.parent / "pack.zip"
    with zipfile.ZipFile(archive, "w") as opened:
        for path in pack.rglob("*"):
            if path.is_file():
                opened.write(path, path.relative_to(root).as_posix())
    return archive.read_bytes()


def test_add_reads_a_zip_from_stdin_named_by_its_top_folder(runner, tmp_path, home):
    pack = _pack(tmp_path / "v1", "lab", calibration=True)
    result = runner.invoke(cli, ["site", "add", "-"], input=_zipped(pack, pack.parent))
    assert result.exit_code == 0, result.output
    added = home / ".dotbot" / "sites" / "lab"
    assert (added / "calibrations" / CALIBRATION_NAME).is_file()
    # It writes a pack and reads no config, so it says nothing about one
    assert "config file" not in result.output

    again = runner.invoke(cli, ["site", "add", "-"], input=_zipped(pack, pack.parent))
    assert again.exit_code != 0 and "--force" in again.output

    bare = runner.invoke(cli, ["site", "add", "-"], input=_zipped(pack, pack))
    assert bare.exit_code != 0 and "nothing names its site" in bare.output

    junk = runner.invoke(cli, ["site", "add", "-"], input=b"not a zip")
    assert junk.exit_code != 0 and "not a zip file" in junk.output


def test_add_from_a_terminal_stdin_says_to_pipe_a_zip(runner, home, monkeypatch):
    class Terminal:
        def isatty(self):
            return True

    monkeypatch.setattr(site_cmd.click, "get_binary_stream", lambda name: Terminal())
    result = runner.invoke(cli, ["site", "add", "-"])
    assert result.exit_code != 0
    assert "curl -L <url> | dotbot site add -" in result.output


def test_add_of_a_zip_url_says_to_download_or_pipe_it(runner, home):
    url = "https://example.org/lab.zip"
    result = runner.invoke(cli, ["site", "add", url])
    assert result.exit_code != 0
    assert f"curl -L {url} | dotbot site add -" in result.output


def test_add_refuses_what_is_not_a_pack(runner, tmp_path, home):
    (tmp_path / "empty").mkdir()
    result = runner.invoke(cli, ["site", "add", str(tmp_path / "empty")])
    assert result.exit_code != 0 and "no site.toml" in result.output
    result = runner.invoke(cli, ["site", "add", str(tmp_path / "missing")])
    assert result.exit_code != 0 and "neither a folder" in result.output


def test_export_names_the_known_sites_when_asked_for_another(runner, tmp_path, home):
    config = tmp_path / "dotbot.toml"
    config.write_text("[sites.lab]\n")
    result = runner.invoke(cli, ["-c", str(config), "site", "export", "nope"])
    assert result.exit_code != 0
    assert "known sites: lab" in result.output


def _commit(repo: Path) -> None:
    for command in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "pack"],
    ):
        subprocess.run(["git", "-C", str(repo), *command], check=True)


def test_add_refuses_a_git_url_that_names_no_usable_site(runner, tmp_path, home):
    # The URL's last segment, `..`, would name the folder above the packs.
    repo = _pack(tmp_path, "repo")
    (repo / "sub").mkdir()
    (repo / "sub" / "keep").write_text("")
    _commit(repo)
    kept = home / ".dotbot" / "dotbot.toml"
    kept.parent.mkdir()
    kept.write_text("")
    url = f"git+{repo.as_uri()}/sub/.."
    result = runner.invoke(cli, ["site", "add", url, "--force"])
    assert result.exit_code != 0
    assert "site name '..'" in result.output
    assert kept.is_file()


def test_add_refuses_a_zip_whose_name_is_not_a_site_name(runner, tmp_path, home):
    archive = tmp_path / "my lab.zip"
    with zipfile.ZipFile(archive, "w") as opened:
        opened.writestr("site.toml", 'anchor = "a corner"\n')
    result = runner.invoke(cli, ["site", "add", str(archive)])
    assert result.exit_code != 0 and "site name 'my lab'" in result.output
    assert not (home / ".dotbot" / "sites").exists()


def test_add_refuses_a_pack_holding_links(runner, tmp_path, home):
    secret = tmp_path / "secret.toml"
    secret.write_text("private = true\n")
    pack = _pack(tmp_path / "shared", "linked", calibration=True)
    try:
        (pack / "calibrations" / "stolen.toml").symlink_to(secret)
    except OSError:
        pytest.skip("this machine cannot create symbolic links")
    result = runner.invoke(cli, ["site", "add", str(pack)])
    assert result.exit_code != 0
    assert "holds links" in result.output and "stolen.toml" in result.output
    assert not (home / ".dotbot" / "sites" / "linked").exists()


def test_add_refuses_git_transports_that_run_commands(runner, tmp_path, home):
    marker = tmp_path / "ran"
    result = runner.invoke(
        cli, ["site", "add", f"git+ext::sh -c touch% {marker.as_posix()}"]
    )
    assert result.exit_code != 0 and "git clone" in result.output
    assert not marker.exists()
