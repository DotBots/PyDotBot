# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot fw` — bare DotBot firmware build/clean/targets/artifacts.

Wraps `make BUILD_TARGET=... BUILD_CONFIG=...` in `repos/DotBot-firmware/`
using SES (`emBuild`) — see the workspace AGENTS.md "Firmware builds —
local SES" convention. `dotbot fw build` defaults to incremental
(passes `BUILD_MODE=-build`) for a fast edit/build loop; pass
`--rebuild` to force a full rebuild.

Sandbox apps (TrustZone NS, OTA-flashed via swarmit) live behind a
separate `dotbot swarm fw` subgroup — different mental model and
different consumer toolchain. See `dotbot/cli/_sandbox_fw.py`.

Subcommands `new` and `flash` remain mocked (Phase 1 scope is
build-only): firmware-scaffolding templates and the cabled-flash
toolchain pickling each warrant their own design pass.
"""

import sys

import click

from dotbot.cli._fw_helpers import (
    BARE_TARGETS,
    CONFIGS,
    DEFAULT_BARE_TARGET,
    DEFAULT_CONFIG,
    artifact_path,
    list_projects,
    run_make,
    validate_bare_target,
)

_NOT_READY = (
    "`dotbot fw {sub}` is not implemented yet.\n"
    "For now: use SEGGER Embedded Studio directly, or invoke the "
    "Makefile in `repos/DotBot-firmware`."
)


@click.group(
    name="fw",
    help=(
        "Bare DotBot firmware: build, clean, list targets, collect artifacts. "
        "For TrustZone sandbox apps that run inside swarmit, see "
        "`dotbot swarm fw`."
    ),
)
def cmd():
    pass


def _project_option(f):
    """Reusable `--app NAME` option for build/clean/artifacts."""
    return click.option(
        "--app",
        "project",
        type=str,
        default=None,
        help=(
            "Build a single app (e.g. `dotbot`, `dotbot_gateway`). "
            "Default: build every app available for TARGET."
        ),
    )(f)


@cmd.command()
@click.argument("target", default=DEFAULT_BARE_TARGET)
@_project_option
@click.option(
    "--config",
    type=click.Choice(CONFIGS),
    default=DEFAULT_CONFIG,
    show_default=True,
)
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Force full rebuild (pass `-rebuild` to emBuild). Default: incremental.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show full SES `-verbose -echo` output.",
)
def build(target, project, config, rebuild, verbose):
    """Build bare DotBot firmware for TARGET (default: dotbot-v3)."""
    validate_bare_target(target)
    if project:
        valid = list_projects(target)
        if project not in valid:
            raise click.ClickException(
                f"App {project!r} is not available for target {target!r}.\n"
                f"Available: {', '.join(valid)}"
            )
    run_make(target, config, project, rebuild=rebuild, quiet=not verbose)
    # Echo where to find the output on success.
    if project:
        out = artifact_path(target, project, config)
        if out.is_file():
            click.echo(str(out))


@cmd.command()
@click.argument("target", default=DEFAULT_BARE_TARGET)
@click.option(
    "--config",
    type=click.Choice(CONFIGS),
    default=DEFAULT_CONFIG,
    show_default=True,
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def clean(target, config, verbose):
    """Clean SES build outputs for TARGET (per BUILD_CONFIG)."""
    validate_bare_target(target)
    run_make(target, config, make_targets=["clean"], quiet=not verbose)


@cmd.command(name="targets")
def list_targets():
    """List valid BUILD_TARGETs for `dotbot fw build` (one per line)."""
    for t in sorted(BARE_TARGETS):
        click.echo(t)


@cmd.command()
@click.argument("target", default=DEFAULT_BARE_TARGET)
@_project_option
@click.option(
    "--config",
    type=click.Choice(CONFIGS),
    default=DEFAULT_CONFIG,
    show_default=True,
)
@click.option(
    "--print-path",
    is_flag=True,
    default=False,
    help="Print where the artifact lives without building.",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def artifacts(target, project, config, print_path, verbose):
    """Build + collect canonical artifacts into `artifacts/`."""
    validate_bare_target(target)
    if print_path:
        if not project:
            raise click.ClickException(
                "`--print-path` requires `--app NAME` — there is no canonical "
                "artifact path without a specific project."
            )
        click.echo(str(artifact_path(target, project, config)))
        return
    run_make(target, config, make_targets=["artifacts"], quiet=not verbose)


@cmd.command()
@click.argument("name")
@click.option(
    "--template",
    type=click.Choice(["swarmit-app", "bare"]),
    default="swarmit-app",
    show_default=True,
)
def new(name, template):  # pylint: disable=unused-argument
    """Scaffold a new firmware project (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="new"), err=True)
    sys.exit(2)


@cmd.command()
@click.argument("image", type=click.Path())
@click.option("--serial", type=str, help="J-Link / nRF serial number.")
@click.option(
    "--component",
    type=click.Choice(["app", "bootloader", "netcore"]),
    default="app",
    show_default=True,
)
@click.option("--gateway", is_flag=True, help="Flash a gateway bot.")
def flash(image, serial, component, gateway):  # pylint: disable=unused-argument
    """USB-cable flash an image to a single bot (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="flash"), err=True)
    sys.exit(2)
