# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm lh2-calibration` - over-the-air LH2 calibration.

The fleet-side home for LH2 calibration: capture and send a calibration
without a serial cable, driving DotBots through the swarmit transport. Two
subcommands:

- `collect` - walk the robots through a placement's points, trigger a
              raw-count capture per point over the air, solve every visible
              station by least squares, and save a schema 2 calibration
              under ~/.dotbot/calibrations/<site>/.
- `push <path|id>` - send a saved calibration to the robots over the air.

The homography solve lives in PyDotBot (`dotbot.calibration.lighthouse2`);
the transport lives in swarmit.

Serial-cable (single DK) calibration stays under
`dotbot run lh2-calibration`.

Calibration runtime deps (`opencv-python`) live behind the `[calibrate]`
extra; ImportError at invocation prints an install hint instead of a
traceback.
"""

import datetime
import sys
import time

import click

from dotbot.cli._site import site_from_context


def _build_swarmit_client(ctx, conn, swarm_id, device=None):
    """Build a swarmit client targeting one `device`, or the whole swarm when None.

    Reuses swarmit's own conn-string translation so the two CLIs can't
    drift, and falls back to the unified dotbot config's `conn` / `swarm_id`
    (like `dotbot swarm`) when the flags are omitted. Imported lazily: the
    swarmit protocol registry must not load during PyDotBot test collection.

    Transport selection is swarmit's call: `build_client` probes for a running
    swarmit server and falls back to an in-process controller on its own, so
    there is no flag to choose here.
    """
    from swarmit.cli.main import DEFAULTS, _conn_to_config
    from swarmit.client import build_client
    from swarmit.testbed.controller import ControllerSettings

    if conn is None or swarm_id is None:
        from dotbot.config import resolve

        obj = ctx.obj or {}
        config = obj.get("config")
        deployment = obj.get("deployment")
        if conn is None:
            conn = resolve("conn", config=config, deployment=deployment)
        if swarm_id is None:
            swarm_id = resolve("swarm_id", config=config, deployment=deployment)

    final = {**DEFAULTS, **_conn_to_config(conn, swarm_id)}
    settings = ControllerSettings(
        serial_port=final["serial_port"],
        serial_baudrate=final["baudrate"],
        mqtt_host=final["mqtt_host"],
        mqtt_port=final["mqtt_port"],
        mqtt_use_tls=final["mqtt_use_tls"],
        mqtt_username=final.get("mqtt_username"),
        mqtt_password=final.get("mqtt_password"),
        network_id=int(final["swarmit_network_id"], 16),
        adapter=final["adapter"],
        devices=[device.upper()] if device else [],
        verbose=False,
    )
    return build_client(settings)


@click.group(
    name="lh2-calibration",
    help="Over-the-air LH2 calibration: collect, push.",
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

        from dotbot.calibration.lighthouse2 import (
            VALID_MM_DEFAULT,
            LighthouseManager,
            Placement,
            calibration_payload_int32,
            read_calibration_file,
        )
        from dotbot.calibration.ota import (
            CAPTURE_READS_DEFAULT,
            CAPTURE_RETRIES_DEFAULT,
            CAPTURE_TIMEOUT_DEFAULT,
            CaptureSession,
        )
        from dotbot.calibration.points import (
            collect_header,
            point_prompt,
            resolve_placement_points,
        )
    except ImportError as exc:
        click.echo(
            "`dotbot swarm lh2-calibration collect` needs the calibration "
            "runtime deps (opencv-python).\n"
            "Install with:  pip install pydotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    reads = reads if reads is not None else CAPTURE_READS_DEFAULT
    timeout = timeout if timeout is not None else CAPTURE_TIMEOUT_DEFAULT
    retries = retries if retries is not None else CAPTURE_RETRIES_DEFAULT
    specs = list(points) or ["arena:corners"]

    site, site_source = site_from_context(ctx, site_name)
    try:
        placements = resolve_placement_points(specs, site.registry())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if len(placements) < 4:
        raise click.ClickException(
            f"a homography needs at least 4 points, --points resolved to "
            f"{len(placements)}. Span the area you will drive in."
        )

    points_mm = [p.mm for p in placements]
    placement = Placement(index=0, at=" ".join(specs), points_mm=points_mm)

    try:
        client = _build_swarmit_client(ctx, conn, swarm_id, device)
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Could not reach the swarm: {exc}", err=True)
        sys.exit(1)

    with client:
        with CaptureSession(client, device, LH2_CALIB_TAG) as session:
            # Give the transport's own connect/subscribe log lines a beat to
            # print before our prompts, so the two don't interleave on screen.
            time.sleep(0.2)
            click.echo(
                collect_header(site, site_source, len(placements), reads, device)
            )
            for index, point in enumerate(placements):
                click.prompt(
                    "  " + point_prompt(index, len(placements), point),
                    default="",
                    show_default=False,
                    prompt_suffix="",
                )
                try:
                    capture = session.capture_point(
                        point=index,
                        reads=reads,
                        timeout=timeout,
                        retries=retries,
                    )
                except TimeoutError as exc:
                    click.echo(f"  ! {exc}", err=True)
                    raise click.Abort()
                placement.samples.extend(capture.samples)
                for sample in capture.samples:
                    counts = sample.mean_counts()
                    click.echo(
                        f"    station {sample.station}: {sample.reads} reads, "
                        f"mean count1={counts.count1:.1f} count2={counts.count2:.1f}"
                    )
                if capture.dropped:
                    click.echo(f"    {capture.drop_summary()}")

        placement.captured_at = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        manager = LighthouseManager(
            placements=[placement],
            site=site,
            valid_mm=site.valid_mm or VALID_MM_DEFAULT,
        )
        try:
            stations = manager.solve()
        except Exception as exc:
            click.echo(f"Failed to compute calibration: {exc}", err=True)
            sys.exit(1)
        for station in stations:
            click.echo(
                f"station {station.index}: {station.points} points, "
                f"residual {station.residual_mm:.3f} mm"
            )
        for index, seen in manager.unsolved_stations:
            click.echo(
                f"station {index}: seen at {seen} point(s), not solved "
                "(a homography needs 4)"
            )
        path = manager.save_calibration(tag=tag)
        calibration = read_calibration_file(path)
        click.echo(f"\nCalibration saved to {path}")
        click.echo(f"Calibration id {calibration.id}, site {site.name}")

        if push:
            client.send_lh2_calibration(calibration_payload_int32(calibration.stations))
            click.echo("Sent the calibration to the robots over the air.")
        else:
            click.echo(
                "To send it to the robots over the air:\n"
                f"  dotbot swarm lh2-calibration push {calibration.id8}"
            )


@cmd.command(
    name="push",
    help=(
        "Send a saved LH2 calibration to the robots over the air. Takes a "
        "file path or the id prefix of a file under "
        "~/.dotbot/calibrations/<site>/."
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
@click.pass_context
def _push(ctx, calibration, conn, swarm_id, site_name):
    from dotbot.calibration.lighthouse2 import (
        calibration_payload_int32,
        read_calibration_file,
        resolve_calibration_path,
    )

    site, _ = site_from_context(ctx, site_name)
    try:
        path = resolve_calibration_path(calibration, site=site.name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    loaded = read_calibration_file(path)
    payload = calibration_payload_int32(loaded.stations)
    click.echo(
        f"Sending {len(loaded.stations)} calibration matrix/matrices "
        f"({len(payload)} B, id {loaded.id8}, site {site.name}) to the swarm..."
    )
    client = _build_swarmit_client(ctx, conn, swarm_id)
    with client:
        client.send_lh2_calibration(payload)
    click.echo("Sent.")
