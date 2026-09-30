# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot config` - scaffold and inspect the dotbot configuration.

A management group (like `git config` / `kubectl config`): `init` writes a
starter config file holding a site to work in (optionally pre-filling `conn` /
`swarm_id`); `path` and `show` are read-only inspectors over what the root
group resolved onto the Click context (`ctx.obj`): the loaded `DotbotConfig`
and its source path. There is no per-key `set` - edit the file, it is yours.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

import click
import tomlkit

from dotbot import config as _config
from dotbot.cli._site import active_site, config_label
from dotbot.config import resolve_source
from dotbot.mqtt_tls import USER_ENV, broker_credentials
from dotbot.site import SITE_DEFAULT, check_site_name

_CONFIG_DOCS_URL = (
    "https://pydotbot.readthedocs.io/en/latest/reference/configuration.html"
)


# The default site's geometry, all derived from the field: a margin of floor
# round it, and a staging strip along its bottom edge.
SITE_MARGIN_MM = 1500
STAGING_DEPTH_MM = 600
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


def default_site_toml(
    name: str, field_mm: tuple[int, int], broker: str | None = None
) -> str:
    """The `[sites.<name>]` table `init` writes: a field with a margin of floor
    round it and a staging strip along its bottom edge, and `broker` as its
    `[connection]`."""
    width, height = field_mm
    extent = (width + 2 * SITE_MARGIN_MM, height + 2 * SITE_MARGIN_MM)
    x = y = SITE_MARGIN_MM
    anchor = (
        f"top-left corner of a {_metres(extent[0])} x {_metres(extent[1])} m "
        f"floor; the field starts {_metres(SITE_MARGIN_MM)} m in from each wall"
    )
    return (
        "# Zero is the top-left corner of the extent, x right, y down, millimetres.\n"
        f"[sites.{name}]\n"
        f'anchor = "{anchor}"\n'
        f"extent_mm = [{extent[0]}, {extent[1]}]\n"
        "\n"
        + (f'[sites.{name}.connection]\nconn = "{broker}"\n\n' if broker else "")
        + f"[sites.{name}.areas]\n"
        f"field   = {{ x = {x}, y = {y}, w = {width}, h = {height} }}\n"
        f"staging = {{ x = {x}, y = {y + height}, w = {width}, "
        f"h = {STAGING_DEPTH_MM} }}\n"
    )


# `dotbot config init` writes a *minimal* file: the keys you pass, the site
# your robots work in, and a one-line pointer to the full reference. No wall
# of commented options - the schema lives in the docs, not in everyone's file.
def _starter_template(
    conn: str | None = None,
    swarm_id: str | None = None,
    site: str = SITE_DEFAULT,
    field_mm: tuple[int, int] = FIELD_DEFAULT_MM,
) -> str:
    header = (
        f"# dotbot config. Options + examples: {_CONFIG_DOCS_URL}\n"
        "# (MQTT credentials are env-only: DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS.)\n"
    )
    broker = conn if conn and conn.lower().startswith(("mqtt://", "mqtts://")) else None
    keys = []
    if conn and broker is None:
        keys.append(f'conn = "{conn}"')
    if swarm_id:
        keys.append(f'swarm_id = "{swarm_id}"')
    keys.append(f'site = "{site}"')
    return (
        header
        + "\n"
        + "\n".join(keys)
        + "\n\n"
        + default_site_toml(site, field_mm, broker)
    )


@click.group(
    name="config",
    help="Show the resolved config + where it came from; scaffold one with init.",
)
def cmd():
    pass


@cmd.command()
@click.option(
    "--global",
    "global_",
    is_flag=True,
    help="Write the user-level ~/.dotbot/dotbot.toml instead of ./dotbot.toml.",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite an existing file.")
@click.option(
    "--conn",
    help="Pre-fill the shared connection (broker URL, serial path, or 'simulator').",
)
@click.option("--swarm-id", help="Pre-fill the shared swarm id.")
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
def init(global_, force, conn, swarm_id, site, field_spec):
    """Write a starter config file you can edit.

    Defaults to ./dotbot.toml in the current directory; --global writes your
    user-level ~/.dotbot/dotbot.toml. Refuses to overwrite unless --force.
    The file names a site with a field, where experiments happen and what
    calibration covers, and a staging strip along its bottom edge, with a
    margin of floor round both. `--field` sizes the field, and the rest
    follows from it. A broker `--conn` becomes the site's [connection]; a
    serial path or `simulator`, and `--swarm-id`, are top-level keys.
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
    if conn is not None:
        from dotbot.cli._conn import ConnError, parse_connection

        try:
            parsed = parse_connection(conn)
        except ConnError as exc:
            raise click.ClickException(f"invalid --conn: {exc}") from exc
        if parsed.kind == "mqtt":
            from pydantic import ValidationError

            try:
                _config.ConnectionSection(conn=conn)
            except ValidationError as exc:
                message = exc.errors()[0]["msg"].removeprefix("Value error, ")
                raise click.ClickException(f"invalid --conn: {message}") from exc

    target = _config.USER_CONFIG_PATH if global_ else Path.cwd() / "dotbot.toml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Pass --force to overwrite it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_starter_template(conn, swarm_id, site, field_mm))
    click.echo(f"Wrote {target}")
    click.echo(
        f"Site {site}: a {_metres(field_mm[0])} x {_metres(field_mm[1])} m field "
        f"with a staging strip below it."
    )
    if max(field_mm) > FIELD_COVERAGE_MM:
        click.echo(
            "Warning: one LH2 base station rarely covers a field over "
            f"{_metres(FIELD_COVERAGE_MM)} x {_metres(FIELD_COVERAGE_MM)} m. "
            "Add stations, or calibrate only the part the robots use with "
            "`dotbot swarm calibrate-lh2 collect --over` or `--square`.",
            err=True,
        )
    if conn or swarm_id:
        filled = " and ".join(
            label for label, val in (("conn", conn), ("swarm_id", swarm_id)) if val
        )
        click.echo(f"Set {filled}; review it, then run `dotbot config show`.")
    else:
        click.echo("Edit it to taste (see the link inside), then `dotbot config show`.")


@cmd.command()
@click.pass_context
def path(ctx):
    """Print the resolved config file path (or note the built-in defaults)."""
    config_path = (ctx.obj or {}).get("config_path")
    if config_path is None:
        click.echo("(none; using built-in defaults)")
        click.echo("Create one with: dotbot config init", err=True)
    else:
        click.echo(str(config_path))


def _prune(value: Any) -> Any:
    """Recursively drop None values and empty tables so only set keys remain."""
    if isinstance(value, dict):
        pruned = {k: _prune(v) for k, v in value.items() if v is not None}
        return {k: v for k, v in pruned.items() if v != {}}
    return value


def _entry_source(active) -> str:
    entry = active.entry
    if entry is None:
        return "not defined by any config or pack"
    if entry.pack is not None:
        return f"pack {entry.pack}"
    return "inline" + (f", shadowing {entry.shadows}" if entry.shadows else "")


def _credentials(conn) -> dict:
    """What happens to the env's broker login, for `show`."""
    if os.environ.get(USER_ENV) is None:
        return {"set": False, "text": f"none ({USER_ENV} unset)"}
    decision = broker_credentials(conn)
    text = f"{USER_ENV} set"
    if decision.withheld:
        text += f"; withheld: {decision.withheld}"
    elif decision.username is not None:
        text += f"; sent to this conn's broker: {decision.reason}"
    return {
        "set": True,
        "sent": decision.username is not None,
        "reason": decision.reason,
        "withheld": decision.withheld,
        "text": text,
    }


@cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Print it as JSON.")
@click.pass_context
def show(ctx, as_json):
    """Print the config file in use, where the site, conn and swarm id each
    came from and what they hide, then the file's own keys.

    None-valued fields are skipped so only what is actually set shows up.
    """
    obj = ctx.obj or {}
    config = obj.get("config")
    config_path = obj.get("config_path")
    active = active_site(ctx)
    label = config_label(config_path)
    resolved = {
        key: resolve_source(
            key,
            section="run",
            config=config,
            config_label=label,
            site=active.layer,
        )
        for key in ("conn", "swarm_id")
    }
    creds = _credentials(resolved["conn"])

    if as_json:
        report = {
            "config": str(config_path) if config_path is not None else None,
            "site": {
                "name": active.name,
                "source": active.source,
                "defined_by": _entry_source(active),
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
            "creds": {k: v for k, v in creds.items() if k != "text"},
            "file": _prune(config.model_dump()) if config is not None else {},
        }
        click.echo(json.dumps(report, indent=2))
        return

    source = (
        str(config_path)
        if config_path is not None
        else "(none; built-in defaults. Create one with: dotbot config init)"
    )
    click.echo(f"{'config:':<10} {source}")
    click.echo(
        f"{'site:':<10} {active.name}  from {active.source}  {_entry_source(active)}"
    )
    for key, item in resolved.items():
        value = item.value if item.value is not None else "(unset)"
        where = f"  from {item.source}" if item.value is not None else ""
        click.echo(f"{key + ':':<10} {value}{where}")
        for src, val in item.hidden:
            click.echo(f"{'':<10} hides {src} {key} = {json.dumps(val)}")
    click.echo(f"{'creds:':<10} {creds['text']}")
    click.echo("")

    if config is None:
        click.echo("(no config loaded)")
        return

    # Prune unset Optionals so the dump shows only what the file explicitly set
    # (matches the resolver's "unset vs default" model), then render via tomlkit
    # so the output is real, round-trippable TOML.
    data = _prune(config.model_dump())
    if not data:
        if config_path is not None:
            click.echo("(the file sets nothing yet; all built-in defaults)")
        return
    click.echo(tomlkit.dumps(data).rstrip())
