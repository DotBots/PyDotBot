# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot run lh2-calibration` - LH2 calibration.

Native subgroup mounting the vendored `dotbot.calibration` package, for
single-device calibration over either transport.

Subcommands:

- `collect`  — capture LH2 counts via the Textual TUI from a single
               serial-attached nRF DK; writes a schema 2 calibration file
               under ~/.dotbot/calibrations/<site>/.

Cable-free, over-the-air calibration of a DotBot in the arena lives under
`dotbot swarm lh2-calibration` (it drives the fleet transport, not a serial
DK).

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
            "`dotbot run lh2-calibration collect` needs the calibration "
            "runtime deps (opencv-python, textual).\n"
            "Install with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)
    # Forward this process's argv tail (anything after `collect`) to the
    # TUI Click command. Click's parent group already consumed the
    # subcommand name itself, so ctx.args/ctx.parent.args don't carry
    # the right tail — let the TUI re-parse from a clean state.
    _tui_main.main(args=list(ctx.args), standalone_mode=True)


@click.group(
    name="lh2-calibration",
    help="LH2 calibration for one serial-attached device: capture.",
    invoke_without_command=True,
)
@click.pass_context
def cmd(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    # Bare `dotbot run lh2-calibration` with no subcommand defaults to
    # collect — the most common action — so it works without recalling
    # the subcommand name.
    _run_tui(ctx)


@cmd.command(
    name="collect",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        help_option_names=[],
    ),
    add_help_option=False,
    help="Capture LH2 counts via the Textual TUI (serial-attached DK).",
)
@click.pass_context
def _collect(ctx: click.Context) -> None:
    _run_tui(ctx)
