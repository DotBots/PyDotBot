# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot calibrate-lh2` — LH2 calibration (serial side).

Native subgroup mounting the vendored `dotbot.calibration` package.
Serial-attached, single-device operations. OTA / swarm-wide
counterparts will live under `dotbot testbed calibrate-lh2` (see
plans/ideas/testbed-scale-lh2-calibration.md).

Subcommands:

- `collect`  — capture LH2 counts via the Textual TUI from a single
               serial-attached nRF DK; writes ~/.dotbot/calibration.out.
- `apply <path>` — write the saved calibration as a C header to
               <path>. Today the only consumer is the swarmit secure
               bootloader (it #includes the file at compile time).

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
            "`dotbot calibrate-lh2 collect` needs the calibration runtime "
            "deps (opencv-python, textual).\n"
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
    name="calibrate-lh2",
    help="LH2 calibration: capture, apply, export (serial-side / single device).",
    invoke_without_command=True,
)
@click.pass_context
def cmd(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    # Bare `dotbot calibrate-lh2` with no subcommand defaults to collect,
    # matching the pre-rename `dotbot calibrate` behavior so muscle
    # memory still works.
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


@cmd.command(
    name="apply",
    help=(
        "Write the saved calibration as a C header to PATH. Today the "
        "consumer is the swarmit secure bootloader (#includes the file "
        "at compile time). OTA / runtime equivalents will live under "
        "`dotbot testbed calibrate-lh2 apply`."
    ),
)
@click.argument(
    "path",
    type=click.Path(dir_okay=False, writable=True),
)
def _apply(path: str) -> None:
    try:
        from dotbot.calibration.exporter import export_calibration
        from dotbot.calibration.lighthouse2 import LighthouseManager
    except ImportError as exc:
        click.echo(
            "`dotbot calibrate-lh2 apply` needs the calibration runtime "
            "deps.\nInstall with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    lh2_manager = LighthouseManager()
    calibrations = lh2_manager.load_calibration()
    if not calibrations:
        click.echo(
            "No saved calibration found at "
            f"{lh2_manager.calibration_output_path}.\n"
            "Run `dotbot calibrate-lh2 collect` first.",
            err=True,
        )
        sys.exit(1)

    output = export_calibration(calibrations)
    with open(path, "w") as f:
        f.write(output)
    click.echo(f"Wrote calibration ({len(calibrations)} matrices) to {path}")
