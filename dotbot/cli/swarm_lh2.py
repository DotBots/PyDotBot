# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm lh2-calibration` - over-the-air LH2 calibration.

The fleet-side home for LH2 calibration: capture and send a calibration
without a serial cable, driving a single DotBot through the swarmit
transport. Two subcommands:

- `collect` - walk one DotBot through the 4 arena corners, trigger a
              raw-count capture per corner over the air, solve the
              homography, and save the calibration under
              ~/.dotbot/calibrations/.
- `push <path>` - send a saved calibration to the DotBot over the air. A thin
              forward to swarmit's `calibrate-lh2`, which picks the payload
              format (legacy `.out` or `calibration-*.toml`) by extension.

The homography solve lives in PyDotBot (`dotbot.calibration.lighthouse2`); the
transport lives in swarmit. `collect` therefore runs natively here, while
`push` is pure transport and reuses swarmit's own command.

Serial-cable (single DK) calibration and the C-header `apply` export stay
under `dotbot run lh2-calibration`.

Calibration runtime deps (`opencv-python`) live behind the `[calibrate]`
extra; ImportError at invocation prints an install hint instead of a
traceback.
"""

import sys
import time

import click


def _build_swarmit_client(ctx, conn, swarm_id, device):
    """Build a swarmit client targeting a single `device`.

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
        devices=[device.upper()],
        verbose=False,
    )
    return build_client(settings)


@click.group(
    name="lh2-calibration",
    help="Over-the-air LH2 calibration for one DotBot: collect, push.",
)
def cmd() -> None:
    pass


@cmd.command(
    name="collect",
    help=(
        "Collect LH2 calibration from one DotBot over the air (no serial "
        "cable). Walks you through the 4 arena corners, triggers a capture "
        "per corner via swarmit, solves the homography, and saves the "
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
    "-d",
    "--distance",
    default=None,
    type=int,
    help=(
        "Distance between reference corners in millimeters "
        "(default: the calibration package default)."
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
    help="Re-trigger this many times per corner before giving up.",
)
@click.option(
    "--tag",
    default=None,
    help=(
        'Optional arena/setup label (e.g. "office-2x2m") added to the saved '
        "filename and metadata, so calibrations stay self-describing."
    ),
)
@click.option(
    "--push",
    is_flag=True,
    help="Send the computed calibration back to the DotBot over the air.",
)
@click.pass_context
def _collect(ctx, device, conn, swarm_id, distance, timeout, retries, tag, push):
    try:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        from dotbot.calibration.lighthouse2 import (
            CALIBRATION_DISTANCE_DEFAULT,
            LighthouseManager,
        )
        from dotbot.calibration.ota import (
            CAPTURE_RETRIES_DEFAULT,
            CAPTURE_TIMEOUT_DEFAULT,
            CORNERS,
            CaptureSession,
        )
    except ImportError as exc:
        click.echo(
            "`dotbot swarm lh2-calibration collect` needs the calibration "
            "runtime deps (opencv-python).\n"
            "Install with:  pip install dotbot[calibrate]",
            err=True,
        )
        click.echo(f"(import error was: {exc})", err=True)
        sys.exit(1)

    distance = distance if distance is not None else CALIBRATION_DISTANCE_DEFAULT
    timeout = timeout if timeout is not None else CAPTURE_TIMEOUT_DEFAULT
    retries = retries if retries is not None else CAPTURE_RETRIES_DEFAULT

    try:
        client = _build_swarmit_client(ctx, conn, swarm_id, device)
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Could not reach the swarm: {exc}", err=True)
        sys.exit(1)

    samples = []
    with client:
        with CaptureSession(client, device, LH2_CALIB_TAG) as session:
            # Give the transport's own connect/subscribe log lines a beat to
            # print before our prompts, so the two don't interleave on screen.
            time.sleep(0.2)
            click.echo(
                f"\nCollecting LH2 calibration from {device.upper()}.\n"
                "Stop the DotBot's app first (capture only runs in READY).\n"
            )
            for corner in CORNERS:
                click.prompt(
                    f"Place the DotBot at the {corner} corner, then press Enter",
                    default="",
                    show_default=False,
                    prompt_suffix="",
                )
                try:
                    sample = session.capture(
                        lh_index=0,
                        timeout=timeout,
                        retries=retries,
                        on_attempt=lambda n, total: click.echo(
                            f"  triggering capture (attempt {n}/{total}), "
                            f"waiting up to {timeout:g}s..."
                        ),
                    )
                except TimeoutError as exc:
                    click.echo(f"  ! {exc}", err=True)
                    raise click.Abort()
                samples.append(sample)
                click.echo(
                    f"  captured {corner}: "
                    f"count1={sample.count1} count2={sample.count2}"
                )

        manager = LighthouseManager(calibration_distance=distance, extra_lh_num=0)
        try:
            manager.compute_calibration(samples)
        except Exception as exc:
            click.echo(f"Failed to compute calibration: {exc}", err=True)
            sys.exit(1)
        path = manager.save_calibration(tag=tag)
        click.echo(f"\nCalibration saved to {path}")

        if push:
            payload = manager.calibration_output_path.read_bytes()
            client.send_lh2_calibration(payload)
            click.echo("Sent the calibration to the DotBot over the air.")
        else:
            click.echo(
                "To send it to the DotBot over the air:\n"
                f"  dotbot swarm lh2-calibration push {path}"
            )


@cmd.command(
    name="push",
    help=(
        "Send a saved LH2 calibration to the DotBot over the air. Forwards to "
        "swarmit's `calibrate-lh2`, which picks the payload format (legacy "
        "`.out` or `calibration-*.toml`) by file extension."
    ),
)
@click.argument(
    "path",
    type=click.Path(exists=True, dir_okay=False),
)
@click.pass_context
def _push(ctx, path):
    from dotbot.cli._swarm_inject import inject_config
    from dotbot.cli.swarm import _load_swarmit_group, _run_swarmit

    swarmit_group = _load_swarmit_group()
    final = inject_config(["calibrate-lh2", path], ctx.obj)
    _run_swarmit(swarmit_group, final)
