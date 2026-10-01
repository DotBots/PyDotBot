# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot site` - the places you work in, and which one is active.

A site pack is a folder holding `site.toml` and optionally `calibrations/`
(`dotbot.site_packs`). `add` copies one into ~/.dotbot/sites/, where every
folder finds it; `init` writes one around a spin calibration's robots; `use`
makes a site the active one; `list` and `show` read; `export` writes one as a
zip; `new` and `edit` open the site editor on a pack. The same folders can be
shared with git, cp or unzip.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import click

from dotbot.cli import _config_write as cw
from dotbot.cli._site import SITE_ENV, active_site
from dotbot.config import ConfigError
from dotbot.site import PACK_CALIBRATIONS, SITE_MARGIN_MM, check_site_name
from dotbot.site_packs import (
    PACK_FILE,
    read_approval,
    read_pack,
    resolve_site_entry,
    site_catalog,
    site_homes,
    user_sites_dir,
    write_approval,
)

_GIT_PREFIXES = ("git@", "git://", "ssh://", "git+")


@click.group(
    name="site",
    help=(
        "The places you work in: add a site pack, switch with use, "
        "list / show, export one to share, new / edit to draw one."
    ),
)
def cmd():
    pass


def _catalog(ctx):
    obj = ctx.obj or {}
    try:
        return site_catalog(obj.get("config"))
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _connection(table):
    """A site table's (conn, swarm_id), each None when unset."""
    connection = getattr(table, "connection", None)
    if connection is None:
        return None, None
    return connection.conn, connection.swarm_id


def write_active_site(ctx, name: str, table=None, where: str | None = None) -> Path:
    """Write `site = "<name>"` to your own config file: dotbot.local.toml
    beside the project's dotbot.toml when one is in use, else the user file;
    `where` (`user` / `project`) picks one.

    Comments and the rest of the file are kept. Warns when a higher file or
    the environment overrides the site, or its connection.
    """
    obj = ctx.obj or {}
    config = obj.get("config")
    try:
        target = cw.target(config, ("site",), where)
        cw.set_value(target, ("site",), name)
    except cw.WriteError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'wrote site = "{name}" to {target}')
    project = getattr(config, "project_path", None)
    if project is not None and target.resolve() == Path(project).resolve():
        click.echo(
            f"note: {target.name} is the project's file, so the change shows "
            "in git status",
            err=True,
        )
    for phrase in cw.hiders(config, target, ("site",)):
        if phrase != f"{SITE_ENV} is set":
            click.echo(f"warning: {phrase}, which overrides it", err=True)
    if os.environ.get(SITE_ENV) and os.environ[SITE_ENV] != name:
        click.echo(
            f"warning: {SITE_ENV}={os.environ[SITE_ENV]} overrides it; unset "
            f"{SITE_ENV} to work in {name}",
            err=True,
        )
    for key, value in zip(("conn", "swarm_id"), _connection(table)):
        if value is None:
            continue
        phrases = [
            f"{item.label} sets {key}"
            for item in getattr(config, "files", ())
            if cw.lookup(item.data, (key,)) is not None
        ]
        env = f"DOTBOT_{key.upper()}"
        if env in os.environ:
            phrases.append(f"{env} is set")
        for phrase in phrases:
            click.echo(
                f"warning: {phrase}, which hides {name}'s {key}; "
                f"`dotbot config unset {key}` to follow the site",
                err=True,
            )
    return target


@cmd.command()
@click.argument("name")
@cw.where_options(
    "Change the project's default in its dotbot.toml, which is committed."
)
@click.pass_context
def use(ctx, name, where):
    """Make NAME the active site.

    Writes site = NAME to dotbot.local.toml beside the project's dotbot.toml
    when one is in use, else to ~/.dotbot/dotbot.toml; --user and --project
    pick the file. NAME is a site pack in sites/ beside the project file or
    in ~/.dotbot/sites, or a pack folder's path.
    """
    from dotbot.site_packs import is_pack_path, pack_at

    if is_pack_path(name):
        try:
            entry = pack_at(name)
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
        try:
            target = cw.target((ctx.obj or {}).get("config"), ("site",), where)
        except cw.WriteError as exc:
            raise click.ClickException(str(exc)) from exc
        name = cw.path_value(("site",), name, target)
    else:
        catalog = _catalog(ctx)
        entry = catalog.get(name)
        if entry is None:
            known = ", ".join(sorted(catalog)) or "(none)"
            raise click.ClickException(f"unknown site {name!r}; known sites: {known}")
    write_active_site(ctx, name, entry.table, where)


def _where(entry) -> str:
    return entry.source


@cmd.command(name="list")
@click.pass_context
def list_sites(ctx):
    """List the sites the config can name, marking the active one (*), with
    each one's connection and where it was read from."""
    catalog = _catalog(ctx)
    if not catalog:
        click.echo("(no sites; add one with `dotbot site add` or `dotbot config init`)")
        return
    active = active_site(ctx).entry
    width = max(len(name) for name in catalog)
    conns = {
        name: _connection(entry.table)[0] or "-" for name, entry in catalog.items()
    }
    conn_width = max(len(conn) for conn in conns.values())
    for name, entry in catalog.items():
        marker = (
            "*"
            if active is not None and entry.pack.resolve() == active.pack.resolve()
            else " "
        )
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
    current = active_site(ctx)
    active = current.entry
    if name is None and active is None and current.source == "the default":
        raise click.ClickException(
            "no site is active; `dotbot site use <name>` picks one, and "
            "`dotbot site list` names them"
        )
    if name is None and active is not None:
        entry = active
    else:
        name = name or current.name
        entry = _catalog(ctx).get(name)
    if entry is None:
        raise click.ClickException(
            f"unknown site {name!r}; `dotbot site list` names the known ones"
        )
    name = entry.name
    is_active = active is not None and entry.pack.resolve() == active.pack.resolve()
    table = entry.table
    click.echo(f"site:        {name}{' (active)' if is_active else ''}")
    click.echo(f"defined in:  {_where(entry)}")
    if table.anchor:
        click.echo(f"anchor:      {table.anchor}")
    if table.extent_mm:
        click.echo(f"extent:      {table.extent_mm[0]} x {table.extent_mm[1]} mm")
    conn, swarm_id = _connection(table)
    click.echo(f"connection:  {conn or '(none)'}")
    if conn is not None:
        click.echo(f"swarm id:    {swarm_id or '(none in the pack)'}")
    if is_active and conn is not None and swarm_id is None:
        from dotbot.config import resolve_source

        yours = resolve_source(
            "swarm_id", config=(ctx.obj or {}).get("config"), site=current.layer
        )
        click.echo(
            f"             yours: {yours.value} (from {yours.source})"
            if yours.value is not None
            else "             yours: none; `dotbot config set swarm_id <id>`"
        )
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
    later differs, that login is withheld until the site is added again. A
    login saved with `dotbot config login HOST` needs no approval: only
    that host's broker gets it.
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
    _hint_login(ctx, new[0])


def _hint_login(ctx, conn: str | None) -> None:
    """Say how to save a login for the pack's broker when none is saved."""
    from urllib.parse import urlparse

    from dotbot.mqtt_tls import LOCAL_HOSTS

    if conn is None or not conn.strip().lower().startswith("mqtts://"):
        return
    host = (urlparse(conn.strip()).hostname or "").lower()
    config = (ctx.obj or {}).get("config")
    saved = {name.lower() for name in getattr(config, "login", {}) or {}}
    if host and host not in LOCAL_HOSTS and host not in saved:
        click.echo(f"If its broker needs a login: dotbot config login {host}")


def _warn_if_shadowed(ctx, name: str, target: Path) -> bool:
    """Warn, and return True, when site `name` resolves to a pack other than
    the one just installed at `target`."""
    obj = ctx.obj or {}
    try:
        entry = resolve_site_entry(obj.get("config"), name)
    except ConfigError:
        return False
    if entry is None or entry.pack.resolve() == target.resolve():
        return False
    click.echo(
        f"warning: the project's site pack {entry.pack} hides this one; "
        f"rename the pack folder to add it under another name",
        err=True,
    )
    return True


def _files(count: int) -> str:
    return f"{count} calibration file{'' if count == 1 else 's'}"


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

    NAME is a site pack in one of the two homes.
    """
    from dotbot.calibration.lighthouse2 import calibration_root

    obj = ctx.obj or {}
    try:
        catalog = site_catalog(obj.get("config"))
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

    site_toml = (entry.pack / PACK_FILE).read_bytes()
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


def _parse_size(_ctx, _param, value):
    if value is None:
        return None
    try:
        width, height = (int(v) for v in value.lower().split("x"))
    except ValueError as exc:
        raise click.BadParameter("takes a width and a height in mm, `WxH`") from exc
    if width <= 0 or height <= 0:
        raise click.BadParameter("takes a positive width and height")
    return (width, height)


def _render_site_pack(site, source_id8: str) -> str:
    def area(name: str, note: str) -> str:
        a = site.registry().resolve(name)
        key = json.dumps(name) if "+" in name else name
        return f"[areas.{key}]   # {note}\nx = {a.x}\ny = {a.y}\nw = {a.w}\nh = {a.h}\n"

    width, height = site.extent_mm
    return (
        f"# Site {site.name}: written by `dotbot site init` from spin calibration\n"
        f"# {source_id8}. The frame's zero is the anchor, x right, y down, mm.\n"
        "\n"
        f"anchor = {json.dumps(site.anchor)}\n"
        f"extent_mm = [{width}, {height}]\n"
        "\n"
        + area("field", "where the robots spun, grown by a robot's footprint")
        + "\n"
        + area("staging", "where robots park, along the field's bottom edge")
        + "\n"
        + area("field+staging", "the field and staging together")
    )


def _serve_editor(name: str, pack: Path, port: int, headless: bool) -> None:
    """Serve the editor on `pack` at 127.0.0.1 until Ctrl-C or Done."""
    import socket
    import threading
    import webbrowser

    import uvicorn

    from dotbot.calibration.lighthouse2 import calibration_root
    from dotbot.site_editor import EDITOR_DIR, EDITOR_PAGE, EditorState, create_app

    if not (EDITOR_DIR / EDITOR_PAGE).is_file():
        raise click.ClickException(
            f"the site editor page is not built ({EDITOR_DIR / EDITOR_PAGE} is "
            "missing). Build it with: npm --prefix dotbot/console-web install && "
            "npm --prefix dotbot/console-web run build"
        )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        sock.close()
        raise click.ClickException(f"cannot listen on 127.0.0.1:{port}: {exc}") from exc
    sock.listen()
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
    state = EditorState(name, pack, [calibration_root() / name])
    server = None

    def done():
        server.should_exit = True

    app = create_app(state, on_done=done)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    click.echo(f"Editing site {name} ({pack / PACK_FILE})")
    click.echo(f"Site editor at {url} - Ctrl-C or Done to stop")
    if not headless:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()


_PORT = click.option(
    "--port",
    type=int,
    default=0,
    show_default="a free port",
    help="Port on 127.0.0.1 to serve the editor on.",
)
_HEADLESS = click.option(
    "--headless", is_flag=True, help="Print the editor's URL; don't open a browser."
)


@cmd.command()
@click.argument("name")
@click.option(
    "--from-calibration",
    "calibration",
    required=True,
    metavar="ID",
    help=(
        "The spin calibration (`dotbot swarm calibrate-lh2 collect --spin`) "
        "whose robots define the field: an id prefix, a tag or a path."
    ),
)
@click.option(
    "--size",
    default=None,
    callback=_parse_size,
    metavar="WxH",
    help=(
        "Make the site this many mm wide and high, with the field in its "
        "middle and staging below it (e.g. 3000x4000). Default: the field "
        f"with {SITE_MARGIN_MM} mm of floor round it."
    ),
)
@click.option(
    "--force", "-f", is_flag=True, help="Replace the site.toml of a site of that name."
)
@click.pass_context
def init(ctx, name, calibration, size, force):
    """Write a site pack NAME around the robots of a spin calibration.

    The field is the minimum-area rectangle around the robots' spin centres,
    grown by what a spinning robot sweeps; the calibration's frame is aligned
    to it, zero at its top-left. The site is the starter site `config init`
    writes, around that field: a margin of floor round it (or a --size site
    with it centred), a staging strip along its bottom edge, and a
    field+staging area spanning both. The pack goes into the nearest site
    home (sites/ beside the project's dotbot.toml, else ~/.dotbot/sites/),
    and the calibration, re-expressed in the site, under
    ~/.dotbot/calibrations/NAME/, its tag suffixed with -NAME.
    """
    from dotbot.calibration.conics import self_defined_site
    from dotbot.calibration.lighthouse2 import (
        read_calibration_file,
        resolve_calibration_path,
        site_name_as_bytes,
        write_calibration,
    )
    from dotbot.cli._swarm_inject import swarm_connection

    obj = ctx.obj or {}
    config = obj.get("config")
    try:
        check_site_name(name)
        site_name_as_bytes(name)  # the push carries the name to the robots
        existing = resolve_site_entry(config, name)
    except (ValueError, ConfigError) as exc:
        raise click.ClickException(str(exc)) from exc
    _, home = site_homes(config)[0]
    target = home / name
    if existing is not None:
        if not force:
            raise click.ClickException(
                f"site {name} already exists ({existing.pack}). Pass --force to "
                "replace its site.toml, or pick another name."
            )
        target = existing.pack
    entry = active_site(ctx).entry
    try:
        try:
            path = resolve_calibration_path(
                calibration, site=entry.site() if entry else None
            )
        except ValueError:
            path = resolve_calibration_path(calibration)
        source = read_calibration_file(path)
        site, placed = self_defined_site(source, name, size)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    saved = write_calibration(placed)
    target.mkdir(parents=True, exist_ok=True)
    (target / PACK_FILE).write_text(
        _render_site_pack(site, source.id8), encoding="utf-8"
    )
    field, staging = site.areas["field"], site.areas["staging"]
    click.echo(f"Wrote site {name} to {target / PACK_FILE}")
    click.echo(
        f"  extent {site.extent_mm[0]} x {site.extent_mm[1]} mm, field "
        f"{field.w} x {field.h} mm at ({field.x}, {field.y}), staging "
        f"{staging.w} x {staging.h} mm below it"
    )
    click.echo(f"Calibration {placed.id8} (from {source.id8}) saved to {saved}")
    robots = ",".join(sorted({t.name for t in placed.tracks})) or "<addresses>"
    conn = swarm_connection(obj)[0].value
    conn_flag = f"-n {conn} " if conn else ""
    click.echo(
        "Next, send it to the robots (--site-changed: they report the site "
        "they were calibrated in), then work in the site:\n"
        f"  dotbot swarm -d {robots} calibrate-lh2 push {placed.id8} "
        f"--site {name} --site-changed\n"
        f"  dotbot run controller {conn_flag}--site {name} "
        f"--lh2-calibration {placed.id8} "
        "--headless"
    )


@cmd.command()
@click.argument("name")
@click.option(
    "--field",
    "field_spec",
    default="2m",
    show_default=True,
    help="The starter field, as for `dotbot config init`: 2m, 2x3m, 1500mm.",
)
@_PORT
@_HEADLESS
@click.pass_context
def new(ctx, name, field_spec, port, headless):
    """Write a new site pack, then open the editor on it.

    The pack goes in sites/NAME/ beside the project's dotbot.toml when one is
    in use, else in ~/.dotbot/sites/NAME/, so `dotbot site use NAME` finds it
    at once. It starts as `dotbot config init` starts a site: a field with
    floor round it and a staging strip below. It is not made the active site.
    """
    from dotbot.cli.config_cmd import default_site_toml, parse_field_size
    from dotbot.site_packs import site_homes

    try:
        check_site_name(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    field_mm = parse_field_size(field_spec)
    _, home = site_homes((ctx.obj or {}).get("config"))[0]
    target = home / name
    if target.exists():
        raise click.ClickException(f"{target} already exists")
    target.mkdir(parents=True)
    (target / PACK_FILE).write_text(default_site_toml(field_mm))
    click.echo(f"Wrote {target / PACK_FILE}")
    _serve_editor(name, target, port, headless)
    click.echo(f"Work in it with `dotbot site use {name}`, or --site {name}.")


@cmd.command()
@click.argument("site", required=False)
@_PORT
@_HEADLESS
@click.pass_context
def edit(ctx, site, port, headless):
    """Open the site editor on a site pack, at 127.0.0.1.

    SITE is a site name or a pack folder's path; it defaults to the active
    site.
    """
    from dotbot.site_packs import is_pack_path, pack_at

    if site is not None and is_pack_path(site):
        try:
            entry = pack_at(site)
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
        _serve_editor(entry.name, entry.pack, port, headless)
        return
    if site is None:
        active = active_site(ctx)
        if active.entry is not None:
            _serve_editor(active.name, active.entry.pack, port, headless)
            return
        site = active.name
    name = site
    entry = _catalog(ctx).get(name)
    if entry is None:
        raise click.ClickException(
            f"unknown site {name!r}; `dotbot site list` names the known ones, "
            "and `dotbot site new` makes one"
        )
    _serve_editor(name, entry.pack, port, headless)
