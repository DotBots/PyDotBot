# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot calibrate-lh2` — LH2 calibration (serial side).

Native subgroup mounting the vendored `dotbot.calibration` package.
Serial-attached, single-device operations. OTA / swarm-wide
counterparts live under `dotbot testbed calibrate-lh2` (today only
`apply` exists there, via the swarmit lazy mount; `collect` over OTA
is a future addition — see plans/ideas/testbed-scale-lh2-calibration.md).

Subcommands:

- `collect`  — capture LH2 counts via the Textual TUI from a single
               serial-attached nRF DK; writes ~/.dotbot/calibration.out.
- `apply`    — write a saved calibration to a single serial-attached
               device's flash. `--sandbox` targets swarmit's config
               page; `--bare` targets bare-metal firmware's slot
               (gated on firmware work; stubbed today).
- `export`   — write the C header for compile-time bake-in to the
               swarmit secure bootloader. Legacy path for the
               compile-time-baked workflow; prefer `apply --sandbox`
               for runtime updates.

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
    help="Write a saved calibration to a serial-attached device's flash.",
)
@click.option(
    "--sandbox",
    "target",
    flag_value="sandbox",
    default=True,
    help="Target swarmit's config page (default).",
)
@click.option(
    "--bare",
    "target",
    flag_value="bare",
    help="Target bare-metal firmware's calibration slot (NOT YET IMPLEMENTED).",
)
@click.argument(
    "calibration_path",
    type=click.Path(dir_okay=False),
    required=False,
)
def _apply(target: str, calibration_path: str | None) -> None:
    """Write a saved calibration to a single serial-attached device.

    Currently both targets are stubs. The implementation path:

    - `--sandbox` (swarmit): extend `dotbot/provision/` to support a
      partial config-page rewrite that preserves the existing net_id
      and replaces only the calibration matrices. Today, the closest
      working flow is to re-provision the device with
      `dotbot testbed provision flash --calibration <path> ...` —
      that flashes everything including calibration. For OTA-only
      calibration replacement on already-running bots, use
      `dotbot testbed calibrate-lh2` (the swarmit OTA command).
    - `--bare`: gated on firmware work — bare-metal apps don't have
      a runtime calibration slot today; the only path is the
      compile-time C-header bake-in (see `dotbot calibrate-lh2
      export`).
    """
    if target == "bare":
        click.echo(
            "`dotbot calibrate-lh2 apply --bare` is not yet implemented.\n"
            "Bare-metal firmware has no runtime calibration slot today; "
            "use `dotbot calibrate-lh2 export <dir>` to bake the\n"
            "calibration into the firmware at compile time.",
            err=True,
        )
        sys.exit(2)
    # --sandbox stub
    click.echo(
        "`dotbot calibrate-lh2 apply --sandbox` is not yet implemented.\n"
        "Working alternatives until this lands:\n"
        "  • Re-provision: `dotbot testbed provision flash --calibration "
        f"{calibration_path or '<path>'} -d dotbot-v3 ...`\n"
        "  • OTA push to running bots: `dotbot testbed calibrate-lh2 "
        f"{calibration_path or '<path>'}`",
        err=True,
    )
    sys.exit(2)


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
    """Export saved calibration as a C header for compile-time bake-in."""
    try:
        from dotbot.calibration.exporter import main as _exp_main
    except ImportError as exc:
        click.echo(
            "`dotbot calibrate-lh2 export` needs the calibration runtime "
            "deps.\nInstall with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)
    _exp_main.main(args=list(ctx.args), standalone_mode=True)
