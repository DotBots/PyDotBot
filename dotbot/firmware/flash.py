"""DotBot firmware flashing + provisioning engine (no CLI).

The hardware-facing engine behind `dotbot device` and `dotbot fw fetch`:
fetch release assets, flash a role's system firmware + config page
(`flash_role`), flash a single app image (`flash_app_image`), flash the
debug-chip programmer (`flash_programmer`), and read back provisioning
state (`read_config_report`). The Click surface lives in
`dotbot/cli/device.py` and `dotbot/cli/fw.py`; this module is pure
library code.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

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
GITHUB_API = "https://api.github.com/repos"
# Firmware release sources. swarmit ships the swarm system images (bootloader
# + mari netcore + mari gateway); DotBot-firmware ships the bare apps (.hex)
# and the sandbox apps (.bin). Each is cached in its own <source>-<version>/
# subdir of the artifacts cache so versions and provenance never collide.
RELEASE_SOURCES = {
    "swarmit": "DotBots/swarmit",
    "dotbot-firmware": "DotBots/DotBot-firmware",
}
DEFAULT_FETCH_SOURCES = ("swarmit", "dotbot-firmware")
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


def resolve_fw_root(bin_dir: Path, source: str, fw_version: str) -> Path:
    return bin_dir / f"{source}-{fw_version}"


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _short_path(path: Path) -> str:
    """Path relative to the cwd when that's shorter, else absolute."""
    rel = os.path.relpath(path)
    return rel if not rel.startswith("..") else str(path)


# Transient HTTP statuses worth retrying (GitHub's asset CDN 502s now and
# then under concurrent load; 429 is rate-limiting).
_RETRY_STATUS = {429, 500, 502, 503, 504}


def download_file(url: str, dest: Path, *, retries: int = 3) -> int:
    """Download ``url`` to ``dest``; return the number of bytes written.

    Retries transient failures (connection errors and HTTP 429/5xx) with
    exponential backoff - GitHub's CDN occasionally 502s under concurrent
    downloads, and a sporadic failure shouldn't abort the whole fetch.
    """
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise click.ClickException(f"HTTP {status} while downloading {url}")
                data = resp.read()
            dest.write_bytes(data)
            return len(data)
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRY_STATUS or attempt == retries:
                raise click.ClickException(
                    f"HTTP error while downloading {url}: {exc}"
                ) from exc
            reason = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            if attempt == retries:
                raise click.ClickException(
                    f"Network error while downloading {url}: {exc}"
                ) from exc
            reason = str(exc.reason)
        delay = 0.5 * (2**attempt)
        click.echo(
            f"  [retry] {url.rsplit('/', 1)[-1]} ({reason}); retrying in {delay:.1f}s",
            err=True,
        )
        time.sleep(delay)
    raise click.ClickException(  # pragma: no cover - loop always returns/raises
        f"Failed to download {url} after {retries} retries."
    )


def _github_get(url: str):
    """Unauthenticated GitHub API GET (60 req/hour is plenty for a CLI)."""
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "dotbot"},
    )
    try:
        with urllib.request.urlopen(request) as resp:
            return json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise click.ClickException(f"GitHub API request failed ({url}): {exc}") from exc


def resolve_release(source: str, fw_version: str) -> dict:
    """Return the GitHub release JSON for ``source`` at ``fw_version``.

    ``fw_version="latest"`` resolves the newest release via ``/releases``
    (prereleases included, unlike ``/releases/latest`` which skips them - the
    current newest, e.g. swarmit 0.8.0rc2, is a prerelease).
    """
    if source not in RELEASE_SOURCES:
        raise click.ClickException(
            f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
        )
    repo = RELEASE_SOURCES[source]
    if fw_version == "latest":
        releases = _github_get(f"{GITHUB_API}/{repo}/releases?per_page=1")
        if not releases:
            raise click.ClickException(
                f"No releases found for {repo}; pass an explicit -f <version>."
            )
        return releases[0]
    return _github_get(f"{GITHUB_API}/{repo}/releases/tags/{fw_version}")


def resolve_latest_version(source: str = "swarmit") -> str:
    """The newest release tag for ``source`` (prereleases included)."""
    return resolve_release(source, "latest")["tag_name"]


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
    """Parse a swarmit LH2 calibration file.

    Accepts two formats:

    - **TOML** (`*.toml`, the modern record): schema-versioned, carries
      metadata (timestamp, station count, calibration distance). The
      `[calibration].data_hex` field is the same byte payload as the
      legacy format, hex-encoded.
    - **Legacy binary** (`calibration.out`): 1-byte count + N × 36 bytes.

    The flash path itself only needs the raw bytes; this loader just
    extracts them from whichever envelope was provided.
    """
    if path.suffix == ".toml":
        if tomllib is None:
            raise click.ClickException(
                "Reading a .toml calibration file needs Python 3.11+ "
                "(tomllib in the stdlib) or the tomli backport."
            )
        try:
            # Binary mode lets tomllib handle UTF-8 itself (TOML is
            # spec'd as UTF-8); read_text() would pick up the platform
            # default (cp1252 on Windows) and mangle the contents.
            with open(path, "rb") as f:
                parsed = tomllib.load(f)
            data = bytes.fromhex(parsed["calibration"]["data_hex"])
        except (KeyError, ValueError) as exc:
            raise click.ClickException(
                f"Malformed TOML calibration file {path}: {exc}"
            ) from exc
    else:
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


def fetch_assets(
    source: str, fw_version: str, bin_dir: Path, local_root: Path | None = None
) -> Path:
    """Fetch one source's firmware into ``bin_dir/<source>-<version>/``.

    For a released version, downloads every ``.hex``/``.bin`` asset the GitHub
    release publishes (so it adapts to whatever the release ships, no hardcoded
    asset list) and writes a ``manifest.json`` with provenance. For
    ``fw_version="local"``, symlinks/copies from a local build tree into
    ``<source>-local/``. Used by `dotbot fw fetch` and the auto-fetch hook in
    `flash_role`.
    """
    if source not in RELEASE_SOURCES:
        raise click.ClickException(
            f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
        )
    if fw_version == "local" and not local_root:
        raise click.ClickException("--local-root is required when --fw-version=local.")
    if fw_version != "local" and local_root:
        click.echo(
            "[WARN] --local-root ignored when --fw-version is not 'local'.",
            err=True,
        )

    if fw_version == "local":
        return _link_local_assets(source, local_root, bin_dir)

    release = resolve_release(source, fw_version)
    tag = release["tag_name"]
    out_dir = resolve_fw_root(bin_dir, source, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = [
        a for a in release.get("assets", []) if a["name"].endswith((".hex", ".bin"))
    ]
    if not assets:
        raise click.ClickException(
            f"{source} release {tag} publishes no .hex/.bin assets."
        )
    click.echo(
        f"Fetching {source} {tag} ({len(assets)} files) into {_short_path(out_dir)}"
    )
    names: list[str] = []
    errors: list[str] = []
    # Downloads are I/O-bound, so a small thread pool overlaps them (urllib
    # releases the GIL during the network read). Sources stay sequential.
    # Kept modest: GitHub's asset CDN starts 502ing under heavier fan-out
    # (download_file retries transient failures regardless).
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_name = {
            pool.submit(
                download_file, asset["browser_download_url"], out_dir / asset["name"]
            ): asset["name"]
            for asset in assets
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                size = future.result()
            except click.ClickException as exc:
                errors.append(f"{name}: {exc.format_message()}")
                continue
            names.append(name)
            click.echo(f"  {name} ({_human_size(size)})")
    if errors:
        raise click.ClickException(
            f"{len(errors)} asset(s) failed to download:\n  " + "\n  ".join(errors)
        )
    _write_manifest(out_dir, source, tag, RELEASE_SOURCES[source], names)
    return out_dir


def _write_manifest(
    out_dir: Path, source: str, version: str, repo: str, files: list[str]
) -> None:
    """Record provenance next to the binaries (a cheap audit trail)."""
    manifest = {
        "source": source,
        "version": version,
        "repo": repo,
        "url": f"https://github.com/{repo}/releases/tag/{version}",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": sorted(files),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _link_local_assets(source: str, local_root: Path, bin_dir: Path) -> Path:
    """Symlink/copy a local build tree into ``bin_dir/<source>-local/``."""
    if source != "swarmit":
        raise click.ClickException(
            f"--fw-version local is only wired for source 'swarmit' so far, "
            f"not '{source}'."
        )
    local_root = local_root.expanduser().resolve()
    out_dir = resolve_fw_root(bin_dir, source, "local")
    out_dir.mkdir(parents=True, exist_ok=True)
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
        raise click.ClickException(
            f"Missing local build artifacts: {', '.join(missing)}"
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
    return out_dir


def flash_role(
    role: str,
    *,
    net_id: tuple[int, str],
    fw_version: str,
    calibration_path: Path | None = None,
    bin_dir: Path = DEFAULT_BIN_DIR,
    sn_starting_digits: str | None = None,
    default_app_name: str | None = None,
) -> None:
    """Flash a device's role: system firmware bundle (app+net cores) + config.

    Backend for `dotbot device flash-swarmit-sandbox` (role='dotbot-v3') and
    `dotbot device flash-mari-gateway` (role='gateway'). Selects the J-Link,
    flashes both cores, writes the config page (magic + has_net_id +
    net_id [+ calibration, dotbot-v3 only]), then best-effort reads back
    net_id/device_id (never raises on readback failure). If the role's
    images are absent from ``bin_dir/<fw_version>/``, fetches the release
    first (the "run fetch under the hood" behaviour).
    """
    assets = DEVICE_ASSETS[role]
    net_id_val, net_id_hex = net_id

    if sn_starting_digits:
        snr = pick_matching_jlink_snr(sn_starting_digits)
    else:
        snr = pick_last_jlink_snr()
    if snr is None:
        raise click.ClickException(
            "Unable to auto-select J-Link; provide --snr explicitly."
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

    calibration_data: tuple[int, bytes] | None = None
    calibration_hex: str | None = None
    if calibration_path is not None:
        if role != "dotbot-v3":
            raise click.ClickException(
                "--calibration is only valid for the sandbox host (dotbot-v3); "
                "gateway firmware does not have LH2 homographies."
            )
        count, matrices = load_calibration_file(calibration_path)
        calibration_data = (count, matrices)
        calibration_hex = (bytes([count]) + matrices).hex()
        click.echo(f"[INFO] calibration: {count} matrices from {calibration_path}")

    fw_root = resolve_fw_root(bin_dir, "swarmit", fw_version)
    # Auto-fetch: if the role's images aren't already present, pull the
    # swarmit release into bin_dir/swarmit-<version>/ before flashing.
    pre_app = fw_root / assets["app"]
    pre_net = fw_root / assets["net"]
    if fw_version != "local" and not (pre_app.exists() and pre_net.exists()):
        click.echo(f"[INFO] firmware {fw_version} not found in {fw_root}; fetching...")
        fetch_assets("swarmit", fw_version, bin_dir)
    if not fw_root.exists():
        raise click.ClickException(f"Firmware root not found: {fw_root}")

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
    net_hex = fw_root / assets["net"]
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
        click.echo(f"[INFO] manifest: {json.dumps(manifest_payload, indent=2)}")
    else:
        click.echo(f"[INFO] using existing config hex: {config_hex}")
    click.echo()
    flash_nrf_both_cores(app_hex, net_hex, nrfjprog_opt=None, snr_opt=snr)
    flash_nrf_one_core(net_hex=config_hex, nrfjprog_opt=None, snr_opt=snr)
    if default_app_hex is not None:
        click.echo(f"[INFO] default app hex: {default_app_hex}")
        flash_nrf_one_core(app_hex=default_app_hex, nrfjprog_opt=None, snr_opt=snr)
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
    click.echo("[INFO] readback values:")
    click.echo(f"[INFO] net_id: {readback_net_id}")
    last_6_digits_spaced = " ".join(
        readback_device_id[-6:][i : i + 2]
        for i in range(0, len(readback_device_id[-6:]), 2)
    )
    click.echo(
        f"[INFO] device_id: {readback_device_id} (last 6 digits: {last_6_digits_spaced})"
    )
    click.secho(
        "[NOTE] you may need to press the reset button on the DotBot "
        "for it to join the network",
        fg="yellow",
    )


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
            "Unable to auto-select J-Link; provide --snr explicitly."
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
            "Unable to auto-select J-Link; provide --snr explicitly."
        )
    click.echo(f"[INFO] using J-Link with serial number: {snr}", err=True)
    return read_net_id(snr=snr), read_device_id(snr=snr)


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
