# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm fw` — TrustZone-sandbox firmware build/clean/targets/artifacts.

Sandbox apps live under `repos/DotBot-firmware/apps-sandbox/` and run as
non-secure user images inside the SwarmIT TrustZone bootloader; they
are OTA-flashed via `dotbot swarm flash`. The Makefile uses
`sandbox-<board>` as its `BUILD_TARGET` to route into `apps-sandbox/`
and emit `.bin` (what swarmit OTA flashes) instead of `.hex`.

This subgroup hides the `sandbox-` prefix from the user: typing
`dotbot swarm fw build --target dotbot-v3` invokes make with
`BUILD_TARGET=sandbox-dotbot-v3`.

Mounted on the `dotbot swarm` group by `dotbot/cli/swarm.py`.
"""

import click

from dotbot.cli._fw_helpers import (
    CONFIGS,
    DEFAULT_CONFIG,
    DEFAULT_SANDBOX_BOARD,
    SANDBOX_BOARDS,
    artifact_path,
    list_projects,
    resolve_firmware_repo,
    run_make,
    validate_sandbox_board,
)


@click.group(
    name="fw",
    help=(
        "Sandbox (TrustZone NS) firmware: build, clean, list boards, "
        "collect artifacts. For bare firmware that talks directly to the "
        "radio, see `dotbot fw`. Need a Makefile knob not covered by these "
        "flags? Use `dotbot make --help`."
    ),
)
def cmd():
    pass


def _target_option(f):
    """Reusable `--target/-t` option — same flag name as `dotbot fw`."""
    return click.option(
        "--target",
        "-t",
        default=DEFAULT_SANDBOX_BOARD,
        show_default=True,
        help=(
            "Board to build the sandbox firmware for (e.g. dotbot-v3, "
            "nrf5340dk — without the `sandbox-` prefix; the CLI adds it). "
            "See `dotbot swarm fw targets`."
        ),
    )(f)


def _project_option(f):
    return click.option(
        "--app",
        "-a",
        "project",
        type=str,
        default=None,
        help=(
            "Build a single sandbox app (e.g. `dotbot`, `motors`, `rgbled`). "
            "Default: build every sandbox app for the target."
        ),
    )(f)


def _config_option(f):
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
    """Build sandbox firmware (default target: dotbot-v3)."""
    validate_sandbox_board(target)
    build_target = f"sandbox-{target}"
    apps_to_build = [project] if project else list_projects(build_target)
    if project and project not in list_projects(build_target):
        raise click.ClickException(
            f"Sandbox app {project!r} is not available for target "
            f"{target!r}.\nAvailable: {', '.join(list_projects(build_target))}"
        )
    mode = "rebuild" if rebuild else "incremental"
    what = project or "all sandbox apps"
    click.echo(
        f"Building {what} for {target} sandbox ({config}, {mode})...", err=True
    )
    elapsed = run_make(
        build_target, config, project, rebuild=rebuild, quiet=not verbose
    )
    click.echo(f"✓ Built sandbox {target} in {elapsed:.1f}s", err=True)
    for app in apps_to_build:
        out = artifact_path(build_target, app, config)
        if out.is_file():
            click.echo(str(out))


@cmd.command()
@_target_option
@_config_option
@click.option("-v", "--verbose", is_flag=True, default=False)
def clean(target, config, verbose):
    """Clean SES build outputs (default target: dotbot-v3)."""
    validate_sandbox_board(target)
    click.echo(f"Cleaning {target} sandbox ({config})...", err=True)
    elapsed = run_make(
        f"sandbox-{target}", config, make_targets=["clean"], quiet=not verbose
    )
    click.echo(f"✓ Cleaned sandbox {target} in {elapsed:.1f}s", err=True)


@cmd.command(name="targets")
def list_targets():
    """List valid targets for `dotbot swarm fw build` (one per line)."""
    for b in sorted(SANDBOX_BOARDS):
        click.echo(b)


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
    """Build + collect canonical sandbox artifacts into `artifacts/`."""
    validate_sandbox_board(target)
    build_target = f"sandbox-{target}"
    if print_path:
        if not project:
            raise click.ClickException(
                "`--print-path` requires `--app NAME` — there is no canonical "
                "artifact path without a specific project."
            )
        click.echo(str(artifact_path(build_target, project, config)))
        return
    click.echo(f"Collecting artifacts for {target} sandbox ({config})...", err=True)
    elapsed = run_make(
        build_target, config, make_targets=["artifacts"], quiet=not verbose
    )
    click.echo(f"✓ Artifacts collected in {elapsed:.1f}s", err=True)
    artifacts_dir = resolve_firmware_repo() / "artifacts"
    if artifacts_dir.is_dir():
        for p in sorted(artifacts_dir.glob(f"*-{build_target}.bin")):
            click.echo(str(p))
