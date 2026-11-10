# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The last site.toml versions the site editor wrote over, kept on this
machine in ~/.dotbot/history/<site>/ so a Save can be undone."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from dotbot import site_toml
from dotbot.calibration import lighthouse2

KEEP = 20
_NAME = re.compile(r"site-(\d{8}T\d{6}\d{6}Z)-([0-9a-f]{12})\.toml")


def history_dir(site: str) -> Path:
    return lighthouse2.CALIBRATION_DIR / "history" / site


def snapshot(site: str, data: bytes, now: datetime | None = None) -> Path:
    """Keep `data`, the file about to be written over; the oldest past
    `KEEP` are removed."""
    now = now or datetime.now(timezone.utc)
    folder = history_dir(site)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    path = folder / f"site-{stamp}-{site_toml.revision(data)[:12]}.toml"
    path.write_bytes(data)
    for old in versions(site)[KEEP:]:
        Path(old["path"]).unlink(missing_ok=True)
    return path


def versions(site: str) -> list[dict]:
    """The kept versions, newest first."""
    folder = history_dir(site)
    if not folder.is_dir():
        return []
    out = []
    for path in folder.glob("site-*.toml"):
        m = _NAME.fullmatch(path.name)
        if m is None:
            continue
        at = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=timezone.utc
        )
        out.append(
            {
                "id": path.stem,
                "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "revision": site_toml.revision(path.read_bytes()),
                "path": str(path),
            }
        )
    return sorted(out, key=lambda v: v["id"], reverse=True)


def read_version(site: str, version: str) -> bytes:
    """A kept version's bytes, by its id; KeyError when there is none."""
    for v in versions(site):
        if v["id"] == version:
            return Path(v["path"]).read_bytes()
    raise KeyError(version)


# --- Restore points: a named site.toml with the calibration served then ----

_POINTS = "points.json"


def points(site: str) -> list[dict]:
    """The named restore points, newest first."""
    import json

    index = history_dir(site) / _POINTS
    try:
        listed = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(
        (p for p in listed if (history_dir(site) / f"{p['id']}.toml").is_file()),
        key=lambda p: p["at"],
        reverse=True,
    )


def save_point(
    site: str, name: str, data: bytes, served: str | None, now: datetime | None = None
) -> dict:
    """Keep `data` and the served calibration's id under `name`; points are
    never pruned."""
    import json

    now = now or datetime.now(timezone.utc)
    folder = history_dir(site)
    folder.mkdir(parents=True, exist_ok=True)
    point = {
        "id": f"point-{now.strftime('%Y%m%dT%H%M%S%fZ')}",
        "name": name.strip() or now.strftime("%Y-%m-%d %H:%M"),
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "served": served,
        "revision": site_toml.revision(data),
    }
    (folder / f"{point['id']}.toml").write_bytes(data)
    index = folder / _POINTS
    listed = points(site)
    index.write_text(json.dumps([*listed, point], indent=1), encoding="utf-8")
    return point


def read_point(site: str, point: str) -> tuple[dict, bytes]:
    """A restore point and its site.toml bytes; KeyError when there is none."""
    for p in points(site):
        if p["id"] == point:
            return p, (history_dir(site) / f"{p['id']}.toml").read_bytes()
    raise KeyError(point)
