# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm calibrate-lh2` - over-the-air LH2 calibration.

The fleet-side home for LH2 calibration: capture and send a calibration
without a serial cable, driving DotBots through the swarmit transport. Two
subcommands:

- `collect` - walk the robots through a placement's points, trigger a
              raw-count capture per point over the air, solve every visible
              station by least squares, and save a schema 2 calibration
              under ~/.dotbot/calibrations/<site>/.
- `push <path|id>` - check the robots' device info, send a saved
              calibration over the air, and list the robots still on
              another id.
- `reframe <path|id>` - re-express a saved calibration in another site's
              frame and re-solve it from its stored samples.

The homography solve lives in PyDotBot (`dotbot.calibration.lighthouse2`);
the transport lives in swarmit.

Serial-cable (single DK) calibration stays under
`dotbot run calibrate-lh2`.

Calibration runtime deps (`opencv-python`) live behind the `[calibrate]`
extra; ImportError at invocation prints an install hint instead of a
traceback.
"""

import sys
import time

import click

from dotbot.cli._site import site_from_context


def _swarmit_client(ctx, conn, swarm_id, device=None):
    """A swarmit client for this CLI invocation.

    Falls back to the unified dotbot config's `conn` / `swarm_id` (like
    `dotbot swarm`) when the flags are omitted, then hands off to the builder
    the controller uses, so the two cannot drift on what a connection string
    means.
    """
    if conn is None or swarm_id is None:
        from dotbot.config import resolve

        obj = ctx.obj or {}
        config = obj.get("config")
        deployment = obj.get("deployment")
        if conn is None:
            conn = resolve("conn", config=config, deployment=deployment)
        if swarm_id is None:
            swarm_id = resolve("swarm_id", config=config, deployment=deployment)

    from dotbot.swarm_client import build_swarmit_client

    return build_swarmit_client(conn, swarm_id, device)


@click.group(
    name="calibrate-lh2",
    help="Over-the-air LH2 calibration: collect, push, reframe.",
)
def cmd() -> None:
    pass


@cmd.command(
    name="collect",
    help=(
        "Collect an LH2 calibration over the air (no serial cable). Walks "
        "you through the points of one placement, triggers n captures per "
        "point via swarmit, solves every visible station, and saves the "
        "calibration."
    ),
)
@click.option(
    "--device",
    required=True,
    help="DotBot link-layer address in hex (e.g. BC3D3C8A2A6F8E68).",
)
@click.option(
    "-n",
    "--conn",
    "--connection",
    "conn",
    default=None,
    help=(
        "Swarm connection string: an MQTT broker `mqtts://host:port` or a "
        "serial gateway `/dev/ttyACM0`. Falls back to the dotbot config."
    ),
)
@click.option(
    "-s",
    "--swarm-id",
    "swarm_id",
    default=None,
    help="Swarm id in hex (required for an MQTT broker connection).",
)
@click.option(
    "--points",
    "points",
    multiple=True,
    help=(
        "Where this placement's points are, repeatable: `x,y` in frame mm, a "
        "rectangle (an area name, or `x,y,w,h` in mm) for its centre, "
        "`<rectangle>:<corner>`, or `<rectangle>:corners` for all four in "
        "capture order. A corner mark is where the photodiode lands with the "
        "robot inside the rectangle, PCB edges on its lines, nose toward the "
        "nearest top or bottom edge. Defaults to `arena:corners`."
    ),
)
@click.option(
    "--site",
    "site_name",
    default=None,
    help=(
        "The site the points are expressed in, and the directory the "
        "calibration is saved under. Defaults to `site` in the dotbot config."
    ),
)
@click.option(
    "--reads",
    default=None,
    type=int,
    help=(
        "Captures averaged per point. A single read costs about 60 % of the "
        "accuracy at every point of the field."
    ),
)
@click.option(
    "--timeout",
    default=None,
    type=float,
    help="Seconds to wait for each capture before re-triggering.",
)
@click.option(
    "--retries",
    default=None,
    type=int,
    help="Re-trigger this many times per capture before giving up.",
)
@click.option(
    "--tag",
    default=None,
    help=(
        'Optional session label (e.g. "arena-relay") added to the saved '
        "metadata, so calibrations stay self-describing."
    ),
)
@click.option(
    "--push",
    is_flag=True,
    help="Send the computed calibration back to the robots over the air.",
)
@click.pass_context
def _collect(
    ctx,
    device,
    conn,
    swarm_id,
    points,
    site_name,
    reads,
    timeout,
    retries,
    tag,
    push,
):
    try:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        from dotbot.calibration.ota import (
            CAPTURE_READS_DEFAULT,
            CAPTURE_RETRIES_DEFAULT,
            CAPTURE_TIMEOUT_DEFAULT,
            CaptureSession,
        )
        from dotbot.calibration.points import collect_header, point_prompt
        from dotbot.calibration.session import CalibrationSession, SessionError
    except ImportError as exc:
        click.echo(
            "`dotbot swarm calibrate-lh2 collect` needs the calibration "
            "runtime deps (opencv-python).\n"
            "Install with:  pip install pydotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    specs = list(points) or ["arena:corners"]
    site, site_source = site_from_context(ctx, site_name)
    try:
        session = CalibrationSession.resolve(
            specs,
            site=site,
            device=device,
            reads=reads if reads is not None else CAPTURE_READS_DEFAULT,
            timeout=timeout if timeout is not None else CAPTURE_TIMEOUT_DEFAULT,
            retries=retries if retries is not None else CAPTURE_RETRIES_DEFAULT,
        )
    except (SessionError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        client = _swarmit_client(ctx, conn, swarm_id, device)
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Could not reach the swarm: {exc}", err=True)
        sys.exit(1)

    with client:
        with CaptureSession(client, device, LH2_CALIB_TAG) as stream:
            # Give the transport's own connect/subscribe log lines a beat to
            # print before our prompts, so the two don't interleave on screen.
            time.sleep(0.2)
            click.echo(
                collect_header(
                    site, site_source, len(session.points), session.reads, device
                )
            )
            while not session.complete:
                outstanding = session.outstanding
                click.prompt(
                    "  "
                    + point_prompt(
                        outstanding.index,
                        len(session.points),
                        outstanding.placement,
                    ),
                    default="",
                    show_default=False,
                    prompt_suffix="",
                )
                try:
                    point = session.capture(stream)
                except TimeoutError as exc:
                    click.echo(f"  ! {exc}", err=True)
                    raise click.Abort()
                for sample in point.capture.samples:
                    counts = sample.mean_counts()
                    click.echo(
                        f"    station {sample.station}: {sample.reads} reads, "
                        f"mean count1={counts.count1:.1f} count2={counts.count2:.1f}"
                    )
                if point.capture.dropped:
                    click.echo(f"    {point.capture.drop_summary()}")

        try:
            calibration = session.save(tag=tag)
        except Exception as exc:
            click.echo(f"Failed to compute calibration: {exc}", err=True)
            sys.exit(1)
        for station in session.stations:
            click.echo(
                f"station {station.index}: {station.points} points, "
                f"residual {station.residual_mm:.3f} mm"
            )
        for index, seen in session.unsolved:
            click.echo(
                f"station {index}: seen at {seen} point(s), not solved "
                "(a homography needs 4)"
            )
        click.echo(f"\nCalibration saved to {session.saved_path}")
        click.echo(f"Calibration id {calibration.id}, site {site.name}")

        if push:
            _gated_push(client, calibration, devices=[device])
        else:
            click.echo(
                "To send it to the robots over the air:\n"
                f"  dotbot swarm calibrate-lh2 push {calibration.id8}"
            )


@cmd.command(
    name="push",
    help=(
        "Send a saved LH2 calibration to the robots over the air. Takes a "
        "file path or the id prefix of a file under "
        "~/.dotbot/calibrations/<site>/. Reads device info first: refuses "
        "robots on firmware older than float32 and robots that report "
        "another site, then lists the robots still on another id."
    ),
)
@click.argument("calibration")
@click.option(
    "-n",
    "--conn",
    "--connection",
    "conn",
    default=None,
    help=(
        "Swarm connection string: an MQTT broker `mqtts://host:port` or a "
        "serial gateway `/dev/ttyACM0`. Falls back to the dotbot config."
    ),
)
@click.option(
    "-s",
    "--swarm-id",
    "swarm_id",
    default=None,
    help="Swarm id in hex (required for an MQTT broker connection).",
)
@click.option(
    "--site",
    "site_name",
    default=None,
    help=(
        "The site to look the id up under. Defaults to `site` in the dotbot " "config."
    ),
)
@click.option(
    "--site-changed",
    is_flag=True,
    help=(
        "The robots really moved to the file's site: push even where they "
        "report another one."
    ),
)
@click.pass_context
def _push(ctx, calibration, conn, swarm_id, site_name, site_changed):
    from dotbot.calibration.lighthouse2 import (
        read_calibration_file,
        resolve_calibration_path,
    )

    site, _ = site_from_context(ctx, site_name)
    try:
        path = resolve_calibration_path(calibration, site=site.name)
        loaded = read_calibration_file(path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    client = _swarmit_client(ctx, conn, swarm_id)
    with client:
        _gated_push(client, loaded, site_changed=site_changed)


def _gated_push(client, calibration, site_changed=False, devices=None):
    """Check the robots' device info, push, and print the stale-id worklist."""
    from dotbot.calibration.lighthouse2 import calibration_payload
    from dotbot.calibration.push import PushRefused, gate_push, push_worklist

    try:
        payload = calibration_payload(calibration)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Reading device info...")
    try:
        check = gate_push(client, calibration, site_changed, devices)
    except PushRefused as exc:
        raise click.ClickException(f"push refused:\n{exc}") from exc
    if check.other_site:
        click.echo(
            f"{len(check.other_site)} robot(s) move to site "
            f"{calibration.site.name} (--site-changed)."
        )
    click.echo(
        f"Sending {len(calibration.stations)} calibration matrix/matrices "
        f"({len(payload)} B, id {calibration.id8}, site {calibration.site.name}) "
        f"to the swarm; {len(check.stale)} robot(s) hold another id..."
    )
    client.send_lh2_calibration(payload)
    click.echo("Sent.")
    stale = push_worklist(client, calibration, devices)
    if stale:
        click.echo(
            f"Still not on {calibration.id8} ({len(stale)}), push again: "
            + ", ".join(stale)
        )
    else:
        click.echo(f"Every robot reports {calibration.id8}.")


def _parse_shift(_ctx, _param, value):
    try:
        x, y = (float(v) for v in value.split(","))
    except ValueError as exc:
        raise click.BadParameter("takes two numbers in mm, `x,y`") from exc
    return (x, y)


@cmd.command(
    name="reframe",
    help=(
        "Re-express a saved calibration in another site's frame, without a "
        "capture: shift (and turn) every placement's points, re-solve every "
        "station from the stored samples, and save a new file with a new id "
        "under ~/.dotbot/calibrations/<site>/."
    ),
)
@click.argument("calibration")
@click.option(
    "--site",
    "site_name",
    required=True,
    help="The site to re-express it in, as declared in the dotbot config.",
)
@click.option(
    "--shift",
    required=True,
    callback=_parse_shift,
    help="Where the old frame's zero lands in the new one, `x,y` in mm.",
)
@click.option(
    "--rotate",
    type=float,
    default=0.0,
    show_default=True,
    help=(
        "Degrees to turn the points about the first placement's first point "
        "before shifting; positive turns x toward y."
    ),
)
@click.pass_context
def _reframe(ctx, calibration, site_name, shift, rotate):
    from dotbot.calibration.lighthouse2 import (
        read_calibration_file,
        reframe_calibration,
        resolve_calibration_path,
        write_calibration,
    )

    site, _ = site_from_context(ctx, site_name)
    if site.extent_mm is None and not site.anchor:
        raise click.ClickException(
            f"site {site_name!r} is not declared in the dotbot config; add a "
            f"[sites.{site_name}] table with its anchor and extent first"
        )
    try:
        source = read_calibration_file(resolve_calibration_path(calibration))
        reframed = reframe_calibration(source, site, shift, rotate)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    path = write_calibration(reframed)
    click.echo(
        f"Reframed {source.id8} (site {source.site.name}) into site {site.name}: "
        f"shift {shift[0]:g},{shift[1]:g} mm, rotate {rotate:g} deg"
    )
    before = {s.index: s.residual_mm for s in source.stations}
    for station in reframed.stations:
        was = before.get(station.index)
        was_text = "" if was is None else f" (was {was:.6f})"
        click.echo(
            f"station {station.index}: {station.points} points, "
            f"residual {station.residual_mm:.6f} mm{was_text}"
        )
    x0, y0, x1, y1 = reframed.valid_mm
    outside = [
        (x, y)
        for placement in reframed.placements
        for x, y in placement.points_mm
        if not (x0 <= x <= x1 and y0 <= y <= y1)
    ]
    if outside:
        click.echo(
            f"warning: {len(outside)} point(s) fall outside the site's "
            f"valid_mm {list(reframed.valid_mm)}; robots there would drop "
            "their positions",
            err=True,
        )
    click.echo(f"\nCalibration saved to {path}")
    click.echo(f"Calibration id {reframed.id}, site {site.name}")
