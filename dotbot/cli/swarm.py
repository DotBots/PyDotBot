# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` — fleet operations over the air (status/start/stop/flash/...).

Mounts the upstream `swarmit` Click group as the `dotbot swarm` parent:
operators get `status|start|stop|flash|monitor|reset|message|serve` with their
existing flags, plus the PyDotBot-native `calibrate-lh2 collect|push`.
`swarm` is strictly the *many-devices, over-the-radio* namespace.

Single-device, cabled operations moved out: firmware-artifact build/fetch/
list live under `dotbot fw`, and per-device flashing/inspection (including
what used to be `swarm provision …`) lives under `dotbot device`.

swarmit has its own config loader, so the unified `dotbot.toml` is bridged in
at the mount boundary: `conn` / `swarm_id` resolved by the root group are
translated into swarmit's flags (see `_swarm_inject`), so `dotbot swarm status`
inherits the active site's connection like every other command. An explicit
swarmit `--conn` / `--swarm-id` / `-c` still wins.
"""

import os

import click

from dotbot.cli._lazy import lazy_subcommand
from dotbot.cli._swarm_inject import (
    group_options,
    inject_config,
    subcommand_index,
    swarm_connection,
)

# The subcommands that act on robots, which name their connection first
_ACTING = {"flash", "start", "stop", "reset"}

_HELP = (
    "Fleet ops over the air: status, start/stop, OTA-flash, monitor, "
    "reset, calibrate-lh2. Wraps swarmit."
)


def _load_swarmit_group():
    from swarmit.cli.main import main as swarmit_group

    return swarmit_group


def _run_swarmit(
    swarmit_group, args
):  # pragma: no cover - delegates to swarmit (needs MQTT/serial)
    swarmit_group.main(args=args, prog_name="dotbot swarm", standalone_mode=True)


def _mount_native_lh2(swarmit_group) -> None:
    """List PyDotBot's `calibrate-lh2` among swarmit's own commands.

    `dotbot swarm --help` is rendered by swarmit's group, so a command the
    passthrough intercepts never reaches that listing. Registering it here is
    what puts it there; dispatch still goes through the intercept, which is
    what carries the resolved config. swarmit ships a `calibrate-lh2` of its
    own that only takes a file path, and this registration replaces it, so it
    must overwrite rather than skip an existing entry.
    """
    from dotbot.cli.swarm_lh2 import cmd as lh2_group

    swarmit_group.add_command(lh2_group)


def _settle_connection(ctx, args, swarmit_group) -> None:
    """Print the banner for a command that acts on robots, and keep the
    broker login from a broker it is not meant for.

    swarmit reads `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` from the
    environment itself, so a withheld login is removed from this process's
    environment before swarmit runs.
    """
    from dotbot.cli._site import active_site, connection_banner
    from dotbot.config import Resolved
    from dotbot.mqtt_tls import PASS_ENV, USER_ENV, broker_credentials

    sub = subcommand_index(args, swarmit_group)
    given = group_options(args, swarmit_group)
    if "config_path" in given:
        return
    conn, swarm_id = swarm_connection(ctx.obj)
    if "conn" in given:
        conn = Resolved(given["conn"], "flag", "--conn")
    if "swarm_id" in given:
        swarm_id = Resolved(given["swarm_id"], "flag", "--swarm-id")
    if sub is not None and args[sub] in _ACTING:
        click.echo(connection_banner(active_site(ctx), conn, swarm_id), err=True)
    credentials = broker_credentials(conn.value, conn.user_set, conn.source)
    if credentials.withheld:
        click.echo(f"warning: {credentials.withheld}", err=True)
        os.environ.pop(USER_ENV, None)
        os.environ.pop(PASS_ENV, None)


def _with_config_injection(swarmit_group):
    """Wrap the swarmit group so `dotbot swarm` injects config-driven conn/swarm_id.

    A passthrough command that captures every token, prepends the resolved
    connection (unless the user gave it explicitly), and re-invokes swarmit.
    `--help` and subcommand help flow straight through.
    """
    _mount_native_lh2(swarmit_group)

    @click.command(
        name="swarm",
        help=_HELP,
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        add_help_option=False,
    )
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    @click.pass_context
    def cmd(ctx, args):
        args = list(args)
        # `calibrate-lh2` is PyDotBot-native (the homography solve lives
        # here, not in swarmit), so intercept it before the passthrough and
        # hand off to our own group, carrying the resolved config along.
        if args and args[0] == "calibrate-lh2":
            from dotbot.cli.swarm_lh2 import cmd as lh2_group

            lh2_group.main(
                args=args[1:],
                prog_name="dotbot swarm calibrate-lh2",
                standalone_mode=True,
                obj=ctx.obj,
            )
            return
        # `flash <name>` is PyDotBot sugar: resolve a bundled app name to its
        # fetched .bin path before handing off (an explicit path passes
        # through), and service `--list` without touching the transport.
        sub = subcommand_index(args, swarmit_group)
        if sub is not None and args[sub] == "flash":
            from dotbot.cli._swarm_flash import flash_help_epilog, resolve_flash_args

            flash_cmd = swarmit_group.commands.get("flash")
            if flash_cmd is not None and not flash_cmd.epilog:
                flash_cmd.epilog = flash_help_epilog()
            rest, handled = resolve_flash_args(args[sub + 1 :])
            if handled:
                return
            args = [*args[: sub + 1], *rest]
        if args and not any(arg in ("-h", "--help") for arg in args):
            _settle_connection(ctx, args, swarmit_group)
        final = inject_config(args, ctx.obj, swarmit_group) if args else args
        _run_swarmit(swarmit_group, final)

    return cmd


cmd = lazy_subcommand(
    name="swarm",
    extra="swarm",
    package="swarmit",
    help=_HELP,
    loader=_load_swarmit_group,
    transform=_with_config_injection,
)
