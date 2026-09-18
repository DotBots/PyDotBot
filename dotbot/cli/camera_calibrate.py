# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot run camera-calibration` - register an overhead camera.

Two steps, one subcommand each: `sheets` renders the four printable ArUco
pages that go in the corners of an area, and `collect` finds the camera
that sees them, reads them back and solves the homography from image
pixels into the site's frame. Both run on your own machine and nothing
here reaches a robot, which is why this sits under `run` beside
`lh2-calibration` rather than under `swarm`.

opencv-python and pillow live behind the `[calibrate]` extra, so they are
imported at invocation and a missing extra prints an install hint instead
of a traceback.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import click

from dotbot.camera.capture import (
    PROBE_INDEX_MAX,
    READS_DEFAULT,
    average_corners,
    build_detector,
    capture_reads,
    choose,
    controls_string,
    discover,
    open_capture,
    parse_source,
    probe,
    write_annotated,
    write_probe_frames,
)
from dotbot.camera.registration import (
    LENS_DEFAULT,
    RESIDUAL_WARN_MM,
    build_calibration,
    collect_header,
    sheet_prompt,
    solve,
    write_camera_calibration,
)
from dotbot.camera.sheets import (
    SCALE_BAR_MM,
    SHEET_FORMATS,
    corner_of,
    layout_ids,
    marker_layout,
    render_sheets,
    write_sheets,
)
from dotbot.cli._site import site_from_context


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
@click.option(
    "--area",
    "area_name",
    required=True,
    help=(
        "The one area this camera covers: a name from the site's "
        "`[sites.<site>.areas.<name>]` tables, `x,y,w,h` in frame mm, or a "
        "`+`-joined composite. The four sheet positions are derived from its "
        "corners."
    ),
)
@click.option(
    "--site",
    "site_name",
    default=None,
    help=(
        "The site the area belongs to, and the directory the registration is "
        "saved under. Defaults to `site` in the dotbot config."
    ),
)
@click.option(
    "--camera",
    "camera_spec",
    default=None,
    help=(
        "Skip the search and use this source: an OpenCV index, or a path (a "
        "/dev/v4l/by-id/ symlink, or a recorded frame to rehearse against). "
        "With no --camera every index is probed and the one that sees the "
        "sheets is used."
    ),
)
@click.option(
    "--reads",
    default=None,
    type=int,
    help=(
        "Frames averaged. Only a frame carrying all four markers counts; a "
        f"black one is counted apart. Default: {READS_DEFAULT}."
    ),
)
@click.option(
    "--lens",
    default=LENS_DEFAULT,
    show_default=True,
    help=(
        "The lens mode the camera is set to, recorded in the file. The fit is "
        "to raw pixels, so it holds only for a rectilinear image and only in "
        "the mode it was solved in; another mode means collecting again."
    ),
)
@click.pass_context
def collect(
    ctx: click.Context,
    area_name: str,
    site_name: str | None,
    camera_spec: str | None,
    reads: int | None,
    lens: str,
) -> None:
    """Capture the sheets through the camera and solve the homography."""
    if not area_name:
        raise click.UsageError(
            "Missing option '--area'. Name the one area this camera covers, "
            "so the four sheet positions can be derived from its corners."
        )
    try:
        detector = build_detector()
    except ImportError as exc:
        click.echo(
            "`dotbot run camera-calibration collect` needs the calibration "
            "runtime deps (opencv-python).\n"
            "Install with:  pip install pydotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    site, _ = site_from_context(ctx, site_name)
    try:
        area = site.registry().resolve(area_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    reads = READS_DEFAULT if reads is None else reads
    if reads < 1:
        raise click.UsageError(f"--reads {reads}: at least one read is needed.")

    layout = marker_layout(area)
    ids = layout_ids()
    click.echo(collect_header(site, area, reads))
    for marker in layout:
        click.echo("  " + sheet_prompt(marker, area))
    click.prompt(
        "\nPress Enter when the four sheets are down",
        default="",
        show_default=False,
        prompt_suffix="",
    )
    click.echo()

    chosen = _find_camera(camera_spec, ids, detector)
    corners_px, tally, last = _read_sheets(chosen, ids, reads, detector, area)
    try:
        solution = solve(layout, corners_px)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    _warn_on_residual(solution, area)

    calibration = build_calibration(
        site=site,
        area=area,
        layout=layout,
        corners_px=corners_px,
        solution=solution,
        probe_result=chosen,
        reads=tally.target,
        lens=lens,
    )
    path = write_camera_calibration(calibration)
    written = str(path)
    if last is not None:
        image = path.with_suffix(".jpg")
        write_annotated(last, corners_px, image)
        written += f" (and {image.name})"
    click.echo(f"wrote {written}")
    click.echo(
        f"residual {solution.residual_mm:.1f} mm over {4 * len(layout)} "
        f"corners, id {calibration.id}, site {site.name}"
    )
    if calibration.controls:
        click.echo(f"colour controls recorded: {controls_string(calibration.controls)}")
    click.echo(
        "To draw it on the console map:\n"
        f"  dotbot run controller --camera-calibration {calibration.id8}"
    )


def _find_camera(camera_spec, ids, detector):
    """The source that sees the sheets, with the table that chose it."""
    if camera_spec is None:
        click.echo(f"probing sources from 0 (stopping at {PROBE_INDEX_MAX})")
        probes = discover(detector=detector)
    else:
        probes = [probe(parse_source(camera_spec), detector=detector)]
    for found in probes:
        click.echo("  " + found.row)

    frames = Path(tempfile.mkdtemp(prefix="dotbot-camera-probe-"))
    if write_probe_frames(probes, frames):
        click.echo(f"probe frames: {frames}")

    choice = choose(probes, ids)
    if not choice.chosen:
        click.echo(f"\n{choice.reason}.", err=True)
        click.echo(
            "Look at the probe frames, then name the source: " "--camera <index|path>.",
            err=True,
        )
        sys.exit(1)
    click.echo(choice.reason)
    return choice.probe


def _read_sheets(chosen, ids, reads, detector, area):
    """The averaged corners of one source, or an exit naming what was missing.

    The source is opened again rather than carried over from the probe: a
    recorded frame delivers exactly one image, so the probe exhausts it, and
    reopening is also what runs the warm-up again before the reads.
    """
    capture = open_capture(chosen.source)
    if not capture.isOpened():
        raise click.ClickException(
            f"source {chosen.source} opened for the probe and will not open "
            "again for the reads."
        )
    try:
        kept, tally, last = capture_reads(capture, ids, reads, detector)
    finally:
        capture.release()
    click.echo(tally.summary)

    if tally.extra:
        listed = " ".join(str(i) for i in tally.extra)
        click.echo(
            f"ignoring marker(s) {listed}: not in {area.name}'s layout", err=True
        )
    if not kept:
        click.echo("", err=True)
        if tally.missing:
            listed = " ".join(str(i) for i in tally.missing)
            click.echo(
                f"No read carried all four markers (never saw {listed}), so "
                "nothing was written. Check those sheets are in frame, flat "
                "and unshadowed.",
                err=True,
            )
        else:
            click.echo(
                "No read carried all four markers, so nothing was written. "
                "Check the sheets are down and the camera is over them.",
                err=True,
            )
        sys.exit(1)
    if tally.complete < tally.target:
        click.echo(
            f"only {tally.complete} of {tally.target} reads carried all four "
            "markers; the fit is over those.",
            err=True,
        )
    return average_corners(kept, ids), tally, last


def _warn_on_residual(solution, area):
    """Name the sheet that fits worst when the whole fit is out of tolerance."""
    if solution.residual_mm <= RESIDUAL_WARN_MM:
        return
    worst_id, worst_mm = solution.worst
    click.echo(
        f"residual {solution.residual_mm:.1f} mm is over "
        f"{RESIDUAL_WARN_MM:g} mm, so this registration is suspect. "
        f"Marker {worst_id} sits {worst_mm:.1f} mm from where {area.name}'s "
        f"{corner_of(worst_id)} corner puts it: check that sheet is in "
        "the corner it names, flush on both edge lines, printed at 100 %, and "
        "inside the area.",
        err=True,
    )
