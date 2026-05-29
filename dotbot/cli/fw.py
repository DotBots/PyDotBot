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
    resolve_firmware_repo,
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
        "`dotbot swarm fw`. Need a Makefile knob not covered by these flags? "
        "Use `dotbot make --help`."
    ),
)
def cmd():
    pass


def _target_option(f):
    """Reusable `--target/-t` option for build/clean/artifacts."""
    return click.option(
        "--target",
        "-t",
        default=DEFAULT_BARE_TARGET,
        show_default=True,
        help=(
            "BUILD_TARGET (e.g. dotbot-v3, nrf5340dk-app, sailbot-v1). "
            "See `dotbot fw targets` for the full list."
        ),
    )(f)


def _project_option(f):
    """Reusable `--app/-a NAME` option for build/clean/artifacts."""
    return click.option(
        "--app",
        "-a",
        "project",
        type=str,
        default=None,
        help=(
            "Build a single app (e.g. `dotbot`, `dotbot_gateway`). "
            "Default: build every app available for the target."
        ),
    )(f)


def _config_option(f):
    """Reusable `--config/-c` option for build/clean/artifacts."""
    return click.option(
        "--config",
        "-c",
        type=click.Choice(CONFIGS),
        default=DEFAULT_CONFIG,
        show_default=True,
    )(f)


@cmd.command()
@_target_option
@_project_option
@_config_option
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
    """Build bare DotBot firmware (default target: dotbot-v3)."""
    validate_bare_target(target)
    apps_to_build = [project] if project else list_projects(target)
    if project and project not in list_projects(target):
        raise click.ClickException(
            f"App {project!r} is not available for target {target!r}.\n"
            f"Available: {', '.join(list_projects(target))}"
        )
    mode = "rebuild" if rebuild else "incremental"
    what = project or "all apps"
    click.echo(f"Building {what} for {target} ({config}, {mode})...", err=True)
    elapsed = run_make(target, config, project, rebuild=rebuild, quiet=not verbose)
    click.echo(f"✓ Built {target} in {elapsed:.1f}s", err=True)
    # Echo each produced artifact path on its own stdout line so pipelines
    # like `dotbot fw build | xargs -n1 nrfjprog --program` work.
    for app in apps_to_build:
        out = artifact_path(target, app, config)
        if out.is_file():
            click.echo(str(out))


@cmd.command()
@_target_option
@_config_option
@click.option("-v", "--verbose", is_flag=True, default=False)
def clean(target, config, verbose):
    """Clean SES build outputs (default target: dotbot-v3)."""
    validate_bare_target(target)
    click.echo(f"Cleaning {target} ({config})...", err=True)
    elapsed = run_make(target, config, make_targets=["clean"], quiet=not verbose)
    click.echo(f"✓ Cleaned in {elapsed:.1f}s", err=True)


@cmd.command(name="targets")
def list_targets():
    """List valid BUILD_TARGETs for `dotbot fw build` (one per line)."""
    for t in sorted(BARE_TARGETS):
        click.echo(t)


@cmd.command()
@_target_option
@_project_option
@_config_option
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
    click.echo(f"Collecting artifacts for {target} ({config})...", err=True)
    elapsed = run_make(target, config, make_targets=["artifacts"], quiet=not verbose)
    click.echo(f"✓ Artifacts collected in {elapsed:.1f}s", err=True)
    # Echo every collected artifact path on its own stdout line so the user
    # sees what's in `artifacts/` without a separate `ls`.
    artifacts_dir = resolve_firmware_repo() / "artifacts"
    if artifacts_dir.is_dir():
        ext = "bin" if target.startswith("sandbox-") else "hex"
        for p in sorted(artifacts_dir.glob(f"*-{target}.{ext}")):
            click.echo(str(p))


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
