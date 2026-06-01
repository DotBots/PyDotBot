# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot deployment` - list / show / switch the configured deployments.

A deployment is one named physical deployment (Inria/100, La Poste/1000, ...)
defined by a `[deployment.<name>]` table in the config file. You *select* one
(`--deployment` / `DOTBOT_DEPLOYMENT` / `default_deployment`) per invocation;
`deployment use` writes the `default_deployment` for you, so switching is one
command rather than a hand edit. `list` / `show` are read-only inspectors.
"""

import re
from pathlib import Path

import click


@click.group(
    name="deployment",
    help="List / show deployments; switch the default with `use`.",
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


# A `default_deployment = ...` line, active or commented-out, so `use` can
# rewrite it in place and leave everything else (comments included) intact.
_ACTIVE_DEFAULT_RE = re.compile(r"^\s*default_deployment\s*=")
_ANY_DEFAULT_RE = re.compile(r"^\s*#?\s*default_deployment\s*=")


def _set_default_deployment(path: Path, name: str) -> None:
    """Write `default_deployment = "<name>"` into `path`, preserving the rest.

    Replaces the existing `default_deployment` line (an active one first, else
    a commented-out one like the `config init` starter ships); when neither
    exists, inserts the key before the first `[table]` header so it stays a
    valid top-level TOML key.
    """
    new_line = f'default_deployment = "{name}"'
    lines = path.read_text().splitlines()

    active = [i for i, line in enumerate(lines) if _ACTIVE_DEFAULT_RE.match(line)]
    any_match = [i for i, line in enumerate(lines) if _ANY_DEFAULT_RE.match(line)]
    target = active[0] if active else (any_match[0] if any_match else None)

    if target is not None:
        lines[target] = new_line
    else:
        insert_at = next(
            (i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
            len(lines),
        )
        lines.insert(insert_at, new_line)
    path.write_text("\n".join(lines) + "\n")


@cmd.command()
@click.argument("name")
@click.pass_context
def use(ctx, name):
    """Set NAME as the default deployment, writing it to the active config file.

    Updates `default_deployment` in the file `dotbot` is currently using (the
    one `dotbot config path` reports), keeping the rest of the file - comments
    included - intact. NAME must be a defined `[deployment.<name>]`.
    """
    obj = ctx.obj or {}
    config = obj.get("config")
    config_path = obj.get("config_path")

    if config_path is None:
        raise click.ClickException(
            "no config file in use to write to; create one with "
            "`dotbot config init` (or point at one with `dotbot -c PATH`)."
        )
    deployments = config.deployment if config is not None else {}
    if name not in deployments:
        known = ", ".join(sorted(deployments)) or "(none defined)"
        raise click.ClickException(
            f"unknown deployment {name!r}; defined deployments: {known}"
        )

    _set_default_deployment(Path(config_path), name)
    click.echo(f"Set default deployment to {name!r} in {config_path}")
