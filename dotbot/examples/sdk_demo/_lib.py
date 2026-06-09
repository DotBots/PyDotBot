# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for the sdk_demo set.

Every geometric quantity (centre, rings, bearings) is computed from the *live*
fleet positions, never hardcoded, so the same demo runs unchanged in the
simulator and on the real testbed regardless of arena size or where the bots
happen to sit.
"""

from __future__ import annotations

import asyncio
import colorsys
import math

from dotbot.sdk import Position, Swarm


async def settle(swarm: Swarm, seconds: float = 1.5) -> list:
    """Wait for the first ws/status round to arrive, then return the bots that
    have a position fix, sorted by address (stable order across runs)."""
    await asyncio.sleep(seconds)
    bots = positioned(swarm)
    print(f"{len(bots)}/{len(swarm)} bots have a position fix")
    return bots


def positioned(swarm: Swarm) -> list:
    """The bots that currently have an LH2 fix, ordered by address."""
    return sorted(
        (b for b in swarm if b.position is not None), key=lambda b: b.address
    )


def centroid(bots: list) -> Position:
    """The mean position of the fleet - its live centre."""
    n = len(bots)
    return Position(
        sum(b.position.x for b in bots) / n,
        sum(b.position.y for b in bots) / n,
    )


def max_radius(bots: list, center: Position) -> float:
    return max(b.position.distance_to(center) for b in bots)


def make_rings(bots: list, center: Position, n_rings: int) -> list:
    """Bucket bots into `n_rings` concentric rings by distance from `center`
    (ring 0 = innermost, ring n-1 = outermost edge)."""
    r_max = max_radius(bots, center) or 1.0
    rings: list = [[] for _ in range(n_rings)]
    for b in bots:
        frac = b.position.distance_to(center) / r_max
        rings[min(int(frac * n_rings), n_rings - 1)].append(b)
    return rings


def angle_deg(bot, center: Position) -> float:
    """Bearing of a bot from `center`, in degrees."""
    return math.degrees(
        math.atan2(bot.position.y - center.y, bot.position.x - center.x)
    )


def rotate(p: Position, center: Position, deg: float) -> Position:
    """Rotate point `p` about `center` by `deg` degrees (counter-clockwise)."""
    rad = math.radians(deg)
    dx, dy = p.x - center.x, p.y - center.y
    return Position(
        center.x + dx * math.cos(rad) - dy * math.sin(rad),
        center.y + dx * math.sin(rad) + dy * math.cos(rad),
    )


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> tuple:
    """HSV (h wrapped into [0, 1)) -> (r, g, b) ints 0..255 for set_color()."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)
