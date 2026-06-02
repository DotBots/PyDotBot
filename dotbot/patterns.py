# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Geometric placement patterns for a fleet of simulated bots.

Pure geometry: each function returns a list of ``(x, y)`` positions in mm inside
a square arena. The simulator uses these to place ``--bots N --layout <kind>``
without hand-writing an init-state file. ``grid`` and ``random`` are the two
universal layouts (ARGoS / Gazebo); ``circle`` and ``line`` are cheap extras.
"""

from __future__ import annotations

import math
import random as _random

ARENA = 2000  # default square arena side, in mm (matches the default map size)
MARGIN = 150  # keep bots this far off the walls, in mm


def grid(
    n: int, *, arena: int = ARENA, margin: int = MARGIN
) -> list[tuple[float, float]]:
    """N bots on a square-ish grid that fills the arena."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    span = arena - 2 * margin
    xs = [margin + span * (c + 0.5) / cols for c in range(cols)]
    ys = [margin + span * (r + 0.5) / rows for r in range(rows)]
    return [(x, y) for y in ys for x in xs][:n]


def circle(
    n: int, *, arena: int = ARENA, margin: int = MARGIN
) -> list[tuple[float, float]]:
    """N bots spaced evenly on a circle centred in the arena."""
    center = arena / 2
    radius = center - margin
    return [
        (
            center + radius * math.cos(2 * math.pi * i / n),
            center + radius * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def line(
    n: int, *, arena: int = ARENA, margin: int = MARGIN
) -> list[tuple[float, float]]:
    """N bots in a horizontal row across the middle of the arena."""
    center = arena / 2
    if n == 1:
        return [(center, center)]
    span = arena - 2 * margin
    return [(margin + span * i / (n - 1), center) for i in range(n)]


def scatter(
    n: int, *, arena: int = ARENA, margin: int = MARGIN, seed: int = 0
) -> list[tuple[float, float]]:
    """N bots at uniform-random positions, seeded for reproducibility."""
    rng = _random.Random(seed)
    lo, hi = margin, arena - margin
    return [(rng.uniform(lo, hi), rng.uniform(lo, hi)) for _ in range(n)]


LAYOUTS = {"grid": grid, "circle": circle, "line": line, "random": scatter}


def layout(
    n: int,
    kind: str = "grid",
    *,
    seed: int = 0,
    arena: int = ARENA,
    margin: int = MARGIN,
) -> list[tuple[float, float]]:
    """Positions for ``n`` bots in the named ``kind`` layout."""
    if kind not in LAYOUTS:
        raise ValueError(f"unknown layout {kind!r}; choose from {sorted(LAYOUTS)}")
    if kind == "random":
        return scatter(n, arena=arena, margin=margin, seed=seed)
    return LAYOUTS[kind](n, arena=arena, margin=margin)
