# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot site` - the places you work in, and which one is active.

A site pack is a folder holding `site.toml` and optionally `calibrations/`
(`dotbot.site_packs`). `add` copies one into ~/.dotbot/sites/, where every
config finds it; `use` makes a site the active one; `list` and `show` read;
`export` writes one as a zip, from a pack or from an inline `[sites.<name>]`
table. The same folders can be shared with git, cp or unzip.
"""

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import click
import tomlkit

from dotbot import config as _config
from dotbot.cli._site import SITE_ENV, active_site, config_label
from dotbot.config import ConfigError
from dotbot.site import PACK_CALIBRATIONS, check_site_name
from dotbot.site_packs import (
    PACK_FILE,
    read_approval,
    read_pack,
    resolve_site_entry,
    site_catalog,
    user_sites_dir,
    write_approval,
)

_GIT_PREFIXES = ("git@", "git://", "ssh://", "git+")


@click.group(
    name="site",
    help=(
        "The places you work in: add a site pack, switch with use, "
        "list / show, export one to share."
    ),
)
def cmd():
    pass


def _catalog(ctx):
    obj = ctx.obj or {}
    try:
        return site_catalog(obj.get("config"), obj.get("config_path"))
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _connection(table):
    """A site table's (conn, swarm_id), each None when unset."""
    connection = getattr(table, "connection", None)
    if connection is None:
        return None, None
    return connection.conn, connection.swarm_id


def _hiders(config, config_path, table) -> list[str]:
    """What in the config file or the environment overrides the site's
    connection, one phrase each."""
    phrases = []
    label = config_label(config_path)
    for key, value in zip(("conn", "swarm_id"), _connection(table)):
        if value is None:
            continue
        if config is not None:
            if getattr(config, key, None) is not None:
                phrases.append(f"{label} sets {key} at top level")
            for section in ("run", "swarm"):
                if getattr(getattr(config, section), key, None) is not None:
                    phrases.append(f"{label} sets {key} in [{section}]")
        for name in (
            f"DOTBOT_{key.upper()}",
            f"DOTBOT_RUN_{key.upper()}",
            f"DOTBOT_SWARM_{key.upper()}",
        ):
            if name in os.environ:
                phrases.append(f"{name} is set")
    return phrases


def write_active_site(ctx, name: str, table=None) -> Path:
    """Write `site = "<name>"` into the config file in use, or create the
    user config holding just that when none is.

    Comments and the rest of the file are kept. Warns when the file or the
    environment will override the site, or its connection.
    """
    obj = ctx.obj or {}
    config_path = obj.get("config_path")
    target = Path(config_path) if config_path is not None else _config.USER_CONFIG_PATH
    if target.is_file():
        document = tomlkit.parse(target.read_text())
    else:
        document = tomlkit.document()
    document["site"] = name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tomlkit.dumps(document))
    click.echo(f'wrote site = "{name}" to {target}')
    if os.environ.get(SITE_ENV) and os.environ[SITE_ENV] != name:
        click.echo(
            f"warning: {SITE_ENV}={os.environ[SITE_ENV]} overrides it; unset "
            f"{SITE_ENV} to work in {name}",
            err=True,
        )
    config = obj.get("config") if config_path is not None else None
    for phrase in _hiders(config, target, table):
        click.echo(
            f"warning: {phrase}, which overrides {name}'s connection; remove "
            "it to follow the site",
            err=True,
        )
    return target


@cmd.command()
@click.argument("name")
@click.pass_context
def use(ctx, name):
    """Make NAME the active site, writing it to the config file in use.

    That is the file `dotbot config path` reports; with none in use,
    ~/.dotbot/dotbot.toml is created. NAME is an inline [sites.<name>] table
    or a site pack.
    """
    catalog = _catalog(ctx)
    entry = catalog.get(name)
    if entry is None:
        known = ", ".join(sorted(catalog)) or "(none)"
        raise click.ClickException(f"unknown site {name!r}; known sites: {known}")
    write_active_site(ctx, name, entry.table)


def _where(entry) -> str:
    if entry.pack is not None:
        return str(entry.pack)
    return "inline" + (f", shadowing {entry.shadows}" if entry.shadows else "")


@cmd.command(name="list")
@click.pass_context
def list_sites(ctx):
    """List the sites the config can name, marking the active one (*), with
    each one's connection and where it was read from."""
    catalog = _catalog(ctx)
    if not catalog:
        click.echo("(no sites; add one with `dotbot site add` or `dotbot config init`)")
        return
    active = active_site(ctx).name
    width = max(len(name) for name in catalog)
    conns = {
        name: _connection(entry.table)[0] or "-" for name, entry in catalog.items()
    }
    conn_width = max(len(conn) for conn in conns.values())
    for name, entry in catalog.items():
        marker = "*" if name == active else " "
        click.echo(
            f"{marker} {name:<{width}}  {conns[name]:<{conn_width}}  {_where(entry)}"
        )


def _echo_areas(entry) -> None:
    """One line per area of a site: its name and its role, saying when the
    role is implied by the name."""
    declared = entry.table.areas
    areas = entry.site().areas
    if not areas:
        return
    click.echo("areas:")
    width = max(len(name) for name in areas)
    for name, area in areas.items():
        if area.role is None:
            role = "no role"
        elif declared[name].role is None:
            role = f"{area.role} (from its name)"
        else:
            role = area.role
        click.echo(f"  {name:<{width}}  {role}")


def _calibration_folders(entry) -> list[Path]:
    from dotbot.calibration.lighthouse2 import calibration_root

    site = entry.site()
    folders = [site.pack_calibrations, calibration_root() / entry.name]
    return [folder for folder in folders if folder is not None]


@cmd.command()
@click.argument("name", required=False)
@click.pass_context
def show(ctx, name):
    """Print one site: where it is defined, its anchor, extent, connection,
    areas and calibrations. NAME defaults to the active site."""
    active = active_site(ctx).name
    name = name or active
    entry = _catalog(ctx).get(name)
    if entry is None:
        raise click.ClickException(
            f"unknown site {name!r}; `dotbot site list` names the known ones"
        )
    table = entry.table
    click.echo(f"site:        {name}{' (active)' if name == active else ''}")
    click.echo(f"defined in:  {_where(entry)}")
    if table.anchor:
        click.echo(f"anchor:      {table.anchor}")
    if table.extent_mm:
        click.echo(f"extent:      {table.extent_mm[0]} x {table.extent_mm[1]} mm")
    conn, swarm_id = _connection(table)
    click.echo(f"connection:  {conn or '(none)'}")
    if conn is not None:
        click.echo(f"swarm id:    {swarm_id or '(none; set swarm_id yourself)'}")
    _echo_areas(entry)
    click.echo("calibrations:")
    for folder in _calibration_folders(entry):
        count = len(list(folder.glob("*.toml"))) if folder.is_dir() else 0
        click.echo(f"  {_files(count):<20}  {folder}")


def _is_git_url(source: str) -> bool:
    return source.startswith(_GIT_PREFIXES) or (
        source.startswith(("https://", "http://")) and not source.endswith(".zip")
    )


def _pack_in(folder: Path, name: str | None) -> tuple[Path, str]:
    """The pack in an unpacked folder: the folder itself, or its one sub-folder.

    With no `name`, as for a zip read from stdin, only the sub-folder can
    name the site.
    """
    children = [child for child in folder.iterdir() if child.is_dir()]
    if (folder / PACK_FILE).is_file():
        if name is None:
            raise click.ClickException(
                f"the zip on stdin holds {PACK_FILE} at its root, so nothing "
                f"names its site: zip the pack folder itself, as `site export` does"
            )
        return folder, name
    if len(children) == 1 and (children[0] / PACK_FILE).is_file():
        return children[0], children[0].name
    raise click.ClickException(f"no {PACK_FILE} found in {name or 'the zip on stdin'}")


def _unzip(path: Path, scratch: Path, name: str | None) -> tuple[Path, str]:
    target = scratch / "unzipped"
    with zipfile.ZipFile(path) as archive:
        archive.extractall(target)
    return _pack_in(target, name)


def _read_stdin(scratch: Path) -> Path:
    """The zip piped to stdin, saved under `scratch`."""
    stdin = click.get_binary_stream("stdin")
    if stdin.isatty():
        raise click.ClickException(
            "`site add -` reads a zip from stdin, and stdin is a terminal; "
            "pipe one in: curl -L <url> | dotbot site add -"
        )
    path = scratch / "stdin.zip"
    with open(path, "wb") as handle:
        shutil.copyfileobj(stdin, handle)
    if not zipfile.is_zipfile(path):
        raise click.ClickException("what came in on stdin is not a zip file")
    return path


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
    if source == "-":
        return _unzip(_read_stdin(scratch), scratch, None)
    if _is_git_url(source):
        url = source.removeprefix("git+")
        target = scratch / "clone"
        _git_clone(url, target)
        name = re.split(r"[/:]", url.rstrip("/"))[-1].removesuffix(".git")
        return _pack_in(target, name)
    if source.startswith(("https://", "http://")):
        raise click.ClickException(
            f"{source} is a zip on the web: download it first, or pipe it: "
            f"curl -L {source} | dotbot site add -"
        )
    path = Path(source).expanduser()
    if path.is_dir():
        return _pack_in(path, path.resolve().name)
    if path.is_file() and zipfile.is_zipfile(path):
        return _unzip(path, scratch, path.stem)
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


def _install(folder: Path, target: Path, approved: str | None) -> None:
    """Copy the pack in `folder` to `target`, replacing any pack there, and
    record `approved` as its approved broker.

    The copy lands in a hidden sibling of `target` first and is renamed into
    place, so a failure leaves whatever was at `target` as it was.
    """
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=parent))
    aside = None
    try:
        shutil.copy2(folder / PACK_FILE, staging / PACK_FILE)
        calibrations = folder / PACK_CALIBRATIONS
        if calibrations.is_dir():
            shutil.copytree(calibrations, staging / PACK_CALIBRATIONS)
        if approved is not None:
            write_approval(staging, approved)
        if target.exists():
            old = staging.with_name(f"{staging.name}-old")
            target.rename(old)
            aside = old
        staging.rename(target)
    except BaseException:
        if aside is not None and not target.exists():
            aside.rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if aside is not None:
        shutil.rmtree(aside, ignore_errors=True)


def _approved_connection(target: Path):
    """The installed pack's (approved broker, swarm id), or None when it
    has no approved broker to compare a re-add against."""
    approved = read_approval(target)
    if approved is None:
        return None
    try:
        return approved, _connection(read_pack(target))[1]
    except ConfigError:
        return approved, None


def _ask(question: str, from_stdin: bool) -> bool:
    """A yes/no question, on the terminal when stdin carried the pack."""
    if not from_stdin:
        return click.confirm(question, default=False, err=True)
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write(f"{question} [y/N]: ")
            tty.flush()
            answer = tty.readline()
    except OSError as exc:
        raise click.ClickException(
            "the pack came in on stdin, so there is no terminal to ask on; "
            "pass --yes to accept its connection"
        ) from exc
    return answer.strip().lower() in ("y", "yes")


def _plain_remote(conn: str | None) -> bool:
    """Whether `conn` is a plain mqtt:// broker on another machine."""
    from urllib.parse import urlparse

    from dotbot.mqtt_tls import LOCAL_HOSTS

    if conn is None or not conn.strip().lower().startswith("mqtt://"):
        return False
    return urlparse(conn.strip()).hostname not in LOCAL_HOSTS


def _confirm_connection(name, new, old, from_stdin) -> bool:
    """Show the broker and swarm id a pack brings, or how a re-add changes
    them, and ask; True when there is nothing to ask about, which includes the
    simulator."""
    if new == old or new == (None, None):
        return True
    if new[0] is not None and new[0].strip().lower() in ("simulator", "sim"):
        return True
    rows = (("broker", 0), ("swarm id", 1))
    if old is None or old == (None, None):
        click.echo(f"Site pack {name} names its connection:", err=True)
        for label, i in rows:
            click.echo(
                f"  {label + ':':<10} {new[i] or '(none; set swarm_id yourself)'}",
                err=True,
            )
    else:
        click.echo(f"Site pack {name} changes its connection:", err=True)
        for label, i in rows:
            click.echo(
                f"  {label + ':':<10} {old[i] or '(none)'} -> {new[i] or '(none)'}",
                err=True,
            )
    login = (
        "never send it DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS, as plain mqtt:// "
        "would carry them unencrypted"
        if _plain_remote(new[0])
        else "send it DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS when they are set"
    )
    click.echo(
        f"Commands in {name} will connect there unless you set conn yourself, "
        f"and {login}.",
        err=True,
    )
    return _ask(f"Add site {name}?", from_stdin)


@cmd.command()
@click.argument("source")
@click.option("--force", "-f", is_flag=True, help="Replace a pack of the same name.")
@click.option(
    "--use",
    "use_",
    is_flag=True,
    help="Make it the active site too, as `dotbot site use` does.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask before adding a pack that names a connection.",
)
@click.pass_context
def add(ctx, source, force, use_, yes):
    """Copy the site pack SOURCE into ~/.dotbot/sites/.

    SOURCE is a pack folder, a zip of one (as `site export` writes), `-` for
    such a zip on stdin, or a git URL whose repository is one. The folder's
    name is the site's name. A pack naming a broker shows it and asks first,
    and asks again when a re-add changes it. Approving it trusts that broker
    with DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS; if the installed pack's broker
    later differs, the login is withheld until the site is added again.
    """
    with tempfile.TemporaryDirectory() as scratch:
        folder, name = _fetch(source, Path(scratch))
        _check_pack(folder, name)
        target = user_sites_dir() / name
        if target.exists() and not force:
            raise click.ClickException(
                f"{target} already exists. Pass --force to replace it."
            )
        table = read_pack(folder)
        old = _approved_connection(target)
        new = _connection(table)
        if not yes and not _confirm_connection(name, new, old, source == "-"):
            click.echo(f"Site {name} not added.", err=True)
            ctx.exit(1)
        _install(folder, target, new[0].strip() if new[0] else None)
    count = len(list((target / PACK_CALIBRATIONS).glob("*.toml")))
    click.echo(f"Added site {name} to {target} ({_files(count)})")
    shadowed = _warn_if_shadowed(ctx, name, target)
    if use_:
        write_active_site(ctx, name, table)
    elif not shadowed:
        click.echo(f"Work in it with `dotbot site use {name}`, or --site {name}.")


def _warn_if_shadowed(ctx, name: str, target: Path) -> bool:
    """Warn, and return True, when the config in use reads site `name` from
    somewhere other than the pack just installed at `target`."""
    obj = ctx.obj or {}
    config_path = obj.get("config_path")
    try:
        entry = resolve_site_entry(obj.get("config"), config_path, name)
    except ConfigError:
        return False
    if entry is None or (
        entry.pack is not None and entry.pack.resolve() == target.resolve()
    ):
        return False
    where = config_path or "the config in use"
    click.echo(
        f"warning: {where} reads site {name} from {_where(entry)}, "
        f"not from this pack; rename the pack folder to add it under "
        f"another name",
        err=True,
    )
    return True


def _files(count: int) -> str:
    return f"{count} calibration file{'' if count == 1 else 's'}"


def _site_toml(table) -> str:
    """An inline `[sites.<name>]` table as a pack's `site.toml`."""
    data = table.model_dump(exclude_none=True)
    document = tomlkit.document()
    for key in ("anchor", "extent_mm"):
        if key in data:
            document[key] = data[key]
    if data.get("connection"):
        connection = tomlkit.table()
        connection.update(data["connection"])
        document["connection"] = connection
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
        + (f" and {_files(len(calibrations))}" if with_calibrations else "")
    )
