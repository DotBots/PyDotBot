# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot config` - inspect the resolved configuration (read-only).

A management group (like `git config` / `kubectl config`) that answers
"what config is `dotbot` actually using, and where did it come from?".
Both subcommands read what the root group already stashed on the Click
context (`ctx.obj`): the loaded `DotbotConfig`, its source path, and the
selected deployment. Writing the file is deferred, so there is no `set` here.
"""

from pathlib import Path
from typing import Any

import click

from dotbot.config import USER_CONFIG_PATH

# An annotated starter, written by `dotbot config init`. Everything is commented
# so a freshly-created file loads as an empty (all-defaults) config; you
# uncomment what you need. It doubles as schema-by-example.
_STARTER_TEMPLATE = """\
# dotbot config. A value resolves:  CLI flag > env (DOTBOT_<SECTION>_<KEY>) >
# this file > built-in default. Found as ./dotbot.toml (searched cwd-upward) or
# ~/.dotbot/config.toml, or named with `dotbot -c PATH`. Everything below is
# commented out - uncomment what you need, then run `dotbot config show`.

# --- shared defaults (any section or deployment can override these) ---------
# conn      = "mqtts://broker:8883"   # broker URL, a serial path, or "simulator"
# swarm_id  = "0001"
# log_level = "info"

# --- named deployments: one per physical site; select with --deployment NAME,
#     DOTBOT_DEPLOYMENT, or default_deployment -------------------------------
# default_deployment = "example"
# [deployment.example]
# conn     = "mqtts://broker.example:8883"
# swarm_id = "0001"
# location = "Example lab"            # descriptive
# bots     = 100                      # descriptive

# --- per-namespace defaults (mirror the fw / device / swarm / run commands) -
# [fw]
# board = "dotbot-v3"
#
# [device]
# sn_starting_digits = "77"
#
# [run.controller]
# http_port = 8000

# MQTT credentials are read only from the environment, never this file:
#   export DOTBOT_MQTT_USER=...  DOTBOT_MQTT_PASS=...
"""


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
def init(global_, force):
    """Write an annotated starter config file you can edit.

    Defaults to ./dotbot.toml in the current directory; --global writes your
    user-level ~/.dotbot/config.toml. Refuses to overwrite unless --force.
    """
    target = USER_CONFIG_PATH if global_ else Path.cwd() / "dotbot.toml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Pass --force to overwrite it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_STARTER_TEMPLATE)
    click.echo(f"Wrote {target}")
    click.echo("Uncomment what you need, then run `dotbot config show`.")


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
