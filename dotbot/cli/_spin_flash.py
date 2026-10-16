# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Put the calibrate-spin app on the robots `collect --spin` picks."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable

import click

from dotbot.cli._artifacts import artifacts_dir
from dotbot.cli._swarm_flash import APP_CATALOG, _filename

SPIN_FILE = _filename(APP_CATALOG["calibrate-spin"])
_SET_PREFIX = "dotbot-firmware-"


def image_sets(artifacts: Path) -> dict[str, list[Path]]:
    """Each sandboxed image's sha256 in the dotbot-firmware sets, to the
    sets holding it, by name."""
    index: dict[str, list[Path]] = {}
    for folder in sorted(artifacts.glob(f"{_SET_PREFIX}*")):
        for image in sorted(folder.glob("*.bin")):
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            index.setdefault(digest, []).append(folder)
    return index


def sets_of_digest(digest: str, index: dict[str, list[Path]]) -> list[Path]:
    """The sets holding the image whose sha256 starts with `digest`, the
    prefix a robot reports."""
    digest = (digest or "").lower()
    if len(digest) < 16 or not digest.strip("0"):
        return []
    return next((f for d, f in index.items() if d.startswith(digest)), [])


def robots_sets(status: dict[str, Any], addresses: list[str]) -> list[Path]:
    """The sets every robot's current image is in: one when that settles it,
    several when byte-identical images sit in several sets, none when the
    images are unknown or come from different sets."""
    index = image_sets(artifacts_dir())
    common: list[Path] | None = None
    for addr in addresses:
        info = getattr(status[addr], "info", None)
        found = sets_of_digest(getattr(info, "image_digest", ""), index)
        common = found if common is None else [f for f in common if f in found]
    return common or []


def set_label(folder: Path, artifacts: Path) -> str:
    """How `-f` names `folder`: the set name in the cache, else its path."""
    if folder.parent == artifacts and folder.name.startswith(_SET_PREFIX):
        return folder.name[len(_SET_PREFIX) :]
    return str(folder)


def spin_images(
    status: dict[str, Any], addresses: list[str], fw_version: str | None
) -> dict[Path, list[str]]:
    """The calibrate-spin image each robot is flashed with, grouped by image."""
    from dotbot.firmware.fetch import resolve_fw_dir

    artifacts = artifacts_dir()
    index = image_sets(artifacts) if fw_version is None else {}
    groups: dict[Path, list[str]] = {}
    fallback: Path | None = None
    for addr in sorted(addresses):
        folder = None
        if fw_version is None:
            info = getattr(status[addr], "info", None)
            found = sets_of_digest(getattr(info, "image_digest", ""), index)
            folder = next((f for f in found if (f / SPIN_FILE).is_file()), None)
        if folder is None:
            if fallback is None:
                fallback, _ = resolve_fw_dir(
                    "dotbot-firmware",
                    fw_version,
                    artifacts,
                    required=(SPIN_FILE,),
                    build="calibrate-spin",
                )
            folder = fallback
        groups.setdefault(folder / SPIN_FILE, []).append(addr)
    return groups


def flash_over_air(client: Any, image: Path, devices: list[str]) -> list[str]:
    """OTA-flash `image` onto `devices`; return the ones it did not reach.

    Raises RuntimeError when the flash fails as a whole.
    """
    events = client.flash(image.read_bytes(), devices=devices, image_name=image.name)
    done: dict[str, bool] = {}
    for event in events:
        kind = event.get("type")
        if kind == "warning":
            click.echo(f"  warning: {event.get('message', '')}")
        elif kind == "device_done":
            done[event["addr"]] = bool(event.get("success"))
        elif kind == "error":
            raise RuntimeError(event.get("message", "flash failed"))
        elif kind == "complete":
            break
    return sorted(d for d in devices if not done.get(d))


def flash_spin_app(
    client: Any,
    status: dict[str, Any],
    addresses: list[str],
    fw_version: str | None,
    stop: Callable[[Any, list[str]], list[str]],
) -> dict[str, Path]:
    """Flash calibrate-spin onto `addresses`; return each robot's image.

    `stop` stops the robots that are in their app and returns those still
    there. Raises ClickException naming the robots it could not flash.
    """
    from dotbot.calibration.push import in_app

    groups = spin_images(status, addresses, fw_version)
    running = [a for a in addresses if in_app(status[a])]
    if running:
        busy = stop(client, running)
        if busy:
            raise click.ClickException(
                "still in their app after a stop, so not flashed: " + ", ".join(busy)
            )
    failed: list[str] = []
    for image, addrs in groups.items():
        click.echo(
            f"Flashing {image.name} from {image.parent} onto {len(addrs)} "
            f"robot(s): {', '.join(addrs)}"
        )
        try:
            failed += flash_over_air(client, image, addrs)
        except RuntimeError as exc:
            raise click.ClickException(f"flashing calibrate-spin failed: {exc}")
    if failed:
        raise click.ClickException(
            "calibrate-spin did not reach " + ", ".join(failed) + "; leave them "
            "out with `dotbot swarm -d <addresses> ...`, or retry."
        )
    return {addr: image for image, addrs in groups.items() for addr in addrs}


def await_flashed(
    client: Any,
    flashed: list[str],
    devices: list[str] | None,
    timeout: float = 15.0,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Re-read device info until no robot in `flashed` is still resetting or
    programming, or `timeout` seconds pass; return the last `status()`."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    deadline = clock() + timeout
    while True:
        client.refresh_device_info(devices)
        fresh = client.status()
        busy = [
            a
            for a in flashed
            if getattr(getattr(fresh.get(a), "status", None), "name", "")
            in ("Resetting", "Programming")
        ]
        if not busy or clock() >= deadline:
            return fresh
        sleep(1.0)
