# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm calibrate-lh2` - over-the-air LH2 calibration.

The fleet-side home for LH2 calibration: capture and send a calibration
without a serial cable, driving DotBots through the swarmit transport. Two
subcommands:

- `collect` - walk the robots through a placement's points, take a
              raw-count capture per point over the air (the robot's button,
              or Enter with --device), solve every visible station by least
              squares, and save a schema 3 calibration under
              ~/.dotbot/calibrations/<site>/. With --spin, the robots
              spin in place instead and the circles they trace are solved
              (`dotbot.calibration.spin`).
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

import queue
import sys
import threading
import time

import click

from dotbot.cli._site import site_from_context

# Where `dotbot swarm` hands over the options given before `calibrate-lh2`
SWARM_OPTIONS = "swarm_options"


def _swarm_option(ctx, name):
    return ((ctx.obj or {}).get(SWARM_OPTIONS) or {}).get(name)


def _devices(ctx) -> list[str] | None:
    """The robots `dotbot swarm -d` named, upper case; None for the swarm."""
    raw = _swarm_option(ctx, "devices") or ""
    devices = [d.strip().upper() for d in raw.split(",") if d.strip()]
    return devices or None


def _swarmit_client(ctx, conn, swarm_id):
    """A swarmit client for this CLI invocation.

    Falls back to the unified dotbot config's `conn` / `swarm_id` (like
    `dotbot swarm`), the active site's `[connection]` included, when the
    flags are omitted, then hands off to the builder the controller uses, so
    the two cannot drift on what a connection string means.
    """
    from dotbot.cli._site import (
        active_site,
        connection_banner,
        credentials_for,
        missing_swarm_message,
    )
    from dotbot.config import resolve_source

    obj = ctx.obj or {}
    site = active_site(ctx)
    conn = conn or _swarm_option(ctx, "conn")
    swarm_id = swarm_id or _swarm_option(ctx, "swarm_id")
    conn_r, swarm_r = (
        resolve_source(
            key,
            flag=flag,
            flag_name=f"--{key.replace('_', '-')}",
            config=obj.get("config"),
            site=site.layer,
        )
        for key, flag in (("conn", conn), ("swarm_id", swarm_id))
    )
    click.echo(connection_banner(site, conn_r, swarm_r), err=True)
    if (
        conn_r.value
        and str(conn_r.value).lower().startswith(("mqtt://", "mqtts://"))
        and not swarm_r.value
    ):
        raise click.ClickException(missing_swarm_message(conn_r, site))
    credentials = credentials_for(ctx, conn_r)
    if credentials.withheld:
        click.echo(f"warning: {credentials.withheld}", err=True)

    from dotbot.swarm_client import build_swarmit_client

    return build_swarmit_client(
        conn_r.value,
        swarm_r.value,
        username=credentials.username,
        password=credentials.password,
        no_server=bool(_swarm_option(ctx, "no_server")),
    )


@click.group(
    name="calibrate-lh2",
    help="Over-the-air LH2 calibration: collect, push, reframe.",
)
def cmd() -> None:
    pass


def _await_point(session, stream, arrivals: queue.Queue):
    """Capture the outstanding point from whichever trigger comes first.

    A capture from any robot's button is stored as the point directly. Enter
    runs the READY-mode capture of the stream's device (DEPRECATED, in favour
    of the button); it only arrives when collect has a --device.
    """
    from dotbot.calibration.session import SessionError

    while True:
        try:
            kind, capture = arrivals.get(timeout=0.5)
        except queue.Empty:
            for addr, press in stream.expired_presses():
                click.echo(
                    f"  ! incomplete capture from {addr} (press {press}): a "
                    "chunk never arrived; press again",
                    err=True,
                )
            continue
        if kind == "eof":
            raise click.Abort()
        if kind == "enter":
            try:
                return session.capture(stream)
            except TimeoutError as exc:
                click.echo(f"  ! {exc}", err=True)
                raise click.Abort()
        if capture.lost:
            click.echo(
                f"  ! {capture.device}: {capture.lost} capture(s) lost before "
                f"press {capture.press}",
                err=True,
            )
        try:
            point = session.store_reads(capture.reads, capture.device)
        except SessionError as exc:
            click.echo(f"  ! {exc}", err=True)
            continue
        if point is None:
            continue
        click.echo(f"  received from {capture.device} as point {point.index}")
        return point


@cmd.command(
    name="collect",
    help=(
        "Collect an LH2 calibration over the air (no serial cable). Walks "
        "you through the points of one placement, takes each point's reads "
        "from the robot's button (calibrate app running) or, with --device, "
        "from Enter, solves every visible station, and saves the "
        "calibration. With --spin, the robots spin in place instead "
        "(experimental)."
    ),
)
@click.option(
    "--device",
    default=None,
    help=(
        "DotBot link-layer address in hex (e.g. BC3D3C8A2A6F8E68) that Enter "
        "captures from, with its app stopped (READY). Deprecated in favour of "
        "the calibrate app's button, which needs no address."
    ),
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
        "nearest top or bottom edge. Without --points, --over or --square, "
        "the four corners of the site's field."
    ),
)
@click.option(
    "--over",
    "over",
    default=None,
    metavar="AREA",
    help=(
        "Calibrate over another area's four corners instead of the field's, "
        "e.g. `--over dev-corner` for bench work."
    ),
)
@click.option(
    "--square",
    "square",
    default=None,
    type=int,
    metavar="MM",
    help=(
        "Calibrate over the four corners of a square this many mm wide, "
        "centred in the field. Quicker to tape; the rest of the field is "
        "extrapolated."
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
        "Captures averaged per point on Enter (--device); the calibrate app "
        "sets its own. A single read costs about 60 % of the accuracy at "
        "every point of the field."
    ),
)
@click.option(
    "--timeout",
    default=None,
    type=float,
    help="Seconds to wait for each Enter capture before re-triggering.",
)
@click.option(
    "--retries",
    default=None,
    type=int,
    help="Re-trigger an Enter capture this many times before giving up.",
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
    help=(
        "Send the computed calibration over the air to the robots whose "
        "captures built it (and to --device, when given)."
    ),
)
@click.option(
    "--spin",
    is_flag=True,
    help=(
        "Calibrate from robots spinning in place where they stand, with no "
        "marks on the floor: starts the calibrate-spin app on the robots "
        "(`dotbot swarm -d` picks them), solves the circles they trace, and "
        "saves a calibration whose frame is aligned to their field (the "
        "rectangle around them, grown by a robot's sweep). "
        "Experimental."
    ),
)
@click.option(
    "--spin-radius",
    "spin_radius",
    default=None,
    type=click.FloatRange(min=1.0, max=200.0),
    metavar="MM",
    help=(
        "With --spin: radius of the photodiode's circle in a spin, in mm, "
        "which sets the scale of every distance. Default: the robot model's "
        "measured value (51.4 mm on a DotBot v3, under the 53.5 mm from "
        "photodiode to axle because the caster drags the turning point "
        "forward). Re-measure it on a different floor."
    ),
)
@click.option(
    "--drop-station",
    "drop_stations",
    multiple=True,
    type=click.IntRange(min=0, max=15),
    metavar="N",
    help=(
        "With --spin: leave station N (0 to 15, channel N+1) out of the "
        "solve, repeatable. For a station that is not tied to the others by "
        "shared circles, which otherwise stops the solve."
    ),
)
@click.pass_context
def _collect(
    ctx,
    device,
    conn,
    swarm_id,
    points,
    over,
    square,
    site_name,
    reads,
    timeout,
    retries,
    tag,
    push,
    spin,
    spin_radius,
    drop_stations,
):
    if spin:
        given = [
            flag
            for flag, value in (
                ("--device", device),
                ("--points", points),
                ("--over", over),
                ("--square", square),
                ("--reads", reads),
                ("--timeout", timeout),
                ("--retries", retries),
            )
            if value not in (None, ())
        ]
        if given:
            raise click.UsageError(
                f"--spin takes no {', '.join(given)}: the robots spin where they stand"
            )
        _collect_spin(
            ctx, conn, swarm_id, site_name, tag, push, spin_radius, drop_stations
        )
        return
    if spin_radius is not None:
        raise click.UsageError("--spin-radius goes with --spin")
    if drop_stations:
        raise click.UsageError("--drop-station goes with --spin")
    if _devices(ctx):
        raise click.UsageError(
            "`dotbot swarm -d` picks the robots of push and collect --spin; a "
            "corner collect takes its captures from whichever robot's button"
        )
    try:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        from dotbot.calibration.ota import (
            CAPTURE_READS_DEFAULT,
            CAPTURE_RETRIES_DEFAULT,
            CAPTURE_TIMEOUT_DEFAULT,
            CaptureSession,
        )
        from dotbot.calibration.points import (
            collect_header,
            collect_points,
            point_prompt,
        )
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

    chosen = [flag for flag, v in (("--points", points), ("--over", over)) if v]
    if square is not None:
        chosen.append("--square")
    if len(chosen) > 1:
        raise click.UsageError(
            f"{' and '.join(chosen)} each choose the points; pass one."
        )
    site, site_source = site_from_context(ctx, site_name)
    try:
        specs, how, note = collect_points(site, list(points), over, square)
        session = CalibrationSession.resolve(
            specs,
            site=site,
            points_from=how,
            device=device or "",
            reads=reads if reads is not None else CAPTURE_READS_DEFAULT,
            timeout=timeout if timeout is not None else CAPTURE_TIMEOUT_DEFAULT,
            retries=retries if retries is not None else CAPTURE_RETRIES_DEFAULT,
        )
    except (SessionError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        client = _swarmit_client(ctx, conn, swarm_id)
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Could not reach the swarm: {exc}", err=True)
        sys.exit(1)

    arrivals: queue.Queue = queue.Queue()

    def on_button_capture(capture) -> None:
        arrivals.put(("button", capture))

    def read_enter() -> None:
        for _ in iter(sys.stdin.readline, ""):
            arrivals.put(("enter", None))
        arrivals.put(("eof", None))

    with client:
        with CaptureSession(
            client, device, LH2_CALIB_TAG, on_button_capture=on_button_capture
        ) as stream:
            # Give the transport's own connect/subscribe log lines a beat to
            # print before our prompts, so the two don't interleave on screen.
            time.sleep(0.2)
            click.echo(
                collect_header(
                    site, site_source, len(session.points), session.reads, device or ""
                )
            )
            click.echo(f"Points: {session.at} ({session.points_from}).")
            if note:
                click.echo(note)
            trigger = "the robot's button"
            if device:
                trigger = "Enter"
                threading.Thread(target=read_enter, daemon=True).start()
            while not session.complete:
                outstanding = session.outstanding
                click.echo(
                    "  "
                    + point_prompt(
                        outstanding.index,
                        len(session.points),
                        outstanding.placement,
                        trigger,
                    )
                )
                point = _await_point(session, stream, arrivals)
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
        click.echo(
            f"Calibration id {calibration.id}, site {site.name}"
            + (f", tag {calibration.tag!r}" if calibration.tag else "")
        )

        if push:
            _gated_push(client, calibration, devices=session.push_devices, stop=True)
        else:
            click.echo(
                "To send it to the robots over the air:\n"
                f"  dotbot swarm calibrate-lh2 push "
                f"{calibration.tag or calibration.id8}"
            )


def _collect_spin(
    ctx, conn, swarm_id, site_name, tag, push, spin_radius, drop_stations=()
):
    """`collect --spin`: spin the robots, solve their circles, save, report."""
    from dotbot.calibration.conics import solve_calibration
    from dotbot.calibration.lighthouse2 import write_calibration
    from dotbot.calibration.multi_station import multi_station_report
    from dotbot.calibration.spin import capture_spins, check_spin_robots, spin_report
    from dotbot.robots import ROBOT_DEFAULT, robot_geometry

    site, site_source = site_from_context(ctx, site_name)
    radius_from = "--spin-radius"
    if spin_radius is None:
        spin_radius = robot_geometry(ROBOT_DEFAULT).spin_radius_mm
        radius_from = f"{ROBOT_DEFAULT}'s measured value"
    devices = _devices(ctx)
    try:
        client = _swarmit_client(ctx, conn, swarm_id)
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Could not reach the swarm: {exc}") from exc
    with client:
        click.echo("Reading device info...")
        client.refresh_device_info(devices)
        status = client.status()
        if devices:
            missing = [d for d in devices if d not in status]
            if missing:
                raise click.ClickException(
                    "not heard on the swarm: " + ", ".join(missing)
                )
            status = {addr: node for addr, node in status.items() if addr in devices}
        robots = check_spin_robots(status)
        refusal = robots.refusal()
        if refusal:
            raise click.ClickException(f"spin refused:\n{refusal}")
        if not robots.robots:
            raise click.ClickException("no robot answered, so none can spin")
        click.echo(
            f"Spin calibration in site {site.name} (from {site_source}): "
            f"{len(robots.robots)} robot(s), spin radius {spin_radius:g} mm "
            f"(from {radius_from}). The robots turn in place: keep their "
            "footprint clear."
        )
        try:
            spins = capture_spins(client, robots, echo=click.echo)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        samples = [s for spin in spins.values() for s in spin.samples(spin_radius)]
        try:
            calibration, joint, unsolved = solve_calibration(
                samples,
                site,
                robot=ROBOT_DEFAULT,
                tag=tag or "",
                drop_stations=drop_stations,
            )
        except ValueError as exc:
            for line in spin_report(spins, robots.robots, {}, {}):
                click.echo(line)
            raise click.ClickException(f"no calibration written: {exc}") from exc
        for line in spin_report(spins, robots.robots, joint.solutions, unsolved):
            click.echo(line)
        if len({s.station for s in samples}) > 1:
            click.echo("")
            for line in multi_station_report(calibration, joint):
                click.echo(line)
        path = write_calibration(calibration)
        width, height = joint.field_mm
        click.echo(
            f"\nThe robots' field is {width} x {height} mm: the calibration's frame "
            "is aligned to it, zero at its top-left, not at the site's anchor. "
            f"Robots take fixes inside {list(calibration.valid_mm)}."
        )
        click.echo(f"Calibration saved to {path}")
        click.echo(
            f"Calibration id {calibration.id}, site {site.name}"
            + (f", tag {calibration.tag!r}" if calibration.tag else "")
        )
        spun = ",".join(robots.robots)
        if push:
            _gated_push(client, calibration, devices=robots.robots, stop=True)
        click.echo(
            "\nNext, make the field a site of its own (--size WxH centres it in a "
            "bigger site):\n"
            f"  dotbot site init <name> --from-calibration {calibration.id8}\n"
            + (
                ""
                if push
                else "Or send it as it is:\n"
                f"  dotbot swarm -d {spun} calibrate-lh2 push {calibration.id8}\n"
            )
            + "The robots still hold the calibrate-spin app; before driving them:\n"
            f"  dotbot swarm -d {spun} flash -y remote-control"
        )


@cmd.command(
    name="push",
    help=(
        "Send a saved LH2 calibration to the robots over the air. Takes a "
        "file path, the exact --tag it was collected with, or the id prefix "
        "of a file under ~/.dotbot/calibrations/<site>/. Reads device info "
        "first: refuses robots on firmware older than this host, which need "
        "a reflash, robots that report another site, and robots running an "
        "app, which would drop it, then lists the robots still on another "
        "id. `dotbot swarm -d <addresses> calibrate-lh2 push` sends to those "
        "robots only."
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
        path = resolve_calibration_path(calibration, site=site)
        loaded = read_calibration_file(path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    client = _swarmit_client(ctx, conn, swarm_id)
    with client:
        _gated_push(client, loaded, site_changed=site_changed, devices=_devices(ctx))


def _gated_push(client, calibration, site_changed=False, devices=None, stop=False):
    """Check the robots' device info, push, and print the stale-id worklist.

    With `stop`, the named `devices` still in their app are stopped first.
    """
    from dotbot.calibration.lighthouse2 import calibration_payload
    from dotbot.calibration.push import (
        PushRefused,
        gate_push,
        in_app,
        push_worklist,
        stop_robots,
    )

    try:
        payload = calibration_payload(calibration)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if stop and devices:
        status = client.status()
        running = [d for d in devices if in_app(status.get(d))]
        if running:
            click.echo(f"Stopping {len(running)} robot(s) in their app for the push...")
            busy = stop_robots(client, running)
            if busy:
                raise click.ClickException(
                    "still in their app after a stop: " + ", ".join(busy)
                )
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
    if check.running:
        click.echo(
            f"{len(check.running)} robot(s) in their app are left out, since they "
            "would drop it; stop them and push to them with "
            f"`dotbot swarm -d {','.join(check.running)} calibrate-lh2 push "
            f"{calibration.id8}`."
        )
    client.send_lh2_calibration(payload, check.send_to)
    click.echo("Sent. Waiting for the robots to report the new id...")
    stale = push_worklist(client, calibration, check.targets)
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
    help=(
        "Translation applied after the turn, `x,y` in mm. Without --rotate it "
        "is where the old frame's zero lands in the new one."
    ),
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
    if _devices(ctx):
        raise click.UsageError(
            "reframe sends nothing, so it takes no `dotbot swarm -d`"
        )
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
