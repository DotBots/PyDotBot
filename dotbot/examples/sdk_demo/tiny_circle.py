# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Each bot traces a small circle around its own starting point.

A motion demo built on the primary waypoint primitive (follow). Net
displacement is ~zero - every bot ends where it began - but each one sweeps a
small disc, so each bot's radius is derived from its *live* spacing to its
nearest neighbour: small enough that even two neighbours at the worst phase
of their circles keep a body's width between them. Crowded bots get smaller
circles or sit the round out; the rest of the fleet rides at full size.

    python -m dotbot.examples.sdk_demo.tiny_circle [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.examples.sdk_demo._lib import SAFE_RADIUS, settle
from dotbot.swarm import Swarm

MAX_RADIUS = 120  # mm - never bigger than this, however sparse the fleet
MIN_RADIUS = 40  # mm - below this a circle is not worth driving
POINTS = 8  # waypoints per circle


def safe_radii(bots: list) -> dict:
    """Per-bot circle radius such that two neighbours circling in opposite
    phase (each eating 2r of their gap) still keep 2*SAFE_RADIUS clearance.
    A crowded bot gets a small circle (or sits the round out); the rest of
    the fleet is not punished for it."""
    out = {}
    for a in bots:
        gap = min(
            (a.position.distance_to(b.position) for b in bots if b is not a),
            default=float("inf"),
        )
        out[a.address] = min(MAX_RADIUS, (gap - 2 * SAFE_RADIUS) / 4)
    return out


def circle(bot, radius: float) -> list:
    # Centre the circle below the start so the path begins (and ends) at home.
    cx, cy = bot.position.x, bot.position.y - radius
    return [
        (
            cx + radius * math.sin(2 * math.pi * k / POINTS),
            cy + radius * math.cos(2 * math.pi * k / POINTS),
        )
        for k in range(1, POINTS + 1)
    ]


async def tiny_circle(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    radii = safe_radii(bots) if len(bots) > 1 else {b.address: MAX_RADIUS for b in bots}
    riders = [b for b in bots if radii[b.address] >= MIN_RADIUS]
    if not riders:
        print("fleet too crowded for circles everywhere; aborting")
        return
    sitting = len(bots) - len(riders)
    if sitting:
        print(f"{sitting} bots too crowded for a circle; they sit this one out")
    print(f"{len(riders)} bots tracing circles (radii up to {MAX_RADIUS} mm) ...")
    swarm.all.set_color("cyan")
    try:
        await asyncio.gather(
            *(b.follow(circle(b, radii[b.address])) for b in riders)
        )
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(tiny_circle)
