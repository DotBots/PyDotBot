# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Checks on a mark: a robot parked on a taped mark, its fix against the
mark, kept beside the site's calibrations in checks.toml.

The file is only ever appended to, and no calibration file is touched, so
a calibration's id and bytes stay what robots and logs name.
"""

from __future__ import annotations

import math
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from dotbot.calibration import lighthouse2

CHECKS_FILE = "checks.toml"


def checks_path(site: str) -> Path:
    return lighthouse2.site_dir(site) / CHECKS_FILE


def _num(v: float) -> str:
    return f"{float(v):.1f}"


def append_check(
    site: str,
    calibration: str,
    mark_mm: tuple[float, float],
    measured_mm: tuple[float, float],
    robot: str,
    predicted_mm: float | None = None,
    note: str = "",
    now: datetime | None = None,
) -> dict:
    """Append one check and return it as written."""
    now = now or datetime.now(timezone.utc)
    error = math.dist(mark_mm, measured_mm)
    entry = {
        "calibration": calibration,
        "mark_mm": [round(float(v), 1) for v in mark_mm],
        "measured_mm": [round(float(v), 1) for v in measured_mm],
        "error_mm": round(error, 2),
        "robot": robot.upper(),
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    lines = [
        "",
        "[[check]]",
        f'calibration = "{calibration}"',
        f"mark_mm = [{_num(mark_mm[0])}, {_num(mark_mm[1])}]",
        f"measured_mm = [{_num(measured_mm[0])}, {_num(measured_mm[1])}]",
        f"error_mm = {entry['error_mm']}",
        f'robot = "{entry["robot"]}"',
        f'at = "{entry["at"]}"',
    ]
    if predicted_mm is not None and math.isfinite(predicted_mm):
        entry["predicted_mm"] = round(float(predicted_mm), 2)
        lines.append(f"predicted_mm = {entry['predicted_mm']}")
    if note.strip():
        entry["note"] = note.strip()
        lines.append(f'note = "{lighthouse2.toml_escape(note.strip())}"')
    path = checks_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = (
        ""
        if path.exists()
        else "# Checks on a mark: a robot's fix against a taped mark, appended by\n"
        "# the site editor; calibration files are never rewritten.\n"
    )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(head + "\n".join(lines) + "\n")
    return entry


def read_checks(site: str) -> list[dict]:
    """Every check of `site`, oldest first; none when there is no file."""
    path = checks_path(site)
    if not path.is_file():
        return []
    try:
        with open(path, "rb") as handle:
            return list(tomllib.load(handle).get("check", []))
    except (OSError, tomllib.TOMLDecodeError):
        return []


def last_check(site: str, calibration_id: str) -> dict | None:
    """The newest check of `calibration_id` on `site`."""
    mine = [c for c in read_checks(site) if str(c.get("calibration", "")) == calibration_id]
    return mine[-1] if mine else None


def check_line(check: dict | None) -> str:
    if not check:
        return "checked on a mark: not recorded"
    mark = check.get("mark_mm", [0, 0])
    robot = str(check.get("robot", ""))
    return (
        f"checked on a mark: {float(check.get('error_mm', 0)):.1f} mm at "
        f"({mark[0]:g}, {mark[1]:g}) by …{robot[-6:]}, {check.get('at', '')}"
    )
