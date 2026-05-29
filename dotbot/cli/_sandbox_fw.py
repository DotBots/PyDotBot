# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm fw` — TrustZone-sandbox firmware build/clean/targets/artifacts.

Sandbox apps live under `repos/DotBot-firmware/apps-sandbox/` and run as
non-secure user images inside the SwarmIT TrustZone bootloader; they are
OTA-flashed via `dotbot swarm flash`. The Makefile uses `sandbox-<BOARD>`
as the `BUILD_TARGET` to route into `apps-sandbox/` and emit `.bin`
(what swarmit OTA flashes) instead of `.hex`. This subgroup hides the
`sandbox-` prefix — the user types `dotbot swarm fw build dotbot-v3`
and the CLI prepends it before invoking make.

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


def _board_to_target(board: str) -> str:
    return f"sandbox-{board}"


def _project_option(f):
    return click.option(
        "--app",
        "project",
        type=str,
        default=None,
        help=(
            "Build a single sandbox app (e.g. `dotbot`, `motors`, `rgbled`). "
            "Default: build every sandbox app for BOARD."
        ),
    )(f)


@cmd.command()
@click.argument("board", default=DEFAULT_SANDBOX_BOARD)
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
def build(board, project, config, rebuild, verbose):
    """Build sandbox firmware for BOARD (default: dotbot-v3)."""
    validate_sandbox_board(board)
    target = _board_to_target(board)
    if project:
        valid = list_projects(target)
        if project not in valid:
            raise click.ClickException(
                f"Sandbox app {project!r} is not available for board "
                f"{board!r}.\nAvailable: {', '.join(valid)}"
            )
    run_make(target, config, project, rebuild=rebuild, quiet=not verbose)
    if project:
        out = artifact_path(target, project, config)
        if out.is_file():
            click.echo(str(out))


@cmd.command()
@click.argument("board", default=DEFAULT_SANDBOX_BOARD)
@click.option(
    "--config",
    type=click.Choice(CONFIGS),
    default=DEFAULT_CONFIG,
    show_default=True,
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def clean(board, config, verbose):
    """Clean SES build outputs for BOARD (per BUILD_CONFIG)."""
    validate_sandbox_board(board)
    run_make(_board_to_target(board), config, make_targets=["clean"], quiet=not verbose)


@cmd.command(name="targets")
def list_targets():
    """List valid BOARDs for `dotbot swarm fw build` (one per line)."""
    for b in sorted(SANDBOX_BOARDS):
        click.echo(b)


@cmd.command()
@click.argument("board", default=DEFAULT_SANDBOX_BOARD)
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
def artifacts(board, project, config, print_path, verbose):
    """Build + collect canonical sandbox artifacts into `artifacts/`."""
    validate_sandbox_board(board)
    target = _board_to_target(board)
    if print_path:
        if not project:
            raise click.ClickException(
                "`--print-path` requires `--app NAME` — there is no canonical "
                "artifact path without a specific project."
            )
        click.echo(str(artifact_path(target, project, config)))
        return
    run_make(target, config, make_targets=["artifacts"], quiet=not verbose)
