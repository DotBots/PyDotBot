# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot demo` — discoverable launcher for built-in research demos.

Demos live in `dotbot/examples/`. Each demo is a Level-3 consumer of
the controller's REST/WS API (see the access-levels architecture in
plans/dotbot-consolidation-roadmap.md). Adding a new demo means
dropping a Click command somewhere under `dotbot/examples/` and
registering it below.
"""

import click

from dotbot.examples.qrkey_demo.cli import main as _qrkey_main


@click.group(
    name="demo",
    help="Built-in research demos (qrkey phone bridge, formations, ...).",
    invoke_without_command=True,
)
@click.option(
    "--list",
    "list_demos",
    is_flag=True,
    help="List available demos.",
)
@click.pass_context
def cmd(ctx, list_demos):
    if list_demos or ctx.invoked_subcommand is None:
        click.echo("Available demos:")
        for name, sub in cmd.commands.items():
            short = (sub.help or "").splitlines()[0] if sub.help else ""
            click.echo(f"  {name:<12} {short}")
        click.echo("")
        click.echo("Run one with: dotbot demo <name> [OPTIONS]")
        ctx.exit(0)


# Register demos. New entries go here. Keep the alias short (the
# subcommand IS the discovery surface — long names defeat the point).
# We pass `name=...` rather than mutating `_qrkey_main.name` so the
# demo's own test suite (which imports the same Click command) stays
# unaffected.
cmd.add_command(_qrkey_main, name="qr")
