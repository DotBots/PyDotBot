# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What the site editor's Stations kind draws for one calibration and one
set of station boxes: the predicted error of the station a robot keeps, the
headline `calibrate-lh2 show` prints, where to spin next, and where the
stations stand.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from dotbot.calibration import multi_station as ms
from dotbot.calibration import station_geometry, station_rule
from dotbot.calibration.lighthouse2 import Calibration
from dotbot.site import Site

# The fog's cell, mm: fine enough to draw, coarse enough to send
FOG_CELL_MM = 20.0

# calibration id -> its solve; files are immutable, so it never goes stale
_MODELS: dict[str, ms.CoverageModel | None] = {}


def _model(calibration: Calibration) -> ms.CoverageModel | None:
    if calibration.id not in _MODELS:
        try:
            _MODELS[calibration.id] = ms.coverage_model(calibration)
        except (ValueError, np.linalg.LinAlgError):
            _MODELS[calibration.id] = None
    return _MODELS[calibration.id]


def _flat(grid: np.ndarray, digits: int = 3) -> list[float | None]:
    return [
        None if not math.isfinite(v) else round(float(v), digits) for v in grid.ravel()
    ]


def _per_station(model: ms.CoverageModel, rects, headline: ms.ErrorMap) -> dict:
    """Each station's worst predicted error on the headline's cells, where it
    may give the fix (alone, or as a candidate where the boxes do not decide)."""
    rows, cols = headline.sigma_mm.shape
    out = {}
    for s in model.stations:
        if s not in rects:
            continue
        own = model.error_map(
            {s: rects[s]},
            headline.cell_mm,
            (
                headline.origin_mm[0],
                headline.origin_mm[1],
                headline.origin_mm[0] + cols * headline.cell_mm,
                headline.origin_mm[1] + rows * headline.cell_mm,
            ),
        ).sigma_mm
        worst = None
        for row in range(rows):
            for col in range(cols):
                x, y = headline.centre(row, col)
                v = own[row, col]
                if math.isfinite(v) and s in station_rule.candidates(rects, x, y):
                    worst = v if worst is None else max(worst, v)
        out[str(s)] = None if worst is None else round(float(worst), 3)
    return out


def coverage(
    calibration: Calibration,
    site: Site,
    boxes: Mapping[int, Sequence[int]] | None = None,
    robots: int = 4,
) -> dict:
    """The Stations kind's numbers for `calibration` with `boxes` (its own
    when None), on `site`'s floor."""
    rects = {
        int(k): tuple(int(v) for v in r)
        for k, r in (
            boxes or {st.index: st.coverage_mm for st in calibration.stations}
        ).items()
    }
    limit = site.error_limit_mm
    out: dict = {
        "id": calibration.id,
        "limit_mm": limit,
        "geometry": station_geometry.geometry(calibration),
        "links": [
            {
                "a": k.a,
                "b": k.b,
                "shared": k.shared,
                "spread_mm": round(k.spread_mm),
                "disagreement_mm": round(k.disagreement_mm, 2),
                "holds": ms.link_holds(k),
                "advised": ms.link_advised(k),
            }
            for k in calibration.links
        ],
        "headline": None,
        "fog": None,
        "next": [],
    }
    model = _model(calibration)
    if model is None or not rects:
        return out
    headline = model.error_map(rects)
    if np.all(np.isnan(headline.sigma_mm)):
        return out
    row, col = np.unravel_index(
        np.nanargmax(headline.sigma_mm), headline.sigma_mm.shape
    )
    out["headline"] = {
        "worst_mm": round(headline.worst_mm, 3),
        "at": [round(v) for v in headline.centre(int(row), int(col))],
        "bound": headline.worst_is_bound,
        "fused_worst_mm": round(headline.fused_worst_mm, 3),
        "cells": int(np.sum(np.isfinite(headline.sigma_mm))),
        "cells_over_limit": int(np.sum(headline.sigma_mm > limit)),
        "cell_mm": headline.cell_mm,
        "per_station": _per_station(model, rects, headline),
    }
    xs = [r[0] for r in rects.values()] + [r[2] for r in rects.values()]
    ys = [r[1] for r in rects.values()] + [r[3] for r in rects.values()]
    if site.extent_mm is not None:
        xs += [0, site.extent_mm[0]]
        ys += [0, site.extent_mm[1]]
    region = (min(xs), min(ys), max(xs), max(ys))
    fog = model.error_map(rects, FOG_CELL_MM, region)
    rows, cols = fog.sigma_mm.shape
    own = {}
    for s in model.stations:
        alone = model.error_map({s: region}, FOG_CELL_MM, region)
        own[str(s)] = _flat(alone.sigma_mm)
    out["fog"] = {
        "origin": list(fog.origin_mm),
        "cell_mm": fog.cell_mm,
        "cols": cols,
        "rows": rows,
        "sigma": _flat(fog.sigma_mm),
        "undecided": [
            bool(v)
            for v in (
                fog.undecided
                if fog.undecided is not None
                else np.zeros_like(fog.sigma_mm, bool)
            ).ravel()
        ],
        "own": own,
    }
    out["next"] = [
        {
            "x": round(t.point_mm[0]),
            "y": round(t.point_mm[1]),
            "stations": list(t.stations),
            "why": t.why,
        }
        for t in ms.next_round(headline, rects, calibration.links, robots=robots)
    ]
    return out
