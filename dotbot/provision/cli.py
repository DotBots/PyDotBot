#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import click

from .nrf_flash import (
    do_daplink,
    do_daplink_if,
    do_jlink,
    flash_nrf_both_cores,
    flash_nrf_one_core,
    pick_last_jlink_snr,
    pick_matching_jlink_snr,
    read_device_id,
    read_net_id,
)

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
CONFIG_MAGIC = 0x5753524D
CONFIG_MANIFEST_NAME = "config-manifest.json"
# LH2 calibration is appended to the swarmit config page after (magic, net_id).
# Matches swarmit's swarmit_config_t and the format produced by
# dotbot-lh2-calibration (1-byte count + N matrices of 3x3 int32 LE).
LH2_MATRIX_BYTES = 3 * 3 * 4  # 3x3 int32 matrix
LH2_MAX_HOMOGRAPHIES = 16
RELEASE_BASE_URL = "https://github.com/DotBots/swarmit/releases/download"
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
        raise click.ClickException(
            "network_id must be 16-bit (0x0000..0xFFFF)."
        )
    return value, f"{value:04X}"


def resolve_fw_root(bin_dir: Path, fw_version: str) -> Path:
    return bin_dir / fw_version


def download_file(url: str, dest: Path) -> None:
    click.echo(f"[GET ] {url}")
    try:
        with urllib.request.urlopen(url) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                raise click.ClickException(
                    f"HTTP {status} while downloading {url}"
                )
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise click.ClickException(
            f"HTTP error while downloading {url}: {exc}"
        ) from exc
    except urllib.error.URLError as exc:
        raise click.ClickException(
            f"Network error while downloading {url}: {exc}"
        ) from exc

    dest.write_bytes(data)
    click.echo(f"[OK  ] wrote {dest} ({len(data)} bytes)")


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


def load_calibration_file(path: Path) -> tuple[int, bytes]:
    """Parse a swarmit LH2 calibration file: 1-byte count + N*36 bytes."""
    data = path.read_bytes()
    if len(data) < 1 or (len(data) - 1) % LH2_MATRIX_BYTES != 0:
        raise click.ClickException(
            f"Invalid calibration file size: expected 1+N*{LH2_MATRIX_BYTES} "
            f"bytes (count byte + matrices), got {len(data)}"
        )
    count = data[0]
    matrices = data[1:]
    expected = len(matrices) // LH2_MATRIX_BYTES
    if count != expected:
        raise click.ClickException(
            f"Invalid calibration file: count byte ({count}) does not match "
            f"matrix payload length ({expected})"
        )
    if count == 0:
        raise click.ClickException(
            "Invalid calibration file: homography count cannot be zero"
        )
    if count > LH2_MAX_HOMOGRAPHIES:
        raise click.ClickException(
            f"Invalid calibration file: homography count {count} exceeds "
            f"LH2 limit ({LH2_MAX_HOMOGRAPHIES})"
        )
    return count, matrices


def _write_word_le(ih, addr: int, word: int) -> None:
    ih[addr + 0] = (word >> 0) & 0xFF
    ih[addr + 1] = (word >> 8) & 0xFF
    ih[addr + 2] = (word >> 16) & 0xFF
    ih[addr + 3] = (word >> 24) & 0xFF


def create_config_hex(
    dest: Path,
    net_id_value: int,
    calibration: tuple[int, bytes] | None = None,
) -> None:
    if IntelHex is None:
        raise click.ClickException(
            "intelhex not available; install it to build config hex."
        )
    ih = IntelHex()
    # Layout matches swarmit_config_t in repos/swarmit/device/network_core/Source/main.c
    # and mari_app_config_t in repos/mari/firmware/app/03app_gateway_net/main.c:
    #   offset 0:  magic (uint32 LE)
    #   offset 4:  has_net_id (uint32 LE)        — 1 means the net_id below is provisioned
    #   offset 8:  net_id (uint32 LE)
    #   offset 12: homography_count (uint32 LE)  — swarmit only; meaningful only with --calibration
    #   offset 16: homographies[N][3][3] (int32 LE) — swarmit only
    _write_word_le(ih, CONFIG_ADDR + 0, CONFIG_MAGIC)
    _write_word_le(ih, CONFIG_ADDR + 4, 1)
    _write_word_le(ih, CONFIG_ADDR + 8, net_id_value)
    if calibration is not None:
        count, matrices = calibration
        _write_word_le(ih, CONFIG_ADDR + 12, count)
        for i, b in enumerate(matrices):
            ih[CONFIG_ADDR + 16 + i] = b
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
        "magic": f"0x{CONFIG_MAGIC:08X}",
        # Stored inline as hex (count byte + matrices, same bytes as the
        # input file). Calibration data is small (typically <100 B, capped
        # well under 1 kB at 16 matrices), so inlining keeps the manifest
        # self-contained and human-inspectable.
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
        and payload.get("magic") == f"0x{CONFIG_MAGIC:08X}"
        and payload.get("calibration") == calibration_hex
        and isinstance(payload.get("config_hex"), str)
    )


@click.group(
    help="A tool for provisioning DotBot devices and gateways in the context of a SwarmIT-enabled testbed."
)
def cli() -> None:
    pass


@cli.command("fetch", help="Fetch firmware assets into bin/<fw-version>/.")
@click.option(
    "--fw-version",
    "-f",
    required=True,
    help="Firmware version tag or 'local'.",
)
@click.option(
    "--local-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    help="Root directory for local builds (used with --fw-version local).",
)
@click.option(
    "--bin-dir",
    default=DEFAULT_BIN_DIR,
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    show_default=True,
    help="Destination bin directory.",
)
def cmd_fetch(fw_version: str, local_root: Path | None, bin_dir: Path) -> None:
    if fw_version == "local" and not local_root:
        raise click.ClickException(
            "--local-root is required when --fw-version=local."
        )
    if fw_version != "local" and local_root:
        click.echo(
            "[WARN] --local-root ignored when --fw-version is not 'local'.",
            err=True,
        )

    out_dir = resolve_fw_root(bin_dir, fw_version)
    out_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"[INFO] target dir: {out_dir}")

    if fw_version == "local":
        local_root = local_root.expanduser().resolve()
        mapping = {
            "bootloader-dotbot-v3.hex": local_root
            / "device/bootloader/Output/dotbot-v3/Debug/Exe/bootloader-dotbot-v3.hex",
            "netcore-nrf5340-net.hex": local_root
            / "device/network_core/Output/nrf5340-net/Debug/Exe/netcore-nrf5340-net.hex",
            "03app_gateway_app-nrf5340-app.hex": local_root
            / "mari/firmware/app/03app_gateway_app/Output/nrf5340-app/Debug/Exe/03app_gateway_app-nrf5340-app.hex",
            "03app_gateway_net-nrf5340-net.hex": local_root
            / "mari/firmware/app/03app_gateway_net/Output/nrf5340-net/Debug/Exe/03app_gateway_net-nrf5340-net.hex",
        }

        missing = [name for name, src in mapping.items() if not src.exists()]
        if missing:
            missing_list = ", ".join(missing)
            raise click.ClickException(
                f"Missing local build artifacts: {missing_list}"
            )

        for name, src in mapping.items():
            dest = out_dir / name
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            try:
                os.symlink(src, dest)
                click.echo(f"[LINK] {dest} -> {src}")
            except OSError:
                shutil.copy2(src, dest)
                click.echo(f"[COPY] {dest} <- {src}")
        return

    assets = [
        "bootloader-dotbot-v3.hex",
        "netcore-nrf5340-net.hex",
        "03app_gateway_app-nrf5340-app.hex",
        "03app_gateway_net-nrf5340-net.hex",
    ]
    example_bins = [
        "dotbot-dotbot-v3.bin",
        "spin-dotbot-v3.bin",
        "rgbled-dotbot-v3.bin",
        "move-dotbot-v3.bin",
        "motors-dotbot-v3.bin",
    ]
    for name in assets:
        url = f"{RELEASE_BASE_URL}/{fw_version}/{name}"
        dest = out_dir / name
        download_file(url, dest)
    for name in example_bins:
        url = f"{RELEASE_BASE_URL}/{fw_version}/{name}"
        dest = out_dir / name
        download_file(url, dest)


@cli.command(
    "flash",
    help="Flash firmware + config using versioned bin layout.",
)
@click.option(
    "--device", "-d", type=click.Choice(VALID_DEVICES), required=True
)
@click.option("--fw-version", "-f", help="Firmware version tag or 'local'.")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.option("--network-id", "-n", help="16-bit hex network ID, e.g. 0100.")
@click.option(
    "--calibration",
    "-l",
    "calibration_path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help=(
        "Optional LH2 calibration file to bake into the swarmit config page "
        "(1-byte count + N*36 bytes, same format as `swarmit calibrate-lh2`). "
        "Only valid for --device dotbot-v3."
    ),
)
@click.option(
    "--sn-starting-digits",
    "-s",
    help="Serial number pattern to use for auto-selection, e.g. 77.",
)
@click.option(
    "--bin-dir",
    default=DEFAULT_BIN_DIR,
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    show_default=True,
    help="Bin directory containing firmware files.",
)
@click.option(
    "--app",
    "-a",
    "default_app_name",
    help=(
        "Optional app name to flash after provisioning (dotbot-v3 only). "
        "Looks for <name>-<device>.hex or .bin in the firmware root."
    ),
)
def cmd_flash(
    device: str,
    fw_version: str | None,
    config_path: Path | None,
    network_id: str | None,
    calibration_path: Path | None,
    sn_starting_digits: str | None,
    bin_dir: Path,
    default_app_name: str | None,
) -> None:
    assets = DEVICE_ASSETS[device]

    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; provide --snr explicitly."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}")

    if device == "dotbot-v3" and not snr.startswith("77"):
        click.secho(
            f"[WARN] Serial number {snr} seems to not be a DotBot, but you are trying to flash a {device} firmware to it.",
            fg="yellow",
        )
        if not click.confirm(
            "Do you want to continue? (you can check or plug the right board)",
            default=True,
        ):
            raise click.ClickException("Aborting.")
    elif device == "gateway" and snr.startswith("77"):
        click.secho(
            f"[WARN] Serial number {snr} seems to be a DotBot, but you are trying to flash a {device} firmware to it.",
            fg="yellow",
        )
        if not click.confirm(
            "Do you want to continue? (you can check or plug the right board)",
            default=True,
        ):
            raise click.ClickException("Aborting.")

    config = {}
    if config_path:
        config = load_config(config_path)

    provisioning = (
        config.get("provisioning", {}) if isinstance(config, dict) else {}
    )
    fw_version = fw_version or provisioning.get("firmware_version")
    net_raw = network_id or provisioning.get("network_id")

    if not fw_version:
        raise click.ClickException(
            "Missing --fw-version (or provisioning.firmware_version in config)."
        )
    net_id = normalize_network_id(net_raw)
    if net_id is None:
        raise click.ClickException(
            "Missing --network-id (or provisioning.network_id in config)."
        )

    net_id_val, net_id_hex = net_id

    calibration_data: tuple[int, bytes] | None = None
    calibration_hex: str | None = None
    if calibration_path is not None:
        if device != "dotbot-v3":
            raise click.ClickException(
                "--calibration is only valid for --device dotbot-v3 "
                "(gateway firmware does not have LH2 homographies)."
            )
        count, matrices = load_calibration_file(calibration_path)
        calibration_data = (count, matrices)
        calibration_hex = (bytes([count]) + matrices).hex()
        click.echo(
            f"[INFO] calibration: {count} matrices from {calibration_path}"
        )

    fw_root = resolve_fw_root(bin_dir, fw_version)
    if not fw_root.exists():
        raise click.ClickException(f"Firmware root not found: {fw_root}")

    default_app_hex: Path | None = None
    if device == "dotbot-v3":
        if default_app_name:
            name = default_app_name.strip()
            if not name:
                raise click.ClickException("--app cannot be empty.")
            candidate = fw_root / f"{name}-{device}.bin"
            if candidate.exists():
                default_app_hex = convert_bin_to_hex(
                    candidate, APP_FLASH_BASE_ADDR
                )
            else:
                raise click.ClickException(
                    f"App firmware not found: {candidate}"
                )
        else:
            # default to dotbot app if no name is provided
            candidate = fw_root / "dotbot-dotbot-v3.bin"
            if candidate.exists():
                default_app_hex = convert_bin_to_hex(
                    candidate, APP_FLASH_BASE_ADDR
                )
    else:
        if default_app_name:
            click.echo(
                "[WARN] --app is only supported for dotbot-v3; skipping.",
                err=True,
            )

    app_hex = fw_root / assets["app"]
    net_hex = fw_root / assets["net"]
    manifest_path = fw_root / CONFIG_MANIFEST_NAME
    manifest = load_config_manifest(manifest_path)
    config_hex = None
    if manifest:
        click.echo(
            f"[INFO] loaded manifest {manifest_path}: {json.dumps(manifest, indent=2)}"
        )
        if manifest_matches(
            manifest, device, fw_version, net_id_hex, calibration_hex
        ):
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
        config_hex = make_config_hex_path(
            fw_root, device, fw_version, net_id_hex
        )
        click.secho(f"[INFO] created new config hex: {config_hex}", fg="green")

    missing = [str(p) for p in (app_hex, net_hex) if not p.exists()]
    if missing:
        missing_list = ", ".join(missing)
        raise click.ClickException(f"Missing firmware files: {missing_list}")

    click.echo(f"[INFO] device: {device}")
    click.echo(f"[INFO] fw_version: {fw_version}")
    click.echo(f"[INFO] network_id: 0x{net_id_hex}")
    click.echo(f"[INFO] app hex: {app_hex}")
    click.echo(f"[INFO] net hex: {net_hex}")
    click.echo(f"[INFO] config hex: {config_hex}")

    if not config_hex.exists():
        create_config_hex(config_hex, net_id_val, calibration=calibration_data)
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
        click.echo(
            f"[INFO] manifest: {json.dumps(manifest_payload, indent=2)}"
        )
    else:
        click.echo(f"[INFO] using existing config hex: {config_hex}")
    click.echo()
    flash_nrf_both_cores(app_hex, net_hex, nrfjprog_opt=None, snr_opt=snr)
    flash_nrf_one_core(net_hex=config_hex, nrfjprog_opt=None, snr_opt=snr)
    if default_app_hex is not None:
        click.echo(f"[INFO] default app hex: {default_app_hex}")
        flash_nrf_one_core(
            app_hex=default_app_hex, nrfjprog_opt=None, snr_opt=snr
        )
    elif device == "dotbot-v3":
        click.echo("[INFO] default app hex not found; skipping.")
    click.secho("\n[INFO] ==== Flash Complete ====\n", fg="green")
    time.sleep(0.2)
    try:
        readback_net_id = read_net_id(snr=snr)
        readback_device_id = read_device_id(snr=snr)
    except RuntimeError as exc:
        click.echo(f"[WARN] readback failed: {exc}", err=True)
        return
    click.echo(f"[INFO] readback values:")
    click.echo(f"[INFO] net_id: {readback_net_id}")
    last_6_digits_spaced = " ".join(
        readback_device_id[-6:][i:i+2] for i in range(0, len(readback_device_id[-6:]), 2)
    )
    click.echo(f"[INFO] device_id: {readback_device_id} (last 6 digits: {last_6_digits_spaced})")


@cli.command("flash-hex", help="Flash explicit app/net hex files.")
@click.option(
    "--app", "app_hex", type=click.Path(path_type=Path, dir_okay=False)
)
@click.option(
    "--net", "net_hex", type=click.Path(path_type=Path, dir_okay=False)
)
def cmd_flash_hex(app_hex: Path | None, net_hex: Path | None) -> None:
    if not app_hex and not net_hex:
        raise click.ClickException("Provide at least one of --app or --net.")
    if app_hex:
        click.echo(f"[TODO] flash app core: {app_hex}")
    if net_hex:
        click.echo(f"[TODO] flash net core: {net_hex}")


@cli.command("read-config", help="Read config from the device.")
@click.option(
    "--sn-starting-digits",
    "-s",
    help="Serial number pattern to use for auto-selection, e.g. 77.",
)
def cmd_read_config(sn_starting_digits: str | None) -> None:
    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; provide --snr explicitly."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}")
    try:
        readback_net_id = read_net_id(snr=snr)
        readback_device_id = read_device_id(snr=snr)
    except RuntimeError as exc:
        click.echo(f"[WARN] readback failed: {exc}", err=True)
        return
    click.echo(f"[INFO] readback net_id: {readback_net_id}")
    last_6_digits_spaced = " ".join(
        readback_device_id[-6:][i:i+2] for i in range(0, len(readback_device_id[-6:]), 2)
    )
    click.echo(f"[INFO] readback device_id: {readback_device_id} (last 6 digits: {last_6_digits_spaced})")


@cli.command(
    "flash-bringup",
    help="Flash J-Link OB or DAPLink programmer firmware.",
)
@click.option(
    "--programmer-firmware",
    "-p",
    type=click.Choice(VALID_PROGRAMMERS),
    required=True,
)
@click.option(
    "--files-dir",
    "-d",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    required=True,
)
@click.option(
    "--probe-uid",
    help="pyOCD probe UID (use when multiple probes are connected).",
)
def cmd_flash_bringup(
    programmer_firmware: str, files_dir: Path, probe_uid: str | None
) -> None:
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


def main() -> int:
    cli(standalone_mode=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
