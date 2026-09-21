"""DotBot firmware flashing + provisioning engine (no CLI).

The hardware-facing engine behind `dotbot device`: flash a role's system
firmware + config page (`flash_role`), flash a single app image
(`flash_app_image`), flash the debug-chip programmer (`flash_programmer`),
and read back provisioning state (`read_config_report`). Release fetching
+ the artifact cache live next door in `fetch.py`; the Click surface lives
in `dotbot/cli/device.py`. This module is pure library code.
"""

from __future__ import annotations

import json
import os
import struct
import time
from pathlib import Path

import click

from .fetch import fetch_assets, resolve_fw_root
from .nrf import (
    do_daplink,
    do_daplink_if,
    do_jlink,
    flash_nrf_both_cores,
    flash_nrf_one_core,
    pick_last_jlink_snr,
    pick_matching_jlink_snr,
    read_device_id,
    read_net_id,
    reset_device,
)
from .schedules import MARI_SCHEDULES, describe_schedules, net_image_name

try:
    from intelhex import IntelHex
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    IntelHex = None
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older Pythons
    tomllib = None


DEFAULT_BIN_DIR = Path("bin")
VALID_DEVICES = ("dotbot-v3", "gateway")
VALID_PROGRAMMERS = ("jlink", "daplink")
CONFIG_ADDR = 0x0103F800
# The config page's magic is per role. The gateway's page is mari's
# `mari_app_config_t` (MARI_APP_CONFIG_MAGIC_VALUE); the sandbox host's is
# swarmit's `swarmit_config_t` (SWARMIT_CONFIG_MAGIC_VALUE), which moved when
# its matrices went float32, so a netcore never reads a page of the other
# layout as valid. Each value must match its firmware's.
CONFIG_MAGIC_BY_ROLE = {
    "dotbot-v3": 0x5753524E,
    "gateway": 0x5753524D,
}
CONFIG_MANIFEST_NAME = "config-manifest.json"
# swarmit_config_t, little-endian and packed: magic, has_net_id, net_id,
# homography_count, sixteen 3x3 float32 matrices, valid_mm[4], site_name[16],
# calibration_id[8]. Every byte the calibration does not set is 0xFF, the
# erase state the firmware reads as "absent".
LH2_MATRIX_BYTES = 3 * 3 * 4
LH2_MAX_HOMOGRAPHIES = 16
SWARMIT_CONFIG_BYTES = 632
SWARMIT_CONFIG_COUNT_OFFSET = 12
SWARMIT_CONFIG_MATRICES_OFFSET = 16
SWARMIT_CONFIG_SITE_OFFSET = 592
# Application images are linked after the bootloader.
APP_FLASH_BASE_ADDR = 0x00010000
# Programmer bring-up files
GEEHY_PACK_NAME = "Geehy.APM32F1xx_DFP.1.1.0.pack"
JLINK_REQUIRED_FILES = ("JLink-ob.bin", "stm32f103xb_bl.hex", GEEHY_PACK_NAME)
DAPLINK_REQUIRED_FILES = (
    "stm32f103xb_bl.hex",
    "stm32f103xb_if.hex",
    GEEHY_PACK_NAME,
)
APM_DEVICE = "APM32F103CB"
# it seems to always start with 77
DOTBOT_V3_SERIAL_PATTERN = r"77[0-9A-F]{7}"

DEVICE_ASSETS: dict[str, dict[str, str]] = {
    "dotbot-v3": {
        "app": "bootloader-dotbot-v3.hex",
        "net": "netcore-nrf5340-net.hex",
        "examples": ["rgbled-dotbot-v3.bin", "dotbot-dotbot-v3.bin"],
    },
    "gateway": {
        "app": "03app_gateway_app-nrf5340-app.hex",
        "net": "03app_gateway_net-nrf5340-net.hex",
        "examples": [],
    },
}


def load_config(path: Path) -> dict:
    if tomllib is None:
        raise click.ClickException(
            "tomllib not available; install Python 3.11+ or add tomli."
        )
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError as exc:
        raise click.ClickException(f"Config file not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001 - surface parse errors
        raise click.ClickException(
            f"Failed to parse config file {path}: {exc}"
        ) from exc


def normalize_network_id(raw: str | None) -> tuple[int, str] | None:
    if raw is None:
        return None
    s = raw.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        value = int(s, 16)
    except ValueError as exc:
        raise click.ClickException(
            f"Invalid network_id '{raw}' (expected hex)."
        ) from exc
    if not (0x0000 <= value <= 0xFFFF):
        raise click.ClickException("network_id must be 16-bit (0x0000..0xFFFF).")
    return value, f"{value:04X}"


def convert_bin_to_hex(bin_path: Path, base_addr: int) -> Path:
    if IntelHex is None:
        raise click.ClickException(
            "intelhex not available; install it to convert .bin to .hex."
        )
    if not bin_path.exists():
        raise click.ClickException(f"BIN file not found: {bin_path}")
    hex_path = bin_path.with_suffix(".hex")
    ih = IntelHex()
    ih.frombytes(bin_path.read_bytes(), offset=base_addr)
    ih.tofile(str(hex_path), "hex")
    click.echo(
        f"[OK  ] converted {bin_path.name} -> {hex_path.name} @ 0x{base_addr:08X}"
    )
    return hex_path


def find_existing_config_hex(fw_root: Path) -> Path | None:
    candidates = sorted(
        fw_root.glob("config-*.hex"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def make_config_hex_path(
    fw_root: Path, device: str, fw_version: str, net_id_hex: str
) -> Path:
    ts = time.strftime("%Y%b%d-%H%M%S")
    return fw_root / f"config-{device}-{fw_version}-{net_id_hex}-{ts}.hex"


def load_calibration_file(path: Path):
    """Read a schema 2 calibration file, refused when a robot could not take it."""
    from dotbot.calibration.lighthouse2 import (
        pushable_stations,
        read_calibration_file,
        site_fields_as_bytes,
    )

    try:
        calibration = read_calibration_file(Path(path))
        pushable_stations(calibration)
        site_fields_as_bytes(calibration)
    except (OSError, ValueError) as exc:
        raise click.ClickException(
            f"Cannot use calibration file {path}: {exc}"
        ) from exc
    return calibration


def swarmit_config_page(net_id_value: int, calibration=None) -> bytes:
    """The sandbox host's whole config page, `swarmit_config_t`."""
    from dotbot.calibration.lighthouse2 import (
        homography_as_float32,
        pushable_stations,
        site_fields_as_bytes,
    )

    page = bytearray(b"\xff" * SWARMIT_CONFIG_BYTES)
    page[0:12] = struct.pack("<III", CONFIG_MAGIC_BY_ROLE["dotbot-v3"], 1, net_id_value)
    if calibration is not None:
        stations = pushable_stations(calibration)
        page[12:16] = struct.pack("<I", len(stations))
        for station in stations:
            offset = SWARMIT_CONFIG_MATRICES_OFFSET + station.index * LH2_MATRIX_BYTES
            page[offset : offset + LH2_MATRIX_BYTES] = homography_as_float32(
                station.homography
            )
        site = site_fields_as_bytes(calibration)
        page[SWARMIT_CONFIG_SITE_OFFSET : SWARMIT_CONFIG_SITE_OFFSET + len(site)] = site
    return bytes(page)


def gateway_config_page(net_id_value: int) -> bytes:
    """The gateway's config page, mari's `mari_app_config_t`."""
    return struct.pack("<III", CONFIG_MAGIC_BY_ROLE["gateway"], 1, net_id_value)


def config_page(role: str, net_id_value: int, calibration=None) -> bytes:
    """The config page `role` boots from."""
    if role == "gateway":
        return gateway_config_page(net_id_value)
    return swarmit_config_page(net_id_value, calibration)


def create_config_hex(dest: Path, page: bytes) -> None:
    """Write `page` at the network core's config address as an Intel hex."""
    if IntelHex is None:
        raise click.ClickException(
            "intelhex not available; install it to build config hex."
        )
    ih = IntelHex()
    for i, b in enumerate(page):
        ih[CONFIG_ADDR + i] = b
    dest.parent.mkdir(parents=True, exist_ok=True)
    ih.tofile(str(dest), "hex")


def load_config_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - surface parse errors
        raise click.ClickException(
            f"Failed to parse config manifest {path}: {exc}"
        ) from exc


def write_config_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_manifest_payload(
    config_hex: Path,
    device: str,
    fw_version: str,
    net_id_hex: str,
    calibration_hex: str | None = None,
) -> dict:
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "config_hex": config_hex.name,
        "device": device,
        "fw_version": fw_version,
        "network_id": net_id_hex,
        "config_addr": f"0x{CONFIG_ADDR:08X}",
        "magic": f"0x{CONFIG_MAGIC_BY_ROLE[device]:08X}",
        # The calibration's part of the page, inline as hex (620 bytes at
        # most), so a changed calibration never reuses a cached page.
        "calibration": calibration_hex,
        "created_at": created_at,
    }


def manifest_matches(
    payload: dict,
    device: str,
    fw_version: str,
    net_id_hex: str,
    calibration_hex: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("device") == device
        and payload.get("fw_version") == fw_version
        and payload.get("network_id") == net_id_hex
        and payload.get("config_addr") == f"0x{CONFIG_ADDR:08X}"
        and payload.get("magic") == f"0x{CONFIG_MAGIC_BY_ROLE[device]:08X}"
        and payload.get("calibration") == calibration_hex
        and isinstance(payload.get("config_hex"), str)
    )


def describe_image(path: Path) -> str:
    """``path``, plus the symlink target and its build time when it is a link.

    ``-f local`` resolves to a directory of symlinks into a build tree, so the
    path alone does not say which tree (or how stale a build) is about to be
    flashed. Resolving it here means every flash reports its own provenance.
    """
    if not path.is_symlink():
        return str(path)
    target = Path(os.readlink(path))
    try:
        built = time.strftime("%Y-%m-%d %H:%M", time.localtime(target.stat().st_mtime))
    except OSError:
        return f"{path} -> {target} (BROKEN LINK)"
    return f"{path}\n              -> {target} (built {built})"


def flash_role(
    role: str,
    *,
    net_id: tuple[int, str],
    fw_version: str,
    calibration_path: Path | None = None,
    bin_dir: Path = DEFAULT_BIN_DIR,
    sn_starting_digits: str | None = None,
    default_app_name: str | None = None,
    local_root: Path | None = None,
    schedule: str | None = None,
) -> None:
    """Flash a device's role: system firmware bundle (app+net cores) + config.

    Backend for `dotbot device flash-swarmit-sandbox` (role='dotbot-v3') and
    `dotbot device flash-mari-gateway` (role='gateway'). Selects the J-Link,
    flashes both cores, writes the config page (magic + has_net_id +
    net_id [+ calibration, dotbot-v3 only]), then best-effort reads back
    net_id/device_id (never raises on readback failure). If the role's
    images are absent from ``bin_dir/<fw_version>/``, fetches the release
    first (the "run fetch under the hood" behaviour).

    ``local_root`` (only with ``fw_version="local"``) re-points the local
    symlinks at that build tree before flashing, so a one-liner can target a
    worktree instead of whichever tree a previous `dotbot fw fetch` linked.

    ``schedule`` (gateway only) selects the per-schedule net-core image rather
    than the role's default one. The schedule is compiled into the image, so
    naming it here names the image it was built into.
    """
    assets = DEVICE_ASSETS[role]
    net_id_val, net_id_hex = net_id

    # Checked before the J-Link probe so a bad flag combination fails
    # instantly rather than after hardware selection.
    if local_root is not None and fw_version != "local":
        raise click.ClickException("--local-root requires --fw-version local.")
    if schedule is not None:
        if role != "gateway":
            raise click.ClickException(
                "--schedule is only valid for the Mari gateway; a node adopts "
                "whatever schedule the gateway's beacon advertises."
            )
        if schedule not in MARI_SCHEDULES:
            raise click.ClickException(
                f"Unknown schedule '{schedule}'. Valid schedules: "
                f"{describe_schedules()}."
            )
    net_asset = net_image_name(schedule) if schedule else assets["net"]

    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; pass --probe with the board's "
            "J-Link serial-number prefix (e.g. --probe 77)."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}")

    if role == "dotbot-v3" and not snr.startswith("77"):
        click.secho(
            f"[WARN] Serial number {snr} seems to not be a DotBot, but you are trying to flash a {role} firmware to it.",
            fg="yellow",
        )
        if not click.confirm(
            "Do you want to continue? (you can check or plug the right board)",
            default=True,
        ):
            raise click.ClickException("Aborting.")
    elif role == "gateway" and snr.startswith("77"):
        click.secho(
            f"[WARN] Serial number {snr} seems to be a DotBot, but you are trying to flash a {role} firmware to it.",
            fg="yellow",
        )
        if not click.confirm(
            "Do you want to continue? (you can check or plug the right board)",
            default=True,
        ):
            raise click.ClickException("Aborting.")

    calibration = None
    calibration_hex: str | None = None
    if calibration_path is not None:
        if role != "dotbot-v3":
            raise click.ClickException(
                "--lh2-calibration is only valid for the sandbox host (dotbot-v3); "
                "gateway firmware does not have LH2 homographies."
            )
        calibration = load_calibration_file(calibration_path)
        page = swarmit_config_page(net_id_val, calibration)
        calibration_hex = page[SWARMIT_CONFIG_COUNT_OFFSET:].hex()
        click.echo(
            f"[INFO] calibration: {len(calibration.stations)} matrices, "
            f"site {calibration.site.name}, id {calibration.id} "
            f"from {calibration_path}"
        )

    fw_root = resolve_fw_root(bin_dir, "swarmit", fw_version)
    # Auto-fetch: if the role's images aren't already present, pull the
    # swarmit release into bin_dir/swarmit-<version>/ before flashing.
    pre_app = fw_root / assets["app"]
    pre_net = fw_root / net_asset
    if fw_version == "local" and local_root is not None:
        fetch_assets("swarmit", "local", bin_dir, local_root)
    elif fw_version != "local" and not (pre_app.exists() and pre_net.exists()):
        click.echo(f"[INFO] firmware {fw_version} not found in {fw_root}; fetching...")
        fetch_assets("swarmit", fw_version, bin_dir)
    if not fw_root.exists():
        raise click.ClickException(f"Firmware root not found: {fw_root}")
    if schedule is not None and not (fw_root / net_asset).exists():
        raise click.ClickException(
            f"No gateway net-core image for the {schedule} schedule: "
            f"{fw_root / net_asset} is not there.\n"
            "A swarmit release publishes a single gateway net-core image, "
            "built with one schedule, so --schedule needs a tree where the "
            "per-schedule images have been built:\n"
            f"  \u2022 build it: <local-root>/mari/firmware/build-schedules.sh {schedule}\n"
            "  \u2022 then flash with -f local --local-root <that tree>"
        )

    device = role

    default_app_hex: Path | None = None
    if device == "dotbot-v3":
        if default_app_name:
            name = default_app_name.strip()
            if not name:
                raise click.ClickException("--app cannot be empty.")
            candidate = fw_root / f"{name}-{device}.bin"
            if candidate.exists():
                default_app_hex = convert_bin_to_hex(candidate, APP_FLASH_BASE_ADDR)
            else:
                raise click.ClickException(f"App firmware not found: {candidate}")
        else:
            # default to dotbot app if no name is provided
            candidate = fw_root / "dotbot-dotbot-v3.bin"
            if candidate.exists():
                default_app_hex = convert_bin_to_hex(candidate, APP_FLASH_BASE_ADDR)
    else:
        if default_app_name:
            click.echo(
                "[WARN] --app is only supported for dotbot-v3; skipping.",
                err=True,
            )

    app_hex = fw_root / assets["app"]
    net_hex = fw_root / net_asset
    manifest_path = fw_root / CONFIG_MANIFEST_NAME
    manifest = load_config_manifest(manifest_path)
    config_hex = None
    if manifest:
        click.echo(
            f"[INFO] loaded manifest {manifest_path}: {json.dumps(manifest, indent=2)}"
        )
        if manifest_matches(manifest, device, fw_version, net_id_hex, calibration_hex):
            candidate = fw_root / manifest["config_hex"]
            if candidate.exists():
                config_hex = candidate
                click.secho(
                    f"[NOTE] using config hex from manifest: {config_hex}",
                    fg="yellow",
                )
        else:
            click.secho(
                "[INFO] manifest does not match, will create new config hex",
                fg="yellow",
            )

    if config_hex is None:
        config_hex = make_config_hex_path(fw_root, device, fw_version, net_id_hex)
        click.secho(f"[INFO] created new config hex: {config_hex}", fg="green")

    missing = []
    for p in (app_hex, net_hex):
        if p.exists():
            continue
        if p.is_symlink():
            # Path.exists() follows symlinks; a dangling symlink reports
            # missing without surfacing the broken target. Re-running
            # `dotbot fw fetch -f <ver> --local-root <path>` typically
            # refreshes these.
            missing.append(f"{p} (broken symlink → {os.readlink(p)})")
        else:
            missing.append(str(p))
    if missing:
        missing_list = ", ".join(missing)
        raise click.ClickException(f"Missing firmware files: {missing_list}")

    click.echo(f"[INFO] device: {device}")
    click.echo(f"[INFO] fw_version: {fw_version}")
    click.echo(f"[INFO] network_id: 0x{net_id_hex}")
    click.echo(f"[INFO] app hex: {describe_image(app_hex)}")
    click.echo(f"[INFO] net hex: {describe_image(net_hex)}")
    if role == "gateway":
        if schedule is None:
            click.echo(
                "[INFO] schedule: whichever one this image was built with "
                "(every schedule is linked in, so the image does not say)"
            )
        else:
            click.echo(
                f"[INFO] schedule: {schedule} "
                f"(up to {MARI_SCHEDULES[schedule]} nodes)"
            )
    click.echo(f"[INFO] config hex: {config_hex}")

    if not config_hex.exists():
        create_config_hex(config_hex, config_page(role, net_id_val, calibration))
        click.echo(f"[OK  ] wrote config hex: {config_hex}")
        manifest_payload = build_manifest_payload(
            config_hex,
            device,
            fw_version,
            net_id_hex,
            calibration_hex=calibration_hex,
        )
        write_config_manifest(manifest_path, manifest_payload)
        click.echo(f"[OK  ] wrote config manifest: {manifest_path}")
        click.echo(f"[INFO] manifest: {json.dumps(manifest_payload, indent=2)}")
    else:
        click.echo(f"[INFO] using existing config hex: {config_hex}")
    click.echo()
    # Program every image first and reset once at the end. The two cores
    # hand-shake over shared memory during bring-up, so they have to start
    # together, and starting them before the config page is written boots the
    # network core against an erased net_id.
    flash_nrf_both_cores(app_hex, net_hex, nrfjprog_opt=None, snr_opt=snr, reset=False)
    flash_nrf_one_core(net_hex=config_hex, nrfjprog_opt=None, snr_opt=snr, reset=False)
    if default_app_hex is not None:
        click.echo(f"[INFO] default app hex: {default_app_hex}")
        flash_nrf_one_core(
            app_hex=default_app_hex, nrfjprog_opt=None, snr_opt=snr, reset=False
        )
    elif device == "dotbot-v3":
        click.echo("[INFO] default app hex not found; skipping.")
    click.secho("\n[INFO] ==== Flash Complete ====\n", fg="green")
    time.sleep(0.2)
    readback_net_id = readback_device_id = None
    try:
        readback_net_id = read_net_id(snr=snr)
        readback_device_id = read_device_id(snr=snr)
    except RuntimeError as exc:
        click.echo(f"[WARN] readback failed: {exc}", err=True)
    if readback_net_id is None or readback_device_id is None:
        reset_device(snr=snr)
        click.echo("[OK  ] device reset (CTRL-AP); it should join on its own")
        return
    click.echo("[INFO] readback values:")
    click.echo(f"[INFO] net_id: {readback_net_id}")
    last_6_digits_spaced = " ".join(
        readback_device_id[-6:][i : i + 2]
        for i in range(0, len(readback_device_id[-6:]), 2)
    )
    click.echo(
        f"[INFO] device_id: {readback_device_id} (last 6 digits: {last_6_digits_spaced})"
    )
    # Reset last. Reading the config page back halts the network core, so a
    # reset done any earlier leaves the device programmed but stopped.
    reset_device(snr=snr)
    click.echo("[OK  ] device reset (CTRL-AP); it should join on its own")


def flash_app_image(
    image: Path, *, board: str = "dotbot-v3", sn_starting_digits: str | None = None
) -> None:
    """Flash a single firmware image to one cabled device (a whole-chip program).

    Backend for `dotbot device flash <app|file>`. Accepts a `.hex` (flashed
    as-is) or a `.bin` (converted at APP_FLASH_BASE_ADDR first). `board`
    selects the nrfjprog family + core via `boards.spec_for`: an nRF52 board
    flashes its single core; on the nRF5340 a `*-net` board programs the
    network core, otherwise the application core. No sandbox host required.
    """
    from .boards import spec_for

    if not image.exists():
        raise click.ClickException(f"Firmware image not found: {image}")
    spec = spec_for(board)
    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; pass --probe with the board's "
            "J-Link serial-number prefix (e.g. --probe 77)."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}")
    image_hex = (
        convert_bin_to_hex(image, APP_FLASH_BASE_ADDR)
        if image.suffix == ".bin"
        else image
    )
    click.echo(f"[INFO] flashing {board} ({spec.family}) image: {image_hex}")
    if spec.coprocessor == "CP_NETWORK":
        flash_nrf_one_core(net_hex=image_hex, family=spec.family, snr_opt=snr)
    else:
        flash_nrf_one_core(app_hex=image_hex, family=spec.family, snr_opt=snr)
    click.secho("\n[INFO] ==== Flash Complete ====\n", fg="green")


def read_config_report(sn_starting_digits: str | None = None) -> tuple[str, str]:
    """Read back (net_id, device_id) from a connected device.

    Backend for `dotbot device info`. Returns net_id (or the string
    "unprovisioned" when the config page has no valid magic) and the
    64-bit device id. Raises RuntimeError only on a genuine nrfjprog
    communication failure — a blank/unprovisioned board is not an error.
    """
    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; pass --probe with the board's "
            "J-Link serial-number prefix (e.g. --probe 77)."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}", err=True)
    try:
        return read_net_id(snr=snr), read_device_id(snr=snr)
    finally:
        # Reading the config page attaches the debugger to the network core,
        # which resets it. The application core does not notice, so the device
        # is left alive but with no radio - indistinguishable from dead. Reset
        # the whole device so both cores come back up together.
        reset_device(snr=snr)
        click.echo(
            "[INFO] device reset (CTRL-AP) after the network-core read", err=True
        )


def flash_programmer(
    programmer_firmware: str, files_dir: Path, probe_uid: str | None = None
) -> None:
    """Flash J-Link OB / DAPLink firmware to the on-board debug chip.

    Backend for `dotbot device flash-programmer` (was
    `provision flash-bringup`). Programs the APM32F103 programmer chip
    itself — an obscure, one-time-per-board bring-up step.
    """
    files_dir = files_dir.expanduser().resolve()
    if not files_dir.exists():
        raise click.ClickException(f"files-dir does not exist: {files_dir}")

    required = {
        "jlink": JLINK_REQUIRED_FILES,
        "daplink": DAPLINK_REQUIRED_FILES,
    }[programmer_firmware]

    missing = [name for name in required if not (files_dir / name).exists()]
    if missing:
        missing_list = ", ".join(missing)
        raise click.ClickException(
            f"Missing required files in {files_dir}: {missing_list}"
        )

    click.echo(f"[INFO] programmer: {programmer_firmware}")
    click.echo(f"[INFO] files-dir: {files_dir}")
    if probe_uid:
        click.echo(f"[INFO] probe uid: {probe_uid}")
    if programmer_firmware == "jlink":
        jlink_bin = (files_dir / "JLink-ob.bin").resolve()
        bl_hex = (files_dir / "stm32f103xb_bl.hex").resolve()
        pack_path = str((files_dir / GEEHY_PACK_NAME).resolve())
        do_jlink(
            jlink_bin,
            bl_hex,
            apm_device=APM_DEVICE,
            jlinktool=None,
            pack_path=pack_path,
            probe_uid=probe_uid,
        )
    elif programmer_firmware == "daplink":
        bl_hex = (files_dir / "stm32f103xb_bl.hex").resolve()
        if_hex = (files_dir / "stm32f103xb_if.hex").resolve()
        pack_path = str((files_dir / GEEHY_PACK_NAME).resolve())
        do_daplink(
            bl_hex,
            apm_device=APM_DEVICE,
            jlinktool=None,
            pack_path=pack_path,
            probe_uid=probe_uid,
        )
        time.sleep(1.0)
        do_daplink_if(
            if_hex,
            apm_device=APM_DEVICE,
            pack_path=pack_path,
            probe_uid=probe_uid,
        )
    else:
        raise click.ClickException(
            f"Invalid programmer firmware: {programmer_firmware}"
        )

    # small delay to let the target settle if needed
    time.sleep(1.0)
    click.secho(
        f"[OK  ] ==== {programmer_firmware} programmer firmware flashed ====",
        fg="green",
    )
