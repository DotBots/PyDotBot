# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What a calibration is, in the lines an experiment log keeps."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from dotbot.calibration import station_rule
from dotbot.calibration.checks import check_line
from dotbot.calibration.lighthouse2 import Calibration
from dotbot.calibration.multi_station import ErrorMap
from dotbot.site import Site


def fix_lines(calibration: Calibration) -> list[str]:
    """Who gives the fix, by the robots' station rule, where the boxes meet."""
    rects = {st.index: st.coverage_mm for st in calibration.stations}
    if len(rects) < 2:
        return []
    links = {(k.a, k.b): k for k in calibration.links}
    lines = [f"who gives the fix: {station_rule.reading(rects)}"]
    for group in station_rule.shared_centres(rects):
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                link = links.get((a, b))
                why = (
                    f"their {link.disagreement_mm:.2f} mm disagreement on "
                    f"{link.shared} shared circles decides"
                    if link is not None
                    else "their disagreement decides, and no link measures it"
                )
                lines.append(
                    f"  where S{a} and S{b} both hold a robot the boxes do not "
                    f"decide: {why}, when both stations see it"
                )
    return lines


def provenance_lines(
    calibration: Calibration,
    site: Site,
    error_map: ErrorMap | None,
    served: str | None = None,
    now: datetime | None = None,
    check: dict | None = None,
) -> list[str]:
    """The block to copy into an experiment log."""
    now = now or datetime.now(timezone.utc)
    name = calibration.site.name
    lines = [
        "provenance:",
        f"  site {name}, frame {calibration.site.frame_id}",
        f"  calibration {calibration.id}"
        + (f" {calibration.tag!r}" if calibration.tag else "")
        + f", measured {calibration.created_at or 'at an unknown time'}",
    ]
    if served:
        lines.append(f"  served by {served}")
    residuals = ", ".join(
        f"S{st.index} {st.residual_mm:.1f} mm"
        for st in sorted(calibration.stations, key=lambda s: s.index)
    )
    lines.append(f"  residuals {residuals or 'none'}")
    rects = {st.index: st.coverage_mm for st in calibration.stations}
    lines.append(f"  boxes {station_rule.reading(rects)}")
    limit = site.error_limit_mm
    if error_map is None or math.isnan(error_map.worst_mm):
        lines.append(f"  no error map: not a spin calibration (limit {limit:.1f} mm)")
    else:
        verdict = "under" if error_map.worst_mm <= limit else "over"
        bound = " (a bound)" if error_map.worst_is_bound else ""
        lines.append(
            f"  predicted error, station kept: worst {error_map.worst_mm:.1f} mm"
            f"{bound}, {verdict} the {limit:.1f} mm limit"
        )
    lines.append(f"  {check_line(check)}")
    lines.append(f"  printed {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    return lines
