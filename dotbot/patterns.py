# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Geometric placement patterns for a fleet of simulated bots.

Pure geometry: each function returns a list of ``(x, y)`` positions in mm inside
a rectangular arena (``width`` x ``height``, both defaulting to the square
``arena``). The simulator uses these to place ``--bots N --layout <kind>``
without hand-writing an init-state file, sized to the active ``--map-size`` so
the fleet fills the whole map. ``grid`` and ``random`` are the two universal
layouts (ARGoS / Gazebo); ``circle`` and ``line`` are cheap extras. ``random``
keeps every bot at least ``min_dist`` (centre-to-centre) from its neighbours so
bots are never placed on top of each other.
"""

from __future__ import annotations

import math
import random as _random

ARENA = 2000  # default square arena side, in mm (matches the default map size)
MARGIN = 150  # keep bots this far off the walls, in mm

# A DotBot is ~10-13 cm across; with ~5 cm of clearance, place no two bots
# closer than this (centre-to-centre) in the random layout. Tune here (or pass
# ``min_dist=`` to ``scatter``/``layout``) for tighter or looser packing.
MIN_SEPARATION = 180  # mm


def _dims(width: int | None, height: int | None, arena: int) -> tuple[float, float]:
    return float(width if width is not None else arena), float(
        height if height is not None else arena
    )


def grid(
    n: int,
    *,
    arena: int = ARENA,
    width: int | None = None,
    height: int | None = None,
    margin: int = MARGIN,
) -> list[tuple[float, float]]:
    """N bots on a grid that fills the arena (column count matched to the
    arena's aspect ratio)."""
    if n <= 0:
        return []
    w, h = _dims(width, height, arena)
    span_x = max(1.0, w - 2 * margin)
    span_y = max(1.0, h - 2 * margin)
    cols = max(1, round(math.sqrt(n * span_x / span_y)))
    rows = math.ceil(n / cols)
    xs = [margin + span_x * (c + 0.5) / cols for c in range(cols)]
    ys = [margin + span_y * (r + 0.5) / rows for r in range(rows)]
    return [(x, y) for y in ys for x in xs][:n]


def circle(
    n: int,
    *,
    arena: int = ARENA,
    width: int | None = None,
    height: int | None = None,
    margin: int = MARGIN,
) -> list[tuple[float, float]]:
    """N bots spaced evenly on a circle centred in the arena."""
    w, h = _dims(width, height, arena)
    center_x, center_y = w / 2, h / 2
    radius = min(w, h) / 2 - margin
    return [
        (
            center_x + radius * math.cos(2 * math.pi * i / n),
            center_y + radius * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def line(
    n: int,
    *,
    arena: int = ARENA,
    width: int | None = None,
    height: int | None = None,
    margin: int = MARGIN,
) -> list[tuple[float, float]]:
    """N bots in a horizontal row across the middle of the arena."""
    w, h = _dims(width, height, arena)
    center_y = h / 2
    if n == 1:
        return [(w / 2, center_y)]
    span = w - 2 * margin
    return [(margin + span * i / (n - 1), center_y) for i in range(n)]


def scatter(
    n: int,
    *,
    arena: int = ARENA,
    width: int | None = None,
    height: int | None = None,
    margin: int = MARGIN,
    seed: int = 0,
    min_dist: float = MIN_SEPARATION,
) -> list[tuple[float, float]]:
    """N bots at random positions, no two closer than ``min_dist``
    (centre-to-centre), seeded for reproducibility.

    Grid-accelerated rejection sampling (so it scales to ~1000 bots). If the
    arena is too crowded to honour ``min_dist`` for all ``n``, the spacing is
    progressively relaxed (with a warning) rather than looping forever, so a
    fleet is always placed.
    """
    if n <= 0:
        return []
    w, h = _dims(width, height, arena)
    lo_x, hi_x = float(margin), max(float(margin), w - margin)
    lo_y, hi_y = float(margin), max(float(margin), h - margin)

    def _attempt(d: float) -> list[tuple[float, float]]:
        cell = d / math.sqrt(2) if d > 0 else max(hi_x - lo_x, hi_y - lo_y, 1.0)
        grid_cells: dict[tuple[int, int], list[tuple[float, float]]] = {}
        rng = _random.Random(seed)

        def _far_enough(x: float, y: float) -> bool:
            if d <= 0:
                return True
            ci, cj = int((x - lo_x) / cell), int((y - lo_y) / cell)
            d2 = d * d
            for i in range(ci - 2, ci + 3):
                for j in range(cj - 2, cj + 3):
                    for px, py in grid_cells.get((i, j), ()):
                        if (x - px) ** 2 + (y - py) ** 2 < d2:
                            return False
            return True

        placed: list[tuple[float, float]] = []
        # Bounded attempts so an over-constrained arena can never hang.
        for _ in range(n * 60):
            if len(placed) >= n:
                break
            x = rng.uniform(lo_x, hi_x)
            y = rng.uniform(lo_y, hi_y)
            if _far_enough(x, y):
                placed.append((x, y))
                grid_cells.setdefault(
                    (int((x - lo_x) / cell), int((y - lo_y) / cell)), []
                ).append((x, y))
        return placed

    dist = float(min_dist)
    placed = _attempt(dist)
    while len(placed) < n and dist > 1.0:
        dist *= 0.85  # relax and retry (still reproducible: same seed)
        placed = _attempt(dist)
    if dist < min_dist and placed:
        try:
            from dotbot.logger import LOGGER

            LOGGER.bind(context=__name__).warning(
                "random layout relaxed bot spacing to fit the arena",
                requested_mm=round(min_dist),
                used_mm=round(dist),
                bots=n,
            )
        except Exception:  # noqa: BLE001 - logging must never break placement
            pass
    return placed[:n]


LAYOUTS = {"grid": grid, "circle": circle, "line": line, "random": scatter}


def layout(
    n: int,
    kind: str = "grid",
    *,
    seed: int = 0,
    arena: int = ARENA,
    width: int | None = None,
    height: int | None = None,
    margin: int = MARGIN,
    min_dist: float = MIN_SEPARATION,
) -> list[tuple[float, float]]:
    """Positions for ``n`` bots in the named ``kind`` layout, sized to
    ``width`` x ``height`` (default: the square ``arena``)."""
    if kind not in LAYOUTS:
        raise ValueError(f"unknown layout {kind!r}; choose from {sorted(LAYOUTS)}")
    if kind == "random":
        return scatter(
            n,
            arena=arena,
            width=width,
            height=height,
            margin=margin,
            seed=seed,
            min_dist=min_dist,
        )
    return LAYOUTS[kind](n, arena=arena, width=width, height=height, margin=margin)
