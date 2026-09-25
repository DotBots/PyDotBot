# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot device` — operate on ONE connected device over the J-Link cable.

Single-device, cabled (nrfjprog / J-Link) operations: flash a user app,
flash the sandbox-host or gateway role (2-image bundle + shared config
page + network identity), flash the on-board programmer chip, and read
provisioning state. The fleet/OTA equivalents live under `dotbot swarm`;
firmware ARTIFACT build/fetch/list live under `dotbot fw`.

NOTE: `dotbot device flash-mari-gateway` FLASHES gateway firmware onto a board
over the cable. `dotbot run gateway` is something else entirely — the
host-side UART<->MQTT bridge process. Different verbs, different objects.
"""

from pathlib import Path

import click

from dotbot.cli._artifacts import (
    DEFAULT_ARTIFACTS_DISPLAY,
    artifacts_dir,
    ensure_nrfjprog,
    resolve_app_artifact,
)
from dotbot.cli._cfg import from_config
from dotbot.firmware.schedules import MARI_SCHEDULES, describe_schedules


@click.group(
    name="device",
    help="One connected device (J-Link cable): flash an app/role, read info.",
)
def cmd():
    pass


def _looks_like_path(value: str) -> bool:
    """True if `value` is a firmware file rather than an app name."""
    return (
        value.endswith((".hex", ".bin"))
        or "/" in value
        or "\\" in value
        or Path(value).is_file()
    )


def _probe_option(f):
    return click.option(
        "--probe",
        help=(
            "Select the attached board by its J-Link serial-number prefix "
            "(e.g. 77 = a DotBot, 10 = the DK). Omit it when only one probe "
            "is attached."
        ),
    )(f)


def _fw_version_option(source: str):
    def deco(f):
        return click.option(
            "--fw-version",
            "-f",
            default=None,
            help=(
                f"Which {source} set to flash: a release tag, 'latest', a set "
                "built by `dotbot fw build` ('local' or its --as name), or a "
                "directory path (containing '/') of release-named files. "
                "Default: the release pydotbot pins. A release missing from "
                f"{DEFAULT_ARTIFACTS_DISPLAY}/ is fetched; nothing is built."
            ),
        )(f)

    return deco


@cmd.command()
@click.argument("app")
@_probe_option
@click.option(
    "--board",
    "-b",
    default="dotbot-v3",
    show_default=True,
    help=(
        "Target board: selects the chip family + core to flash (nRF52 vs "
        f"nRF5340 app/net) and the <app> image name in {DEFAULT_ARTIFACTS_DISPLAY}/."
    ),
)
@click.option(
    "--bare",
    is_flag=True,
    help=(
        "Flash the bare-metal app (.hex). Default: the sandboxed app (.bin) on "
        "boards that have a sandbox, which runs under a swarmit sandbox host."
    ),
)
@_fw_version_option("dotbot-firmware")
@click.pass_context
def flash(ctx, app, probe, board, bare, fw_version):
    """Flash a firmware image to one cabled device (whole-chip program).

    APP is an app name, looked up in the dotbot-firmware set -f selects, or
    an explicit `.hex`/`.bin` file path. `--board` selects the chip family +
    core to program (see `dotbot fw targets`). Nothing is built: for your own
    build, run `dotbot fw build dotbot-firmware -a APP` then pass `-f local`.
    """
    from dotbot.firmware.flash import flash_app_image

    board = from_config(ctx, "board", "board", "device")
    probe = from_config(ctx, "probe", "probe", "device")
    ensure_nrfjprog()
    if _looks_like_path(app):
        if fw_version is not None:
            raise click.ClickException(
                "-f selects the set an app name resolves from; an explicit "
                "file path needs no -f."
            )
        image = Path(app)
        if not image.is_file():
            raise click.ClickException(f"Firmware image not found: {image}")
    else:
        image = resolve_app_artifact(
            app, board=board, bare=bare, fw_version=fw_version
        )
    flash_app_image(image, board=board, sn_starting_digits=probe)


@cmd.command(name="flash-swarmit-sandbox")
@click.option(
    "--swarm-id",
    default=None,
    help="16-bit hex swarm id (e.g. 0100); defaults to your config's swarm_id.",
)
@click.option(
    "--lh2-calibration",
    "calibration_path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="Optional LH2 calibration file (schema 2) to bake into the config page.",
)
@_fw_version_option("swarmit")
@_probe_option
@click.pass_context
def flash_swarmit_sandbox(ctx, swarm_id, calibration_path, fw_version, probe):
    """Turn a DotBot v3 into a swarm sandbox host (was `provision -d dotbot-v3`).

    Flashes the SwarmIT bootloader (app core) + netcore + writes the
    network identity, from the swarmit set -f selects.
    """
    from dotbot.firmware.flash import flash_role, normalize_network_id

    swarm_id = from_config(ctx, "swarm_id", "swarm_id", None)
    if swarm_id is None:
        raise click.ClickException(
            "no swarm id. Pass --swarm-id (a 16-bit hex value, e.g. "
            "--swarm-id 0100), or set swarm_id (or a deployment) in your "
            "config."
        )
    ensure_nrfjprog()
    net_id = normalize_network_id(swarm_id)
    flash_role(
        "dotbot-v3",
        net_id=net_id,
        fw_version=fw_version,
        calibration_path=calibration_path,
        bin_dir=artifacts_dir(),
        sn_starting_digits=probe,
    )


@cmd.command(name="flash-mari-gateway")
@click.option(
    "--swarm-id",
    default=None,
    help="16-bit hex swarm id (e.g. 0100); defaults to your config's swarm_id.",
)
@click.option(
    "--schedule",
    type=click.Choice(tuple(MARI_SCHEDULES)),
    default=None,
    help=(
        "Mari TSCH schedule to put on the gateway: "
        f"{describe_schedules()}. The schedule is compiled into the net-core "
        "image, so this selects the per-schedule image that Mari's "
        "build-schedules.sh produces (`dotbot fw build` does not build those "
        "yet). Omit it to flash whichever schedule the artifact was built with."
    ),
)
@_fw_version_option("swarmit")
@_probe_option
@click.pass_context
def flash_mari_gateway(ctx, swarm_id, schedule, fw_version, probe):
    """Turn an nRF5340-DK into the swarm gateway (was `provision -d gateway`).

    Flashes the Mari gateway firmware (both cores) + writes the network
    identity, from the swarmit set -f selects. (To run the host-side
    UART<->MQTT bridge instead, use `dotbot run gateway`.)
    """
    from dotbot.firmware.flash import flash_role, normalize_network_id

    swarm_id = from_config(ctx, "swarm_id", "swarm_id", None)
    if swarm_id is None:
        raise click.ClickException(
            "no swarm id. Pass --swarm-id (a 16-bit hex value, e.g. "
            "--swarm-id 0100), or set swarm_id (or a deployment) in your "
            "config."
        )
    ensure_nrfjprog()
    net_id = normalize_network_id(swarm_id)
    flash_role(
        "gateway",
        net_id=net_id,
        fw_version=fw_version,
        bin_dir=artifacts_dir(),
        sn_starting_digits=probe,
        schedule=schedule,
    )


@cmd.command(name="flash-programmer")
@click.option(
    "--programmer-firmware",
    "-p",
    type=click.Choice(("jlink", "daplink")),
    required=True,
)
@click.option(
    "--files-dir",
    "-d",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    required=True,
)
@click.option("--probe-uid", help="pyOCD probe UID (when multiple probes attached).")
def flash_programmer(programmer_firmware, files_dir, probe_uid):
    """Flash J-Link OB / DAPLink firmware to the on-board debug chip.

    Obscure, one-time-per-board bring-up (was `provision flash-bringup`).
    """
    from dotbot.firmware.flash import flash_programmer as _flash_programmer

    _flash_programmer(programmer_firmware, files_dir, probe_uid)


@cmd.command()
@_probe_option
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip the confirmation prompt (the network id read resets the device).",
)
def info(probe, yes):
    """Read a device's provisioning state (chip id + network identity).

    Reading the network id resets the device: the swarm config lives in the
    network core's flash, and attaching the debugger there restarts that core.
    On a DotBot mid-experiment that drops the radio until the device is reset,
    so the command asks first. Pass -y to skip the prompt.

    Never fails on a blank/unprovisioned board — reports 'not
    provisioned' and how to fix it.
    """
    from dotbot.firmware.flash import read_config_report
    from dotbot.firmware.nrf import NET_CORE_READ_WARNING

    ensure_nrfjprog()
    if not yes:
        click.secho(f"[WARN] {NET_CORE_READ_WARNING}", fg="yellow")
        if not click.confirm("Read it anyway?", default=True):
            raise click.ClickException("Aborted.")
    try:
        net_id, device_id = read_config_report(probe)
    except RuntimeError as exc:
        raise click.ClickException(f"Could not read the device: {exc}") from exc

    last6 = device_id[-6:]
    last6_spaced = " ".join(last6[i : i + 2] for i in range(0, len(last6), 2))
    click.echo(f"device-id: {device_id} (last 6: {last6_spaced})")
    if net_id == "unprovisioned":
        click.echo("config:    not provisioned (no swarm config on this device)")
        click.echo(
            "  → run `dotbot device flash-swarmit-sandbox` (DotBot) or "
            "`flash-mari-gateway` (gateway) first."
        )
    else:
        click.echo("config:    provisioned")
        click.echo(f"  net-id:  0x{net_id}")
