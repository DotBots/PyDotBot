# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot config` - inspect the resolved configuration (read-only).

A management group (like `git config` / `kubectl config`) that answers
"what config is `dotbot` actually using, and where did it come from?".
Both subcommands read what the root group already stashed on the Click
context (`ctx.obj`): the loaded `DotbotConfig`, its source path, and the
selected deployment. Writing the file is deferred, so there is no `set` here.
"""

from typing import Any

import click


@click.group(
    name="config",
    help="Show the resolved config + where it came from (read-only).",
)
def cmd():
    pass


@cmd.command()
@click.pass_context
def path(ctx):
    """Print the resolved config file path (or note the built-in defaults)."""
    config_path = (ctx.obj or {}).get("config_path")
    if config_path is None:
        click.echo("(none; using built-in defaults)")
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
        click.echo("(empty; all built-in defaults)")
        return
    for line in lines:
        click.echo(line)
