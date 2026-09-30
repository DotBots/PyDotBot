# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Root `dotbot` Click group: four object-namespaces + management commands.

The top level is the four object-namespaces, each one *kind of thing*:

  fw      — firmware artifacts (cached in ~/.dotbot/artifacts/, no hardware)
  device  — one connected device (cable / probe)
  swarm   — the fleet (radio / OTA)
  run     — host-side processes (software you launch on your computer)

Three are nouns (things you manage); `run` is the verb (the thing you do).
Alongside them sit the management commands - `config` (what config is in
effect, and where each value came from) and `site` (the places you work in,
and which one is active).

Each group lives in its own module under `dotbot.cli.<name>` exposing a
`cmd` attribute. The root lists the groups eagerly (so `dotbot --help` is
cheap) but only imports a group's module when it's actually invoked — see
`dotbot.cli._lazygroup.LazyGroup`.

Adding a new top-level group:
  1. Create `dotbot/cli/<name>.py` exposing `cmd = click.Command(...)`.
  2. Add a `(cli-name, module path, short help)` entry to `_SUBCOMMANDS`.
  3. If the backend lives in an optional sibling package, wrap it with
     `dotbot.cli._lazy.lazy_subcommand` inside that module.
"""

import click

from dotbot import pydotbot_version
from dotbot.cli._lazygroup import LazyGroup
from dotbot.mqtt_tls import allow_unverified_broker

# (cli-name, dotted module path, short help shown by `dotbot --help`)
_SUBCOMMANDS = (
    (
        "guide",
        "dotbot.cli.guide",
        "Start here: for people and AI agents, simulator first.",
    ),
    (
        "fw",
        "dotbot.cli.fw",
        "Firmware artifacts (no hardware): build / fetch / list / make.",
    ),
    (
        "device",
        "dotbot.cli.device",
        "One connected device (cable/probe): flash an app/role, read info.",
    ),
    (
        "swarm",
        "dotbot.cli.swarm",
        "The fleet over the air: status, start/stop, OTA flash, monitor.",
    ),
    (
        "run",
        "dotbot.cli.run",
        "Host-side processes: controller, gateway, simulator, LH2 and "
        "camera calibration, demos, teleop.",
    ),
    (
        "config",
        "dotbot.cli.config_cmd",
        "Show the resolved config + where it came from.",
    ),
    (
        "site",
        "dotbot.cli.site_cmd",
        "Sites: add a pack, switch with use, list / show, export one to share.",
    ),
)


# The commands that read no config, so say nothing about which one is in
# effect: `config` inspects that itself, `site add` only writes a pack, and
# `guide` prints a file
_CONFIGLESS = {("config",), ("site", "add"), ("guide",)}


class _RootGroup(LazyGroup):
    """The root group, which records the words after its subcommand's name
    before its own callback runs, so the callback can tell `site add` from
    `site export`."""

    def resolve_command(self, ctx, args):
        name, command, rest = super().resolve_command(ctx, args)
        ctx.meta[_SUBCOMMAND_ARGS] = list(rest)
        return name, command, rest


_SUBCOMMAND_ARGS = "dotbot.subcommand_args"


def _reads_config(ctx) -> bool:
    words = (ctx.invoked_subcommand, *ctx.meta.get(_SUBCOMMAND_ARGS, [])[:1])
    return not any(words[: len(path)] == path for path in _CONFIGLESS)


@click.group(
    cls=_RootGroup,
    subcommands=_SUBCOMMANDS,
    help=(
        "One CLI for the whole DotBot workflow: build and flash firmware, "
        "program and control a single DotBot, and run experiments over the air "
        "across a swarm - from one DotBot to a thousand.\n\n"
        "New here, or an AI agent? Start with: dotbot guide"
    ),
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(dir_okay=False),
    default=None,
    help=(
        "Config file to use (default: a dotbot.toml in the current directory, "
        "else ~/.dotbot/dotbot.toml)."
    ),
)
@click.version_option(
    version=pydotbot_version(),
    prog_name="dotbot",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(ctx, config_path):
    """Load the unified config, then dispatch.

    The resolved config and its path are stashed on the Click context
    (`ctx.obj`) so each subcommand can read its defaults from them; flags and
    env vars still override the file (see `dotbot.config`).

    Discovery order: `-c` / `DOTBOT_CONFIG` > a `dotbot.toml` in the cwd >
    `~/.dotbot/dotbot.toml` (the per-machine fallback). `fw` reads its `[fw]`
    keys (`segger_dir`, `[fw.sources]`, ...) through this same resolver.

    Certificate checking is settled here, before any subcommand runs.
    """
    allow_unverified_broker()

    from dotbot.config import (
        PROJECT_CONFIG_NAME,
        USER_CONFIG_PATH,
        ConfigError,
        discover_config_path,
        load_config,
    )

    ctx.ensure_object(dict)
    try:
        path = discover_config_path(config_path)
        config = load_config(path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    if _reads_config(ctx):
        if path is not None:
            click.echo(f"Using config file at {path}", err=True)
        else:
            click.echo(
                f"No config file found (looked for ./{PROJECT_CONFIG_NAME} and "
                f"{USER_CONFIG_PATH}); using built-in defaults",
                err=True,
            )

    ctx.obj["config"] = config
    ctx.obj["config_path"] = path
