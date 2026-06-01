# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot deployment` - list / show configured deployments (read-only).

A deployment is one named physical deployment (Inria/100, La Poste/1000, ...)
defined by a `[deployment.<name>]` table in the config file. You *select* one
(`--deployment` / `DOTBOT_DEPLOYMENT` / `default_deployment`); you never edit the
file to switch. This group lets you see which deployments are defined and
which one is active. Writing the file (`deployment use`) is deferred.
"""

import click


@click.group(
    name="deployment",
    help="List / show configured deployments.",
)
def cmd():
    pass


# The descriptive fields worth showing inline, in display order.
_FIELDS = ("conn", "swarm_id", "serial_port", "location", "bots")


def _deployment_fields(deployment) -> list[tuple[str, object]]:
    """The (name, value) pairs that are actually set on a deployment."""
    return [
        (field, getattr(deployment, field))
        for field in _FIELDS
        if getattr(deployment, field) is not None
    ]


@cmd.command(name="list")
@click.pass_context
def list_deployments(ctx):
    """List configured deployment names, marking the active one (*)."""
    obj = ctx.obj or {}
    config = obj.get("config")
    active = obj.get("deployment_name")

    deployments = config.deployment if config is not None else {}
    if not deployments:
        click.echo("(no deployments configured)")
        return

    for name in sorted(deployments):
        marker = "* " if name == active else "  "
        click.echo(f"{marker}{name}")
        for field, value in _deployment_fields(deployments[name]):
            click.echo(f"      {field}: {value}")


@cmd.command()
@click.argument("name")
@click.pass_context
def show(ctx, name):
    """Print one deployment's fields. Errors if NAME isn't defined."""
    obj = ctx.obj or {}
    config = obj.get("config")

    deployments = config.deployment if config is not None else {}
    if name not in deployments:
        known = ", ".join(sorted(deployments)) or "(none defined)"
        raise click.ClickException(
            f"unknown deployment {name!r}; defined deployments: {known}"
        )

    active = obj.get("deployment_name")
    suffix = " (active)" if name == active else ""
    click.echo(f"{name}{suffix}")
    fields = _deployment_fields(deployments[name])
    if not fields:
        click.echo("  (no fields set)")
        return
    for field, value in fields:
        click.echo(f"  {field}: {value}")
