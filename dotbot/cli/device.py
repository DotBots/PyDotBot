# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot device` - operate on ONE connected device over the J-Link cable.

Single-device, cabled (nrfjprog / J-Link) operations: `flash` takes a role
(`swarmit-sandbox` or `mari-gateway`: 2-image bundle + shared config page +
network identity), a user app, a file, or `programmer` (the on-board debug
chip); `info` reads provisioning state. The fleet/OTA
equivalents live under `dotbot swarm`; firmware ARTIFACT build/fetch/list
live under `dotbot fw`, which takes the same role and app names.

NOTE: `dotbot device flash mari-gateway` FLASHES gateway firmware onto a
board over the cable. `dotbot run gateway` is something else entirely - the
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
from dotbot.cli._cfg import from_config, on_commandline
from dotbot.firmware.schedules import MARI_SCHEDULES, describe_schedules


@click.group(
    name="device",
    help="One connected device (J-Link cable): flash a role or an app, read info.",
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


# The roles `device flash` takes by name, and the `flash_role` device each is.
_ROLE_DEVICES = {"swarmit-sandbox": "dotbot-v3", "mari-gateway": "gateway"}

# The on-board debug chip, flashed through an external J-Link.
_PROGRAMMER = "programmer"
# Every name `device flash` reads as something other than an app.
FLASH_TARGETS = (*_ROLE_DEVICES, _PROGRAMMER)

# What each kind of NAME accepts, by Click parameter name.
_ACCEPTS = {
    "swarmit-sandbox": {"swarm_id", "calibration_path", "fw_version", "probe"},
    "mari-gateway": {"swarm_id", "schedule", "fw_version", "probe"},
    "app": {"board", "bare", "fw_version", "probe"},
    "file": {"board", "probe"},
    _PROGRAMMER: {"programmer_firmware", "files_dir", "probe_uid"},
}
_REFUSALS = {
    "board": "--board only applies to apps and firmware files; swarmit-sandbox "
    "is a DotBot v3 and mari-gateway an nRF5340-DK.",
    "bare": "--bare/--sandboxed only apply to apps.",
    "swarm_id": "--swarm-id only applies to swarmit-sandbox and mari-gateway.",
    "schedule": "--schedule only applies to mari-gateway; a DotBot adopts the "
    "schedule the gateway's beacon advertises.",
    "calibration_path": "--lh2-calibration only applies to swarmit-sandbox.",
    "fw_version": "-f only applies to roles and apps: it selects the set a name "
    "resolves from.",
    "probe": "programmer is flashed through an external J-Link: select it "
    "with --probe-uid.",
    "programmer_firmware": "--programmer-firmware only applies to programmer.",
    "files_dir": "--files-dir only applies to programmer.",
    "probe_uid": "--probe-uid only applies to programmer; select a J-Link "
    "with --probe.",
}


@cmd.command()
@click.argument("name", metavar="ROLE|APP|FILE")
@click.option(
    "--swarm-id",
    default=None,
    help=(
        "Roles: the 16-bit hex swarm id (e.g. 0100) written with the "
        "firmware. Default: your config's swarm_id."
    ),
)
@click.option(
    "--schedule",
    type=click.Choice(tuple(MARI_SCHEDULES)),
    default=None,
    help=(
        "mari-gateway: the Mari TSCH schedule, "
        f"{describe_schedules()}. It is compiled into the net-core image, so "
        "this selects the image `dotbot fw build mari-gateway --schedule` "
        "builds; no release carries one. Omit it to flash the default net "
        "image, with whichever schedule it was built with."
    ),
)
@click.option(
    "--lh2-calibration",
    "calibration_path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help=(
        "swarmit-sandbox: an LH2 calibration file (schema 2) to bake into the "
        "config page."
    ),
)
@click.option(
    "--board",
    "-b",
    default="dotbot-v3",
    show_default=True,
    help=(
        "Apps and files: the board, which selects the chip family + core to "
        "flash (nRF52 vs nRF5340 app/net) and the app's image name in "
        f"{DEFAULT_ARTIFACTS_DISPLAY}/."
    ),
)
@click.option(
    "--bare/--sandboxed",
    default=None,
    help=(
        "Apps: flash the bare-metal app (.hex) or the sandboxed app (.bin), "
        "which runs under swarmit-sandbox. Default: [fw].bare in config, else "
        "sandboxed on boards that have a sandbox."
    ),
)
@click.option(
    "--fw-version",
    "-f",
    default=None,
    help=(
        "Which set to flash from: a release tag, 'latest', a set built by "
        "`dotbot fw build` ('local' or its --as name), or a directory path "
        "(containing '/') of release-named files. A tag names a swarmit "
        "release for swarmit-sandbox and mari-gateway (Mari's releases carry "
        "no firmware) and a DotBot-firmware release for apps. Default: the "
        "release pydotbot pins. A release missing from "
        f"{DEFAULT_ARTIFACTS_DISPLAY}/ is fetched; nothing is built."
    ),
)
@_probe_option
@click.option(
    "--programmer-firmware",
    "-p",
    type=click.Choice(("jlink", "daplink")),
    help="programmer: the debug-chip firmware to install.",
)
@click.option(
    "--files-dir",
    "-d",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    help="programmer: the folder holding the programmer firmware files.",
)
@click.option(
    "--probe-uid",
    help="programmer: the pyOCD UID of the external J-Link, when several are attached.",
)
@click.pass_context
def flash(
    ctx,
    name,
    swarm_id,
    schedule,
    calibration_path,
    board,
    bare,
    fw_version,
    probe,
    programmer_firmware,
    files_dir,
    probe_uid,
):
    """Flash a role, an app or a file onto one board (whole-chip program).

    \b
      swarmit-sandbox  turn a DotBot v3 into a swarm sandbox host: the
                       swarmit bootloader + network core + network identity
      mari-gateway     turn an nRF5340-DK into the swarm gateway: both
                       Mari gateway cores + network identity
      APP              a DotBot-firmware app, e.g. spin or dotbot
      FILE             a .hex/.bin path, flashed as-is
      programmer       the board's on-board debug chip (J-Link OB or
                       DAPLink), for first-time setup and recovery only;
                       needs an external J-Link, -p and -d

    Nothing is built: for your own build, run `dotbot fw build` with the same
    name, then pass `-f local`. (To run the host-side UART<->MQTT bridge instead, use
    `dotbot run gateway`.)
    """
    from dotbot.firmware.flash import flash_app_image, flash_role, normalize_network_id

    if name in FLASH_TARGETS:
        kind = name
    elif _looks_like_path(name):
        kind = "file"
    else:
        kind = "app"
    for param, message in _REFUSALS.items():
        if param not in _ACCEPTS[kind] and on_commandline(ctx, param):
            raise click.ClickException(message)

    if kind == _PROGRAMMER:
        from dotbot.firmware.flash import flash_programmer

        if programmer_firmware is None or files_dir is None:
            raise click.ClickException(
                "programmer needs the firmware and its files: -p jlink|daplink "
                "-d <folder>."
            )
        flash_programmer(programmer_firmware, files_dir, probe_uid)
        return

    probe = from_config(ctx, "probe", "probe", "device")

    if kind in _ROLE_DEVICES:
        swarm_id = from_config(ctx, "swarm_id", "swarm_id", None)
        if swarm_id is None:
            raise click.ClickException(
                "no swarm id. Pass --swarm-id (a 16-bit hex value, e.g. "
                "--swarm-id 0100), or set swarm_id (or a deployment) in your "
                "config."
            )
        ensure_nrfjprog()
        flash_role(
            _ROLE_DEVICES[kind],
            net_id=normalize_network_id(swarm_id),
            fw_version=fw_version,
            calibration_path=calibration_path,
            bin_dir=artifacts_dir(),
            sn_starting_digits=probe,
            schedule=schedule,
        )
        return

    board = from_config(ctx, "board", "board", "device")
    ensure_nrfjprog()
    if kind == "file":
        image = Path(name)
        if not image.is_file():
            raise click.ClickException(f"Firmware image not found: {image}")
    else:
        bare = from_config(ctx, "bare", "bare", "fw", default=False)
        image = resolve_app_artifact(
            name, board=board, bare=bare, fw_version=fw_version
        )
    flash_app_image(image, board=board, sn_starting_digits=probe)


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
            "  → run `dotbot device flash swarmit-sandbox` (DotBot) or "
            "`dotbot device flash mari-gateway` (gateway) first."
        )
    else:
        click.echo("config:    provisioned")
        click.echo(f"  net-id:  0x{net_id}")
