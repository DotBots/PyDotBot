# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot config` - scaffold and inspect the dotbot configuration.

A management group (like `git config` / `kubectl config`): `init` writes a
starter config file (optionally pre-filling `conn` / `swarm_id`); `path` and
`show` are read-only inspectors over what the root group resolved onto the
Click context (`ctx.obj`): the loaded `DotbotConfig`, its source path, and the
selected deployment. There is no per-key `set` - edit the file, it is yours.
"""

from pathlib import Path
from typing import Any

import click

from dotbot.config import USER_CONFIG_PATH

_CONFIG_DOCS_URL = (
    "https://pydotbot.readthedocs.io/en/latest/reference/configuration.html"
)


# `dotbot config init` writes a *minimal* file: just the keys you pass, plus a
# one-line pointer to the full reference. No wall of commented options - the
# schema lives in the docs, not in everyone's config file.
def _starter_template(conn: str | None = None, swarm_id: str | None = None) -> str:
    header = (
        f"# dotbot config. Options + examples: {_CONFIG_DOCS_URL}\n"
        "# (MQTT credentials are env-only: DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS.)\n"
    )
    keys = []
    if conn:
        keys.append(f'conn = "{conn}"')
    if swarm_id:
        keys.append(f'swarm_id = "{swarm_id}"')
    if keys:
        return header + "\n" + "\n".join(keys) + "\n"
    return header


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
    help="Write the user-level ~/.dotbot/config.toml instead of ./dotbot.toml.",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite an existing file.")
@click.option(
    "--conn",
    help="Pre-fill the shared connection (broker URL, serial path, or 'simulator').",
)
@click.option("--swarm-id", help="Pre-fill the shared swarm id.")
def init(global_, force, conn, swarm_id):
    """Write a minimal starter config file you can edit.

    Defaults to ./dotbot.toml in the current directory; --global writes your
    user-level ~/.dotbot/config.toml. Refuses to overwrite unless --force.
    `--conn` / `--swarm-id` pre-fill those top-level keys; the file otherwise
    holds just a one-line pointer to the full reference (no wall of options).
    """
    if conn is not None:
        from dotbot.cli._conn import ConnError, parse_connection

        try:
            parse_connection(conn)
        except ConnError as exc:
            raise click.ClickException(f"invalid --conn: {exc}") from exc

    target = USER_CONFIG_PATH if global_ else Path.cwd() / "dotbot.toml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Pass --force to overwrite it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_starter_template(conn, swarm_id))
    click.echo(f"Wrote {target}")
    if conn or swarm_id:
        filled = " and ".join(
            label for label, val in (("conn", conn), ("swarm_id", swarm_id)) if val
        )
        click.echo(f"Set {filled}; review it, then run `dotbot config show`.")
    else:
        click.echo(
            "Add your settings (see the link inside), then `dotbot config show`."
        )


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


def _dump_lines(prefix: str, value: Any) -> list[str]:
    """Render `value` as `key = repr` lines, skipping None, recursing tables.

    Pydantic sections become nested `[section]` / `[section.sub]` tables;
    scalar fields print as `key = value` with the value quoted for strings.
    """
    lines: list[str] = []
    nested: list[str] = []
    for field, item in value.items():
        if item is None or item == {}:
            continue
        if isinstance(item, dict):
            header = f"{prefix}.{field}" if prefix else field
            inner = _dump_lines(header, item)
            if not inner:
                continue
            nested.append("")
            nested.append(f"[{header}]")
            nested.extend(inner)
        elif isinstance(item, str):
            lines.append(f"{field} = {item!r}")
        else:
            lines.append(f"{field} = {item}")
    return lines + nested


@cmd.command()
@click.pass_context
def show(ctx):
    """Print the source path, the active deployment, and the loaded config.

    None-valued fields are skipped so only what is actually set shows up.
    """
    obj = ctx.obj or {}
    config = obj.get("config")
    config_path = obj.get("config_path")
    deployment_name = obj.get("deployment_name")

    source = (
        str(config_path) if config_path is not None else "(none; built-in defaults)"
    )
    click.echo(f"source:  {source}")
    click.echo(f"deployment: {deployment_name or '(none)'}")
    click.echo("")

    if config is None:
        click.echo("(no config loaded)")
        return

    # exclude_none drops every unset Optional so the dump shows only what the
    # file explicitly set (matches the resolver's "unset vs default" model).
    data = config.model_dump(exclude_none=True)
    lines = _dump_lines("", data)
    if not lines:
        if config_path is None:
            click.echo("No config file found. Create one with:  dotbot config init")
        else:
            click.echo("(the file sets nothing yet; all built-in defaults)")
        return
    for line in lines:
        click.echo(line)
