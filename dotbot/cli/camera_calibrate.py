# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot run camera-calibration` - register an overhead camera.

Two steps, one subcommand each: `sheets` renders the four printable ArUco
pages that go in the corners of an area as one A4 PDF, and `collect`
reads them back through the camera and solves the homography from image
pixels into the site's frame. Both run on your own machine and nothing
here reaches a robot, which is why this sits under `run` beside
`lh2-calibration` rather than under `swarm`.

opencv-python and pillow live behind the `[calibrate]` extra, so they are
imported at invocation and a missing extra prints an install hint instead
of a traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from dotbot.calibration.camera import (
    SCALE_BAR_MM,
    SHEET_FORMATS,
    render_sheets,
    write_sheets,
)


@click.group(
    name="camera-calibration",
    help="Overhead-camera registration: print the ArUco sheets, then capture.",
    invoke_without_command=True,
)
@click.pass_context
def cmd(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    # Bare `dotbot run camera-calibration` defaults to collect, the step
    # run again every time the camera moves, as `run lh2-calibration` does.
    ctx.invoke(collect)


@cmd.command(name="sheets")
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=".",
    help="Where to write the sheets. Default: the current directory.",
)
@click.option(
    "--format",
    "sheet_format",
    type=click.Choice(SHEET_FORMATS),
    default="pdf",
    show_default=True,
    help="pdf is the four pages as one print job; png is one image per sheet.",
)
@click.option(
    "--per-sheet",
    is_flag=True,
    help=(
        "Write one single-page PDF per sheet instead of one four-page file. "
        "What a printer forcing double-sided output needs: a four-page job "
        "comes back as two sheets with a marker on each face. No effect on "
        "png, which is already one file per sheet."
    ),
)
def sheets(out_dir: str, sheet_format: str, per_sheet: bool) -> None:
    """Render the four printable ArUco sheets, one per area corner."""
    try:
        pages = render_sheets()
    except ImportError as exc:
        click.echo(
            "`dotbot run camera-calibration sheets` needs the calibration "
            "runtime deps (opencv-python, pillow).\n"
            "Install with:  pip install pydotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for path in write_sheets(pages, out, sheet_format, per_sheet):
        click.echo(str(path))
    click.echo(
        f"Print at 100 % (no scale-to-fit); check the {SCALE_BAR_MM:g} mm bar "
        "with a ruler.\n"
        "Tape each sheet inside the corner it names, its two outer edges on "
        "the area's edge lines, page top toward the top of the map.",
        err=True,
    )


@cmd.command(name="collect")
def collect() -> None:
    """Capture the sheets through the camera and solve the homography."""
    click.echo(
        "`collect` is not built yet. Until it is, "
        "`dotbot run camera-calibration sheets --out <dir>` renders the "
        "pages to print and tape down.",
        err=True,
    )
    sys.exit(1)
