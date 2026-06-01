# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot testbed` - list / show configured deployments (read-only).

A testbed is one named physical deployment (Inria/100, La Poste/1000, ...)
defined by a `[testbed.<name>]` table in the config file. You *select* one
(`--testbed` / `DOTBOT_TESTBED` / `default_testbed`); you never edit the
file to switch. This group lets you see which deployments are defined and
which one is active. Writing the file (`testbed use`) is deferred.
"""

import click


@click.group(
    name="testbed",
    help="List / show configured testbeds (deployments).",
)
def cmd():
    pass


# The descriptive fields worth showing inline, in display order.
_FIELDS = ("conn", "swarm_id", "serial_port", "location", "bots")


def _testbed_fields(testbed) -> list[tuple[str, object]]:
    """The (name, value) pairs that are actually set on a testbed."""
    return [
        (field, getattr(testbed, field))
        for field in _FIELDS
        if getattr(testbed, field) is not None
    ]


@cmd.command(name="list")
@click.pass_context
def list_testbeds(ctx):
    """List configured testbed names, marking the active one (*)."""
    obj = ctx.obj or {}
    config = obj.get("config")
    active = obj.get("testbed_name")

    testbeds = config.testbed if config is not None else {}
    if not testbeds:
        click.echo("(no testbeds configured)")
        return

    for name in sorted(testbeds):
        marker = "* " if name == active else "  "
        click.echo(f"{marker}{name}")
        for field, value in _testbed_fields(testbeds[name]):
            click.echo(f"      {field}: {value}")


@cmd.command()
@click.argument("name")
@click.pass_context
def show(ctx, name):
    """Print one testbed's fields. Errors if NAME isn't defined."""
    obj = ctx.obj or {}
    config = obj.get("config")

    testbeds = config.testbed if config is not None else {}
    if name not in testbeds:
        known = ", ".join(sorted(testbeds)) or "(none defined)"
        raise click.ClickException(
            f"unknown testbed {name!r}; defined testbeds: {known}"
        )

    active = obj.get("testbed_name")
    suffix = " (active)" if name == active else ""
    click.echo(f"{name}{suffix}")
    fields = _testbed_fields(testbeds[name])
    if not fields:
        click.echo("  (no fields set)")
        return
    for field, value in fields:
        click.echo(f"  {field}: {value}")
