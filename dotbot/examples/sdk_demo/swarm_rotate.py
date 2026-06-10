# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The whole swarm rotates as one formation about its centroid.

The showpiece. Three things make it behave like real robots instead of ghosts:

  1. if the live formation cannot rotate safely - some pair tighter than the
     BVC safety floor, or the sweep would leave the arena - the fleet first
     re-forms into a disc that keeps every bot's bearing from the centre
     (so it still "looks like" the fleet) but spaces everyone out and fits
     the walls;
  2. the rotation is a *servo*, not a sequence of jumps: every tick each bot
     is steered (through the BVC safety projection) at the formation rotated
     by the current angle, and the angle only advances while the slowest bot
     is keeping up - the formation turns as fast as its laggard allows;
  3. every waypoint goes through safe_hop, so even a bot that has to U-turn
     arcs inside a widened buffer instead of into a neighbour.

Each bot is coloured by its bearing so the rotating "spokes" are easy to see.

    python -m dotbot.examples.sdk_demo.swarm_rotate [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.examples.sdk_demo._lib import (
    ARRIVE,
    SAFE_RADIUS,
    WALL_MARGIN,
    angle_deg,
    centroid,
    drive,
    hop_goto,
    hsv,
    max_radius,
    pace_tick,
    rotate,
    safe_hop,
    settle,
)
from dotbot.sdk import Position, Swarm

TOTAL_ANGLE = 90  # degrees to rotate the whole formation
DEG_TICK = 6  # degrees the formation advances per tick when nobody lags
LAG_HOLD = 280  # mm: a bot this far behind its slot pauses the rotation
SETTLE_SECS = 15.0  # s budget for the final convergence on the end pose
FLOOR_GAP = 2 * SAFE_RADIUS + 60  # spacing every pair needs, plus slack


def _disc(bots: list, center, radius: float) -> dict:
    """A bearing-preserving disc: each bot keeps its angle from the centre and
    is placed at a radius set by its rank, spacing the fleet evenly."""
    ranked = sorted(bots, key=lambda b: b.position.distance_to(center))
    n = len(bots)
    out = {}
    for k, b in enumerate(ranked):
        ang = math.atan2(b.position.y - center.y, b.position.x - center.x)
        r = radius * math.sqrt((k + 0.5) / n)
        out[b.address] = Position(
            center.x + r * math.cos(ang), center.y + r * math.sin(ang)
        )
    return out


async def swarm_rotate(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    w, h = await swarm.map_size()
    center = centroid(bots)
    home = {b.address: b.position for b in bots}

    r_fit = min(center.x, w - center.x, center.y, h - center.y) - WALL_MARGIN
    r_max = max_radius(bots, center) or 1.0
    min_gap = min(
        a.position.distance_to(b.position)
        for i, a in enumerate(bots)
        for b in bots[i + 1 :]
    )
    if min_gap < FLOOR_GAP or r_max > r_fit:
        print("re-forming into a safe disc before rotating ...")
        # Size the disc from the spacing requirement (mean nearest-neighbour
        # distance in a disc of n bots is ~R*sqrt(pi/n)), capped by the walls.
        r_disc = min(r_fit, FLOOR_GAP * math.sqrt(len(bots) / math.pi) * 1.2)
        home = _disc(bots, center, r_disc)
        await drive(bots, {a: (p.x, p.y) for a, p in home.items()}, (w, h))

    for b in bots:  # colour by bearing so the rotation is legible
        b.set_color(hsv((angle_deg(b, center) % 360) / 360))

    print(f"rotating {len(bots)} bots {TOTAL_ANGLE} deg about the centroid ...")
    tick = pace_tick(len(bots))
    max_ticks = int(4 * TOTAL_ANGLE / DEG_TICK) + 30  # stalls must not hang us
    angle = 0.0
    held = 0
    try:
        for _ in range(max_ticks):
            if angle >= TOTAL_ANGLE:
                break
            positions = {
                b.address: (b.position.x, b.position.y) for b in bots if b.position
            }
            targets = {a: rotate(p, center, angle) for a, p in home.items()}
            lag = max(
                math.hypot(t.x - positions[a][0], t.y - positions[a][1])
                for a, t in targets.items()
                if a in positions
            )
            # Advance when the fleet keeps up - or after a few held ticks, so a
            # single boxed-in laggard slows the show instead of freezing it.
            if lag < LAG_HOLD or held >= 4:
                angle = min(angle + DEG_TICK, TOTAL_ANGLE)
                targets = {a: rotate(p, center, angle) for a, p in home.items()}
                held = 0
            else:
                held += 1
            for b in bots:
                if b.address in positions:
                    t = targets[b.address]
                    px, py = positions[b.address]
                    hop_goto(b, safe_hop(b, positions, (t.x, t.y), (w, h)), px, py)
            await asyncio.sleep(tick)
        goals = {
            a: (rotate(p, center, TOTAL_ANGLE).x, rotate(p, center, TOTAL_ANGLE).y)
            for a, p in home.items()
        }
        arrived = await drive(bots, goals, (w, h), timeout=SETTLE_SECS, arrive=ARRIVE)
        print(f"{len(arrived)}/{len(bots)} on the final pose")
    finally:
        swarm.all.stop()
    print("done")


if __name__ == "__main__":
    Swarm.run(swarm_rotate)
