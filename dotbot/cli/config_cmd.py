# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot config` - scaffold, inspect and change the dotbot configuration.

A management group (like `git config`): `init` scaffolds a site and the keys
that select it; `path` and `show` read what the root group merged onto the
Click context (`ctx.obj["config"]`); `set`, `unset` and `login` change one
key, in an untracked file unless told otherwise (`dotbot.cli._config_write`).
"""

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import click
import tomlkit

from dotbot import config as _config
from dotbot.cli import _config_write as cw
from dotbot.cli._site import active_site, credentials_for
from dotbot.config import display_path, resolve_source, unknown_env
from dotbot.mqtt_tls import LOCAL_HOSTS
from dotbot.site import SITE_DEFAULT, SITE_MARGIN_MM, check_site_name, starter_layout
from dotbot.site_packs import (
    PACK_FILE,
    PROJECT_SITES_DIR,
    user_sites_dir,
    write_approval,
)

_CONFIG_DOCS_URL = (
    "https://pydotbot.readthedocs.io/en/latest/reference/configuration.html"
)


FIELD_DEFAULT_MM = (2000, 2000)
FIELD_MIN_MM = 100
FIELD_MAX_MM = 100_000
# Above this, one LH2 base station rarely covers the field well.
FIELD_COVERAGE_MM = 5000

_FIELD_SIDE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>mm|m|[a-z]+)?$")


def _metres(mm: int) -> str:
    return f"{mm / 1000:g}"


def _field_side(text: str, unit: str | None, spec: str, in_metres: str) -> int:
    """One side of `--field` in millimetres; `unit` is None for a bare number.

    `in_metres` is the spelling suggested when a millimetre value looks like
    metres.
    """
    value = float(text)
    if unit == "m":
        mm = value * 1000
        if mm > FIELD_MAX_MM:
            raise click.BadParameter(
                f"a {text} m field is too large; did you mean {text}mm?"
            )
    else:
        if value < FIELD_MIN_MM:
            hint = (
                f"; did you mean {in_metres}?" if value * 1000 >= FIELD_MIN_MM else ""
            )
            raise click.BadParameter(f"a {text} mm field is too small{hint}")
        if value != int(value):
            raise click.BadParameter(
                f"{spec!r}: millimetres are whole numbers; use m for decimals"
            )
        mm = value
    mm = round(mm)
    if mm < FIELD_MIN_MM:
        raise click.BadParameter(f"a {_metres(mm)} m field is too small")
    if mm > FIELD_MAX_MM:
        raise click.BadParameter(f"a {_metres(mm)} m field is too large")
    return mm


def parse_field_size(spec: str) -> tuple[int, int]:
    """`--field` as (width, height) in millimetres.

    One value is a square, `WxH` a rectangle. A bare number is millimetres;
    `mm` and `m` suffixes are accepted, decimals only on `m`, and a side with
    no suffix takes the other side's.
    """
    sides = spec.strip().lower().split("x")
    if len(sides) not in (1, 2):
        raise click.BadParameter(f"{spec!r}: give one size or WxH, e.g. 2m or 2x3m")
    parsed = []
    for side in sides:
        match = _FIELD_SIDE.match(side.strip())
        if match is None:
            raise click.BadParameter(
                f"{spec!r}: a size is a number of mm, or ends in mm or m, e.g. 2m"
            )
        unit = match["unit"]
        if unit not in (None, "mm", "m"):
            raise click.BadParameter(f"{spec!r}: units are mm or m, not {unit}")
        parsed.append((match["value"], unit))
    units = [unit for _, unit in parsed if unit is not None]
    shared = units[-1] if units else None
    sizes = [
        _field_side(
            value,
            unit or shared,
            spec,
            f"{spec.strip()}m" if not units else f"{value}m",
        )
        for value, unit in parsed
    ]
    return (sizes[0], sizes[-1])


def default_site_toml(field_mm: tuple[int, int], broker: str | None = None) -> str:
    """The `site.toml` `init` writes: the starter site around the field
    (`starter_layout`), and `broker` as its `[connection]`."""
    extent, field_area, staging = starter_layout(field_mm)
    anchor = (
        f"top-left corner of a {_metres(extent[0])} x {_metres(extent[1])} m "
        f"floor; the field starts {_metres(SITE_MARGIN_MM)} m in from each wall"
    )
    connection = f'[connection]\nconn = "{broker}"\n\n' if broker else ""
    return (
        "# Zero is the top-left corner of the extent, x right, y down, millimetres.\n"
        f'anchor = "{anchor}"\n'
        f"extent_mm = [{extent[0]}, {extent[1]}]\n"
        "\n" + connection + "[areas]\n"
        f"field   = {_area_toml(field_area)}\n"
        f"staging = {_area_toml(staging)}\n"
    )


def _area_toml(area) -> str:
    return f"{{ x = {area.x}, y = {area.y}, w = {area.w}, h = {area.h} }}"


def _project_template(site: str) -> str:
    return (
        f"# The project's dotbot config, shared by everyone who clones it.\n"
        f"# Your own settings go in dotbot.local.toml (`dotbot config set`).\n"
        f"# Options: {_CONFIG_DOCS_URL}\n"
        "\n"
        f'site = "{site}"   # a pack in sites/ beside this file\n'
    )


def _ignore_local(folder: Path) -> str | None:
    """Add dotbot.local.toml to the .gitignore of the git repository `folder`
    is in, unless git already ignores it; the line added, or None."""
    local = folder / ("dotbot" + _config.LOCAL_CONFIG_SUFFIX)
    try:
        inside = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0:
            return None
        ignored = subprocess.run(
            ["git", "-C", str(folder), "check-ignore", "-q", str(local)],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if ignored.returncode == 0:
        return None
    gitignore = folder / ".gitignore"
    text = gitignore.read_text() if gitignore.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    gitignore.write_text(text + local.name + "\n")
    return f"added {local.name} to {gitignore}"


@click.group(
    name="config",
    help="Show the resolved config and where it came from; change one key.",
)
def cmd():
    pass


def _check_init_conn(conn: str | None) -> bool:
    """Validate `--conn`; True when it names a broker."""
    if conn is None:
        return False
    from dotbot.cli._conn import ConnError, parse_connection

    try:
        parsed = parse_connection(conn)
    except ConnError as exc:
        raise click.ClickException(f"invalid --conn: {exc}") from exc
    if parsed.kind != "mqtt":
        return False
    from pydantic import ValidationError

    try:
        _config.ConnectionSection(conn=conn)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise click.ClickException(f"invalid --conn: {message}") from exc
    return True


def _write(target: Path, key: tuple[str, ...], value) -> None:
    try:
        cw.set_value(target, key, value)
    except cw.WriteError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"wrote {cw.key_text(key)} = {json.dumps(value)} to {target}")


def _warn_conn_hidden(config, site: str, broker: str, replaced: Path | None) -> None:
    """Warn about each file or env variable whose `conn` hides the site's
    `broker`, leaving out the file at `replaced`."""
    phrases = []
    for item in getattr(config, "files", ()):
        conn = cw.lookup(item.data, ("conn",))
        if conn is not None and str(conn).strip() != broker and item.path != replaced:
            phrases.append(f"{item.label} sets conn")
    if os.environ.get("DOTBOT_CONN", broker).strip() != broker:
        phrases.append("DOTBOT_CONN is set")
    for phrase in phrases:
        click.echo(
            f"warning: {phrase}, which hides {site}'s conn; "
            "`dotbot config unset conn` to follow the site",
            err=True,
        )


def _set_pack_broker(pack_file: Path, broker: str) -> None:
    """Make `broker` the `[connection]` conn of the pack at `pack_file`,
    keeping its comments and other keys."""
    from pydantic import ValidationError

    document = tomlkit.parse(pack_file.read_text())
    connection = document.get("connection")
    previous = connection.get("conn") if isinstance(connection, dict) else None
    if previous is not None and str(previous).strip() == broker:
        click.echo(f"The site's [connection] already names {broker}")
        return
    if not isinstance(connection, dict):
        connection = tomlkit.table()
        document["connection"] = connection
    connection["conn"] = broker
    text = tomlkit.dumps(document)
    try:
        _config.SiteSection.model_validate(tomllib.loads(text))
    except ValidationError as exc:
        raise click.ClickException(f"invalid site pack {pack_file}:\n{exc}") from exc
    staged = pack_file.with_name(pack_file.name + ".tmp")
    staged.write_text(text)
    staged.replace(pack_file)
    was = f" (was {previous})" if previous is not None else ""
    click.echo(f"wrote [connection] conn = {json.dumps(broker)} to {pack_file}{was}")


@cmd.command()
@click.option(
    "--project",
    is_flag=True,
    help="Start a project here: ./dotbot.toml and its site in ./sites/, "
    "instead of your user file and ~/.dotbot/sites/.",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite an existing file.")
@click.option(
    "--conn",
    help="The connection: a broker URL becomes the site's, a serial path or "
    "'simulator' is yours.",
)
@click.option("--swarm-id", help="Your swarm id.")
@click.option(
    "--site",
    default=SITE_DEFAULT,
    show_default=True,
    help="Name the site; its calibrations are kept under that name.",
)
@click.option(
    "--field",
    "field_spec",
    default="2m",
    show_default=True,
    help="The field's size: one value for a square, WxH for a rectangle. "
    "A bare number is mm; 1.5m and 1500mm also work.",
)
@click.pass_context
def init(ctx, project, force, conn, swarm_id, site, field_spec):
    """Scaffold a site with a field and select it.

    Writes the site pack (~/.dotbot/sites/<site>/site.toml) and sets site,
    and your --swarm-id and a serial --conn, in ~/.dotbot/dotbot.toml,
    keeping the rest of that file. With --project, writes ./dotbot.toml and
    ./sites/<site>/site.toml for everyone who clones this folder, puts your
    own keys in ./dotbot.local.toml, and keeps that file out of git. A
    broker --conn becomes the site's [connection], in an existing pack too.
    """
    try:
        check_site_name(site)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="'--site'") from exc
    try:
        field_mm = parse_field_size(field_spec)
    except click.BadParameter as exc:
        exc.param_hint = "'--field'"
        raise
    broker = conn if _check_init_conn(conn) else None

    cwd = Path.cwd()
    project_file = cwd / _config.PROJECT_CONFIG_NAME
    if project and project_file.exists() and not force:
        raise click.ClickException(
            f"{project_file} already exists. Pass --force to overwrite it."
        )
    home = cwd / PROJECT_SITES_DIR if project else user_sites_dir()
    pack = home / site
    pack_file = pack / PACK_FILE
    if pack_file.exists() and not force:
        click.echo(f"Kept the site pack at {pack} (--force replaces it)")
        if broker:
            _set_pack_broker(pack_file, broker.strip())
            if not project:
                write_approval(pack, broker.strip())
    else:
        pack.mkdir(parents=True, exist_ok=True)
        pack_file.write_text(default_site_toml(field_mm, broker))
        if broker and not project:
            write_approval(pack, broker.strip())
        click.echo(
            f"Wrote {pack_file}: a {_metres(field_mm[0])} x "
            f"{_metres(field_mm[1])} m field with a staging strip below it."
        )
    personal = _config.USER_CONFIG_PATH
    if project:
        project_file.write_text(_project_template(site))
        click.echo(f"Wrote {project_file}")
        personal = _config.local_path_for(project_file)
        note = _ignore_local(cwd)
        if note:
            click.echo(note)
    else:
        _write(personal, ("site",), site)
    if conn and broker is None:
        _write(personal, ("conn",), conn)
    if swarm_id:
        _write(personal, ("swarm_id",), swarm_id)
    if broker:
        _warn_conn_hidden(
            (ctx.obj or {}).get("config"),
            site,
            broker.strip(),
            project_file if project else None,
        )
    if max(field_mm) > FIELD_COVERAGE_MM:
        click.echo(
            "Warning: one LH2 base station rarely covers a field over "
            f"{_metres(FIELD_COVERAGE_MM)} x {_metres(FIELD_COVERAGE_MM)} m. "
            "Add stations, or calibrate only the part the robots use with "
            "`dotbot swarm calibrate-lh2 collect --over` or `--square`.",
            err=True,
        )
    click.echo("Check it with `dotbot config show`.")


@cmd.command()
@click.pass_context
def path(ctx):
    """Print the config files in use, lowest priority first, with their kind."""
    config = (ctx.obj or {}).get("config")
    files = config.files if config is not None else ()
    if not files:
        click.echo("(none; using built-in defaults)")
        click.echo("Create one with: dotbot config init", err=True)
        return
    for item in files:
        click.echo(f"{item.kind:<8} {item.path}")


def _prune(value: Any) -> Any:
    """Recursively drop None values and empty tables so only set keys remain."""
    if isinstance(value, dict):
        pruned = {k: _prune(v) for k, v in value.items() if v is not None}
        return {k: v for k, v in pruned.items() if v != {}}
    return value


def _merged_keys(config) -> dict:
    """The merged config's set keys, with login passwords masked."""
    data = _prune(config.model_dump(by_alias=True))
    for login in data.get("login", {}).values():
        if "password" in login:
            login["password"] = "********"
    return data


def _entry_source(active) -> str:
    entry = active.entry
    if entry is None:
        return "no site pack of that name"
    where = {"project": "project pack", "user": "pack", "path": "pack"}[entry.home]
    hides = f", hiding {entry.shadows}" if entry.shadows else ""
    return f"{where} {display_path(entry.pack)}{hides}"


def _login(ctx, conn) -> dict:
    """Which login the conn's broker gets, for `show`."""
    url = conn.value if isinstance(conn.value, str) else ""
    if not url.strip().lower().startswith(("mqtt://", "mqtts://")):
        return {"sent": False, "text": "none needed (conn is not a broker)"}
    from marilib.communication_adapter import parse_mqtt_url

    host = parse_mqtt_url(url)[0]
    decision = credentials_for(ctx, conn)
    if decision.username is not None:
        text = f"{host}: {decision.reason}"
    elif decision.withheld:
        text = f"{host}: withheld: {decision.withheld}"
    elif host in LOCAL_HOSTS:
        text = f"{host}: none"
    else:
        text = f"{host}: none (save one with `dotbot config login {host}`)"
    return {
        "host": host,
        "sent": decision.username is not None,
        "reason": decision.reason,
        "withheld": decision.withheld,
        "text": text,
    }


@cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Print it as JSON.")
@click.pass_context
def show(ctx, as_json):
    """Print the config files in use, where the site, conn and swarm id each
    came from and what they hide, the login the broker gets, then every key
    the files set, merged."""
    config = (ctx.obj or {}).get("config") or _config.DotbotConfig()
    active = active_site(ctx)
    site = resolve_source("site", config=config, default=SITE_DEFAULT)
    resolved = {
        key: resolve_source(key, config=config, site=active.layer)
        for key in ("conn", "swarm_id")
    }
    login = _login(ctx, resolved["conn"])
    unknown = unknown_env()

    if as_json:
        report = {
            "files": [{"kind": f.kind, "path": str(f.path)} for f in config.files],
            "site": {
                "name": active.name,
                "source": active.source,
                "pack": str(active.entry.pack) if active.entry else None,
                "hides": [{"source": src, "value": val} for src, val in site.hidden],
            },
            **{
                key: {
                    "value": item.value,
                    "source": item.source,
                    "hides": [
                        {"source": src, "value": val} for src, val in item.hidden
                    ],
                }
                for key, item in resolved.items()
            },
            "login": {k: v for k, v in login.items() if k != "text"},
            "unknown_env": [name for name, _ in unknown],
            "merged": _merged_keys(config),
        }
        click.echo(json.dumps(report, indent=2))
        return

    files = (
        "  ".join(f"{f.label} ({f.kind})" for f in config.files)
        or "(none; built-in defaults. Create one with: dotbot config init)"
    )
    click.echo(f"{'files:':<10} {files}")
    click.echo(
        f"{'site:':<10} {active.name}  from {active.source}  {_entry_source(active)}"
    )
    for src, val in site.hidden:
        click.echo(f"{'':<10} hides {src} site = {json.dumps(val)}")
    for key, item in resolved.items():
        value = item.value if item.value is not None else "(unset)"
        where = f"  from {item.source}" if item.value is not None else ""
        click.echo(f"{key + ':':<10} {value}{where}")
        for src, val in item.hidden:
            click.echo(f"{'':<10} hides {src} {key} = {json.dumps(val)}")
    click.echo(f"{'login:':<10} {login['text']}")
    for name, close in unknown:
        hint = f" (did you mean {close}?)" if close else ""
        click.echo(f"{'unknown:':<10} {name}{hint}: nothing reads it")
    click.echo("")
    data = _merged_keys(config)
    if not data:
        if config.files:
            click.echo("(the files set nothing yet; all built-in defaults)")
        return
    click.echo(tomlkit.dumps(data).rstrip())


def _key(text: str) -> tuple[str, ...]:
    try:
        return cw.parse_key(text)
    except cw.WriteError as exc:
        raise click.BadParameter(str(exc), param_hint="'KEY'") from exc


def _route(ctx, key, where) -> Path:
    try:
        return cw.target((ctx.obj or {}).get("config"), key, where)
    except cw.WriteError as exc:
        raise click.ClickException(str(exc)) from exc


def _after_write(ctx, target: Path, key) -> None:
    config = (ctx.obj or {}).get("config")
    project = getattr(config, "project_path", None)
    if project is not None and target.resolve() == Path(project).resolve():
        click.echo(
            f"note: {target.name} is the project's file, so the change shows "
            "in git status",
            err=True,
        )
    for phrase in cw.hiders(config, target, key):
        click.echo(f"warning: {phrase}, which overrides it", err=True)


def _refuse_conn_login(conn: str) -> None:
    """Refuse a broker URL carrying a login, which belongs in `config login`."""
    from urllib.parse import urlparse

    if not conn.strip().lower().startswith(("mqtt://", "mqtts://")):
        return
    parsed = urlparse(conn.strip())
    if parsed.username is not None or parsed.password is not None:
        raise click.ClickException(
            "conn carries no credentials: a password typed here stays in your "
            "shell history; drop the user:pass@ part and save the login with "
            f"`dotbot config login {parsed.hostname or 'HOST'}`"
        )


@cmd.command(name="set")
@click.argument("key")
@click.argument("value")
@cw.where_options("Write the project's dotbot.toml, which is committed.")
@click.pass_context
def set_(ctx, key, value, where):
    """Set KEY to VALUE in your own config file.

    KEY is spelled as in TOML: swarm_id, fw.segger_dir,
    run.controller.lh2_calibration. Keys true of this machine (fw.segger_dir,
    device.probe, ...) go to ~/.dotbot/dotbot.toml; any other key goes to
    dotbot.local.toml beside the project's dotbot.toml when one is in use,
    else to ~/.dotbot/dotbot.toml. --user and --project pick the file.
    """
    path = _key(key)
    if path[0] == "login" and path[-1] == "password":
        raise click.ClickException(
            "a password typed here stays in your shell history; save it with "
            f"`dotbot config login {path[1] if len(path) > 2 else 'HOST'}`"
        )
    try:
        cw.check_key(path)
    except cw.WriteError as exc:
        raise click.BadParameter(str(exc), param_hint="'KEY'") from exc
    try:
        typed = cw.coerce(path, value)
    except cw.WriteError as exc:
        raise click.BadParameter(str(exc), param_hint="'VALUE'") from exc
    if path == ("conn",):
        _refuse_conn_login(typed)
    target = _route(ctx, path, where)
    if path == ("site",):
        from dotbot.site_packs import is_pack_path, pack_at

        if is_pack_path(typed):
            try:
                pack_at(typed)
            except _config.ConfigError as exc:
                raise click.ClickException(str(exc)) from exc
    if isinstance(typed, str):
        typed = cw.path_value(path, typed, target)
    _write(target, path, typed)
    _after_write(ctx, target, path)


@cmd.command()
@click.argument("key")
@cw.where_options("Write the project's dotbot.toml, which is committed.")
@click.pass_context
def unset(ctx, key, where):
    """Remove KEY from your own config file, so a lower layer applies.

    The file is chosen as `dotbot config set` chooses it.
    """
    path = _key(key)
    target = _route(ctx, path, where)
    try:
        removed = cw.unset_value(target, path)
    except cw.WriteError as exc:
        raise click.ClickException(str(exc)) from exc
    if removed:
        click.echo(f"removed {cw.key_text(path)} from {target}")
        _after_write(ctx, target, path)
        return
    config = (ctx.obj or {}).get("config")
    others = [
        item.label
        for item in getattr(config, "files", ())
        if cw.lookup(item.data, path) is not None
    ]
    where_set = f"; it is set in {', '.join(others)}" if others else ""
    raise click.ClickException(f"{cw.key_text(path)} is not set in {target}{where_set}")


@cmd.command()
@click.argument("host")
def login(host):
    """Save the login sent to the broker at HOST.

    HOST is the broker's host name, or its mqtts:// URL. The user name and
    password are asked for and kept in ~/.dotbot/dotbot.toml, made readable
    by you alone, and only that host's broker ever gets them.
    """
    if "://" in host:
        from urllib.parse import urlparse

        host = urlparse(host).hostname or ""
    host = host.strip().lower()
    if not host or any(char.isspace() or char in "/@:" for char in host):
        raise click.BadParameter("give a host name, e.g. broker.lab.example")
    user = click.prompt("User", err=True)
    password = click.prompt("Password", hide_input=True, err=True)
    target = _config.USER_CONFIG_PATH
    try:
        cw.set_value(target, ("login", host, "user"), user)
        cw.set_value(target, ("login", host, "password"), password)
    except cw.WriteError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"saved the login for {host} to {target}")
