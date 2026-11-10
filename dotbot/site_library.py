# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One site's LH2 calibrations as the site editor's library lists them:
the served file first, then the files in the site's frame grouped by the
spin they were measured from, then the files not placed in the site yet.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from dotbot.calibration import lighthouse2, station_rule
from dotbot.calibration.station_boxes import frame_refusal
from dotbot.site import Site

# path -> ((mtime_ns, size), row)
_ROWS: dict[Path, tuple[tuple[int, int], dict]] = {}


def spin_fingerprint(calibration: lighthouse2.Calibration) -> str:
    """8 hex digits naming the measurement a file holds: its content id
    without its boxes, so files differing only in boxes share it."""
    text = lighthouse2.canonical_serialisation(calibration)
    kept = "\n".join(line for line in text.split("\n") if "valid_mm" not in line)
    return hashlib.sha256(kept.encode("utf-8")).hexdigest()[:8]


def site_files(folders: Iterable[Path]) -> list[Path]:
    """Every calibration file directly in `folders`, each once."""
    seen, out = set(), []
    for folder in folders:
        for path in sorted(Path(folder).glob(lighthouse2.CALIBRATION_TOML_GLOB)):
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                out.append(path)
    return out


def _row(path: Path) -> dict | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _ROWS.get(path)
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        cal = lighthouse2.read_calibration_file(path)
    except (OSError, ValueError):
        return None
    boxes = {st.index: tuple(int(v) for v in st.valid_mm) for st in cal.stations}
    row = {
        "id": cal.id,
        "id8": cal.id8,
        "tag": cal.tag,
        "created_at": cal.created_at,
        "path": str(path),
        "site": cal.site.name,
        "anchor": cal.site.anchor,
        "fence": [int(v) for v in cal.valid_mm],
        "spin": spin_fingerprint(cal),
        "tracks": len(cal.tracks),
        "stations": [
            {
                "index": st.index,
                "residual_mm": round(st.residual_mm, 2),
                "box": list(boxes[st.index]),
                "solved_from": st.solved_from,
            }
            for st in sorted(cal.stations, key=lambda s: s.index)
        ],
        "reading": station_rule.reading(boxes),
    }
    _ROWS[path] = (key, row)
    return row


def library(folders: Iterable[Path], site: Site, served_id: str | None) -> dict:
    """The library of `site`'s calibration `folders`, `served_id` pinned first."""
    rows = [r for r in (_row(p) for p in site_files(folders)) if r is not None]
    serving = None
    groups: dict[str, list[dict]] = {}
    not_placed: list[dict] = []
    for r in rows:
        file_site = Site(name=r["site"], anchor=r["anchor"])
        row = {
            **{k: v for k, v in r.items() if k != "anchor"},
            "in_frame": frame_refusal(file_site, site) is None,
            "served": bool(served_id) and r["id"] == served_id,
        }
        if row["served"]:
            serving = row
        if row["in_frame"]:
            groups.setdefault(r["spin"], []).append(row)
        else:
            not_placed.append(row)
    newest = lambda rs: max(x["created_at"] for x in rs)  # noqa: E731
    return {
        "site": site.name,
        "served": served_id,
        "serving": serving,
        "count": len(rows),
        "groups": [
            {
                "spin": spin,
                "created_at": newest(members),
                "rows": sorted(members, key=lambda x: (not x["served"], x["id8"])),
            }
            for spin, members in sorted(
                groups.items(), key=lambda kv: newest(kv[1]), reverse=True
            )
        ],
        "not_placed": sorted(not_placed, key=lambda x: x["created_at"], reverse=True),
    }
