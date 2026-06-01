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
    artifacts_dir,
    ensure_nrfjprog,
    resolve_app_artifact,
)
from dotbot.cli._cfg import from_config


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


@cmd.command()
@click.argument("app")
@click.option("--sn-starting-digits", "-s", help="J-Link serial prefix, e.g. 77.")
@click.option(
    "--board",
    "-b",
    default="dotbot-v3",
    show_default=True,
    help=(
        "Target board: selects the chip family + core to flash (nRF52 vs "
        "nRF5340 app/net) and resolves <app>-<board> in ./artifacts/."
    ),
)
@click.option("--sandbox", is_flag=True, help="Resolve the sandbox-app flavor (.bin).")
@click.option(
    "--build-config",
    "config",
    type=click.Choice(("Debug", "Release")),
    default="Release",
    show_default=True,
    help="Build configuration (for auto-resolving the artifact).",
)
@click.pass_context
def flash(ctx, app, sn_starting_digits, board, sandbox, config):
    """Flash a firmware image to one cabled device (whole-chip program).

    APP is an app name (resolved against ./artifacts/, building from source
    if needed) or an explicit `.hex`/`.bin` file path. `--board` selects the
    chip family + core to program (see `dotbot fw targets`); no sandbox host
    is required.
    """
    from dotbot.firmware.flash import flash_app_image

    board = from_config(ctx, "board", "board", "device")
    sn_starting_digits = from_config(
        ctx, "sn_starting_digits", "sn_starting_digits", "device"
    )
    config = from_config(ctx, "config", "build_config", "device")
    ensure_nrfjprog()
    if _looks_like_path(app):
        image = Path(app)
        if not image.is_file():
            raise click.ClickException(f"Firmware image not found: {image}")
    else:
        image = resolve_app_artifact(app, board=board, config=config, sandbox=sandbox)
    flash_app_image(image, board=board, sn_starting_digits=sn_starting_digits)


def _fw_version_option(f):
    return click.option(
        "--fw-version",
        "-f",
        required=True,
        help=(
            "Release version to flash, e.g. 0.8.0rc1. Its binaries are "
            "fetched into ./artifacts/ if not already cached."
        ),
    )(f)


def _sn_option(f):
    return click.option(
        "--sn-starting-digits", "-s", help="J-Link serial prefix, e.g. 77."
    )(f)


@cmd.command(name="flash-swarmit-sandbox")
@click.option(
    "--network-id", "-n", required=True, help="16-bit hex network id, e.g. 0100."
)
@click.option(
    "--calibration",
    "-l",
    "calibration_path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="Optional LH2 calibration file to bake into the config page.",
)
@_fw_version_option
@_sn_option
def flash_swarmit_sandbox(network_id, calibration_path, fw_version, sn_starting_digits):
    """Turn a DotBot v3 into a swarm sandbox host (was `provision -d dotbot-v3`).

    Flashes the SwarmIT bootloader (app core) + netcore + writes the
    network identity. Auto-fetches the release if not already in
    ./artifacts/<version>/.
    """
    from dotbot.firmware.flash import flash_role, normalize_network_id

    ensure_nrfjprog()
    net_id = normalize_network_id(network_id)
    flash_role(
        "dotbot-v3",
        net_id=net_id,
        fw_version=fw_version,
        calibration_path=calibration_path,
        bin_dir=artifacts_dir(),
        sn_starting_digits=sn_starting_digits,
    )


@cmd.command(name="flash-mari-gateway")
@click.option(
    "--network-id", "-n", required=True, help="16-bit hex network id, e.g. 0100."
)
@_fw_version_option
@_sn_option
def flash_mari_gateway(network_id, fw_version, sn_starting_digits):
    """Turn an nRF5340-DK into the swarm gateway (was `provision -d gateway`).

    Flashes the Mari gateway firmware (both cores) + writes the network
    identity. Auto-fetches the release if absent. (To run the host-side
    UART<->MQTT bridge instead, use `dotbot run gateway`.)
    """
    from dotbot.firmware.flash import flash_role, normalize_network_id

    ensure_nrfjprog()
    net_id = normalize_network_id(network_id)
    flash_role(
        "gateway",
        net_id=net_id,
        fw_version=fw_version,
        bin_dir=artifacts_dir(),
        sn_starting_digits=sn_starting_digits,
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
@_sn_option
def info(sn_starting_digits):
    """Read a device's provisioning state (chip id + network identity).

    Never fails on a blank/unprovisioned board — reports 'not
    provisioned' and how to fix it.
    """
    from dotbot.firmware.flash import read_config_report

    ensure_nrfjprog()
    try:
        net_id, device_id = read_config_report(sn_starting_digits)
    except RuntimeError as exc:
        raise click.ClickException(f"Could not read the device: {exc}") from exc

    last6 = device_id[-6:]
    last6_spaced = " ".join(last6[i : i + 2] for i in range(0, len(last6), 2))
    click.echo(f"device-id: {device_id} (last 6: {last6_spaced})")
    if net_id == "unprovisioned":
        click.echo("config:    not provisioned (no swarm config on this device)")
        click.echo(
            "  → run `dotbot device flash-swarmit-sandbox` (robot) or "
            "`flash-mari-gateway` (gateway) first."
        )
    else:
        click.echo("config:    provisioned")
        click.echo(f"  net-id:  0x{net_id}")
