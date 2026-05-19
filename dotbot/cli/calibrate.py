# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot calibrate` — LH2 calibration TUI + exporter.

Native subgroup mounting the vendored `dotbot.calibration` package. The
default (no subcommand) runs the Textual TUI; `dotbot calibrate tui`
is an explicit alias for the same; `dotbot calibrate export PATH`
writes the C header for the swarmit bootloader bake-in.

Calibration runtime deps (`opencv-python`, `textual`) live behind the
`[calibrate]` extra; ImportError at subcommand invocation prints an
install hint instead of a traceback.
"""

import sys

import click


def _run_tui(ctx: click.Context) -> None:
    """Lazy-load the TUI Click command and hand off this process's argv tail."""
    try:
        from dotbot.calibration.cli import main as _tui_main
    except ImportError as exc:
        click.echo(
            "`dotbot calibrate` needs the calibration runtime deps "
            "(opencv-python, textual).\n"
            "Install with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)
    # Forward this process's argv tail (anything after `calibrate`) to the
    # TUI Click command. Click's parent group already consumed `calibrate`
    # itself, so ctx.args/ctx.parent.args don't carry the right tail —
    # let the TUI re-parse from a clean state.
    _tui_main.main(args=list(ctx.args), standalone_mode=True)


@click.group(
    name="calibrate",
    help="Run the LH2 calibration workflow (capture + export).",
    invoke_without_command=True,
)
@click.pass_context
def cmd(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    _run_tui(ctx)


@cmd.command(
    name="tui",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        help_option_names=[],
    ),
    add_help_option=False,
    help="Run the LH2 calibration TUI (same as `dotbot calibrate`).",
)
@click.pass_context
def _tui(ctx: click.Context) -> None:
    _run_tui(ctx)


@cmd.command(
    name="export",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        help_option_names=[],
    ),
    add_help_option=False,
)
@click.pass_context
def _export(ctx: click.Context) -> None:
    """Export saved calibration as a C header for the swarmit bootloader."""
    try:
        from dotbot.calibration.exporter import main as _exp_main
    except ImportError as exc:
        click.echo(
            "`dotbot calibrate export` needs the calibration runtime deps.\n"
            "Install with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)
    _exp_main.main(args=list(ctx.args), standalone_mode=True)
