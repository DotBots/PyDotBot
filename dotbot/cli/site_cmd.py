# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot site` - add and export site packs.

A site pack is a folder holding `site.toml` and optionally `calibrations/`
(`dotbot.site_packs`). `add` copies one into ~/.dotbot/sites/, where every
config finds it; `export` writes one as a zip, from a pack or from an inline
`[sites.<name>]` table. The same folders can be shared with git, cp or unzip.
"""

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import click
import tomlkit

from dotbot.config import ConfigError
from dotbot.site import PACK_CALIBRATIONS, check_site_name
from dotbot.site_packs import PACK_FILE, read_pack, site_catalog, user_sites_dir

_GIT_PREFIXES = ("git@", "git://", "ssh://", "git+")


@click.group(
    name="site",
    help="Add a site pack to this machine, or export one to share.",
)
def cmd():
    pass


def _is_git_url(source: str) -> bool:
    return source.startswith(_GIT_PREFIXES) or (
        source.startswith(("https://", "http://")) and not source.endswith(".zip")
    )


def _pack_in(folder: Path, name: str) -> tuple[Path, str]:
    """The pack in an unpacked folder: the folder itself, or its one sub-folder."""
    if (folder / PACK_FILE).is_file():
        return folder, name
    children = [child for child in folder.iterdir() if child.is_dir()]
    if len(children) == 1 and (children[0] / PACK_FILE).is_file():
        return children[0], children[0].name
    raise click.ClickException(f"no {PACK_FILE} found in {name}")


def _git_clone(url: str, target: Path) -> None:
    """A shallow clone of `url`; git's `ext::` transport, which runs a
    command, is refused."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "protocol.ext.allow=never",
            "clone",
            "--depth",
            "1",
            "--",
            url,
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise click.ClickException(f"git clone {url} failed:\n{result.stderr.strip()}")


def _fetch(source: str, scratch: Path) -> tuple[Path, str]:
    """The pack folder SOURCE names, and its site name."""
    if _is_git_url(source):
        url = source.removeprefix("git+")
        target = scratch / "clone"
        _git_clone(url, target)
        name = re.split(r"[/:]", url.rstrip("/"))[-1].removesuffix(".git")
        return _pack_in(target, name)
    path = Path(source).expanduser()
    if path.is_dir():
        return _pack_in(path, path.resolve().name)
    if path.is_file() and zipfile.is_zipfile(path):
        target = scratch / "unzipped"
        with zipfile.ZipFile(path) as archive:
            archive.extractall(target)
        return _pack_in(target, path.stem)
    raise click.ClickException(
        f"{source} is neither a folder, a zip file nor a git URL"
    )


def _check_pack(folder: Path, name: str) -> None:
    """Refuse a pack with an unusable name, a link in it, or an invalid
    `site.toml`."""
    try:
        check_site_name(name)
    except ValueError as exc:
        raise click.ClickException(
            f"{exc}; rename the pack folder (or the repository) to its site's name"
        ) from exc
    calibrations = folder / PACK_CALIBRATIONS
    paths = [folder / PACK_FILE, calibrations]
    if calibrations.is_dir() and not calibrations.is_symlink():
        paths += list(calibrations.rglob("*"))
    links = [path for path in paths if path.is_symlink()]
    if links:
        raise click.ClickException(
            f"the site pack {name} holds links, which are not copied: "
            + ", ".join(str(path.relative_to(folder)) for path in links)
        )
    try:
        read_pack(folder)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


@cmd.command()
@click.argument("source")
@click.option("--force", "-f", is_flag=True, help="Replace a pack of the same name.")
def add(source, force):
    """Copy the site pack SOURCE into ~/.dotbot/sites/.

    SOURCE is a pack folder, a zip of one (as `site export` writes) or a git
    URL whose repository is one. The folder's name is the site's name.
    """
    with tempfile.TemporaryDirectory() as scratch:
        folder, name = _fetch(source, Path(scratch))
        _check_pack(folder, name)
        target = user_sites_dir() / name
        if target.exists():
            if not force:
                raise click.ClickException(
                    f"{target} already exists. Pass --force to replace it."
                )
            shutil.rmtree(target)
        target.mkdir(parents=True)
        shutil.copy2(folder / PACK_FILE, target / PACK_FILE)
        calibrations = folder / PACK_CALIBRATIONS
        if calibrations.is_dir():
            shutil.copytree(calibrations, target / PACK_CALIBRATIONS)
    count = len(list((target / PACK_CALIBRATIONS).glob("*.toml")))
    click.echo(f"Added site {name} to {target} ({count} calibration files)")
    click.echo(f'Work in it with `site = "{name}"` in your config, or --site {name}.')


def _site_toml(table) -> str:
    """An inline `[sites.<name>]` table as a pack's `site.toml`."""
    data = table.model_dump(exclude_none=True)
    document = tomlkit.document()
    for key in ("anchor", "extent_mm"):
        if key in data:
            document[key] = data[key]
    areas = tomlkit.table()
    for area_name, area in data.get("areas", {}).items():
        inline = tomlkit.inline_table()
        inline.update(area)
        areas[area_name] = inline
    if areas:
        document["areas"] = areas
    return tomlkit.dumps(document)


@cmd.command()
@click.argument("name")
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="The zip to write. Default: <name>.zip in the current directory.",
)
@click.option(
    "--with-calibrations",
    is_flag=True,
    help="Include the site's calibration files, from its pack and from "
    "~/.dotbot/calibrations/<name>/.",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite an existing zip.")
@click.pass_context
def export(ctx, name, out_path, with_calibrations, force):
    """Write the site NAME as a site pack zip.

    NAME is an inline [sites.<name>] table of the config or a site pack.
    """
    from dotbot.calibration.lighthouse2 import calibration_root

    obj = ctx.obj or {}
    try:
        catalog = site_catalog(obj.get("config"), obj.get("config_path"))
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    entry = catalog.get(name)
    if entry is None:
        known = ", ".join(sorted(catalog)) or "(none)"
        raise click.ClickException(f"unknown site {name!r}; known sites: {known}")
    try:
        check_site_name(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    target = Path(out_path or f"{name}.zip")
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Pass --force to overwrite it."
        )

    if entry.pack is not None:
        site_toml = (entry.pack / PACK_FILE).read_bytes()
    else:
        site_toml = _site_toml(entry.table).encode()
    calibrations: dict[str, Path] = {}
    if with_calibrations:
        site = entry.site()
        folders = [site.pack_calibrations, calibration_root() / name]
        for folder in folders:
            if folder is not None and folder.is_dir():
                for path in sorted(folder.glob("*.toml")):
                    calibrations.setdefault(path.name, path)

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}/{PACK_FILE}", site_toml)
        for file_name, path in calibrations.items():
            archive.write(path, f"{name}/{PACK_CALIBRATIONS}/{file_name}")
    click.echo(
        f"Wrote {target}: site {name}"
        + (f" and {len(calibrations)} calibration files" if with_calibrations else "")
    )
