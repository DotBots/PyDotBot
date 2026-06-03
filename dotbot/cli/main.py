# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Root `dotbot` Click group: four object-namespaces + management commands.

The top level is the four object-namespaces, each one *kind of thing*:

  fw      — firmware artifacts (files in ./artifacts/, no hardware)
  device  — one connected device (cable / probe)
  swarm   — the fleet (radio / OTA)
  run     — host-side processes (software you launch on your computer)

Three are nouns (things you manage); `run` is the verb (the thing you do).
Alongside them sit the read-only management commands - `config` (what
config is in effect, and where it came from) and `deployment` (which
deployments are defined, and which is active).

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

# (cli-name, dotted module path, short help shown by `dotbot --help`)
_SUBCOMMANDS = (
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
        "Host-side processes: controller, gateway, simulator, calibration, demos, teleop.",
    ),
    (
        "config",
        "dotbot.cli.config_cmd",
        "Show the resolved config + where it came from.",
    ),
    (
        "deployment",
        "dotbot.cli.deployment_cmd",
        "List / show configured deployments.",
    ),
)


@click.group(
    cls=LazyGroup,
    subcommands=_SUBCOMMANDS,
    help=(
        "One CLI for the whole DotBot workflow: build and flash firmware, "
        "program and control a single robot, and run experiments over the air "
        "across a swarm - from one bot to a thousand."
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
        "else ~/.dotbot/config.toml)."
    ),
)
@click.option(
    "--deployment",
    "deployment_name",
    default=None,
    metavar="NAME",
    help="Which configured deployment to target; overrides default_deployment.",
)
@click.version_option(
    version=pydotbot_version(),
    prog_name="dotbot",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(ctx, config_path, deployment_name):
    """Load the unified config + select the deployment, then dispatch.

    The resolved config and the selected deployment are stashed on the Click
    context (`ctx.obj`) so each subcommand can read its defaults from them;
    flags and env vars still override the file (see `dotbot.config`).

    Discovery order: `-c` / `DOTBOT_CONFIG` > a `dotbot.toml` in the cwd >
    `~/.dotbot/config.toml` (the per-machine fallback). `fw` reads its `[fw]`
    keys (`segger_dir`, `firmware_repo`, ...) through this same resolver.
    """
    from dotbot.config import (
        ConfigError,
        discover_config_path,
        load_config,
        select_deployment,
    )

    ctx.ensure_object(dict)
    try:
        path = discover_config_path(config_path)
        config = load_config(path)
        deployment, deployment_resolved = select_deployment(
            config, cli_name=deployment_name
        )
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    if path is not None:
        click.echo(f"using config file at {path}", err=True)
    else:
        click.echo("no config file found; using built-in defaults", err=True)

    ctx.obj["config"] = config
    ctx.obj["config_path"] = path
    ctx.obj["deployment"] = deployment
    ctx.obj["deployment_name"] = deployment_resolved
