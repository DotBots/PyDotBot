# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` — fleet operations over the air (status/start/stop/flash/...).

Mounts the upstream `swarmit` Click group as the `dotbot swarm` parent:
operators get `status|start|stop|flash|monitor|reset|message|serve` with their
existing flags, plus the PyDotBot-native `lh2-calibration collect|push`.
`swarm` is strictly the *many-devices, over-the-radio* namespace.

Single-device, cabled operations moved out: firmware-artifact build/fetch/
list live under `dotbot fw`, and per-device flashing/inspection (including
what used to be `swarm provision …`) lives under `dotbot device`.

swarmit has its own config loader, so the unified `dotbot.toml` is bridged in
at the mount boundary: `conn` / `swarm_id` resolved by the root group are
translated into swarmit's flags (see `_swarm_inject`), so `dotbot swarm status`
inherits a saved deployment like every other command. An explicit swarmit
`--conn` / `--swarm-id` / `-c` still wins.
"""

import click

from dotbot.cli._lazy import lazy_subcommand
from dotbot.cli._swarm_inject import inject_config

_HELP = (
    "Fleet ops over the air: status, start/stop, OTA-flash, monitor, "
    "reset, lh2-calibration. Wraps swarmit."
)


def _load_swarmit_group():
    from swarmit.cli.main import main as swarmit_group

    return swarmit_group


def _run_swarmit(
    swarmit_group, args
):  # pragma: no cover - delegates to swarmit (needs MQTT/serial)
    swarmit_group.main(args=args, prog_name="dotbot swarm", standalone_mode=True)


def _with_config_injection(swarmit_group):
    """Wrap the swarmit group so `dotbot swarm` injects config-driven conn/swarm_id.

    A passthrough command that captures every token, prepends the resolved
    connection (unless the user gave it explicitly), and re-invokes swarmit.
    `--help` and subcommand help flow straight through.
    """

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
        # `lh2-calibration` is PyDotBot-native (the homography solve lives
        # here, not in swarmit), so intercept it before the passthrough and
        # hand off to our own group, carrying the resolved config along.
        if args and args[0] == "lh2-calibration":
            from dotbot.cli.swarm_lh2 import cmd as lh2_group

            lh2_group.main(
                args=args[1:],
                prog_name="dotbot swarm lh2-calibration",
                standalone_mode=True,
                obj=ctx.obj,
            )
            return
        # `flash <name>` is PyDotBot sugar: resolve a bundled app name to its
        # fetched .bin path before handing off (an explicit path passes
        # through), and service `--list` without touching the transport.
        if args and args[0] == "flash":
            from dotbot.cli._swarm_flash import flash_help_epilog, resolve_flash_args

            flash_cmd = swarmit_group.commands.get("flash")
            if flash_cmd is not None and not flash_cmd.epilog:
                flash_cmd.epilog = flash_help_epilog()
            rest, handled = resolve_flash_args(args[1:])
            if handled:
                return
            args = ["flash", *rest]
        final = inject_config(args, ctx.obj) if args else args
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
