# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Each bot traces a small circle around its own starting point.

A motion demo built on the primary waypoint primitive (follow). Net
displacement is ~zero - every bot ends where it began - but each one sweeps a
small disc, so on real hardware keep RADIUS well under half the inter-bot
spacing.

    python -m dotbot.examples.sdk_demo.tiny_circle [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.examples.sdk_demo._lib import settle
from dotbot.sdk import Swarm

RADIUS = 120  # mm - keep small
POINTS = 8  # waypoints per circle


def circle(bot) -> list:
    # Centre the circle below the start so the path begins (and ends) at home.
    cx, cy = bot.position.x, bot.position.y - RADIUS
    return [
        (
            cx + RADIUS * math.sin(2 * math.pi * k / POINTS),
            cy + RADIUS * math.cos(2 * math.pi * k / POINTS),
        )
        for k in range(1, POINTS + 1)
    ]


async def tiny_circle(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    print(f"{len(bots)} bots each tracing a {RADIUS} mm circle ...")
    swarm.all.set_color("cyan")
    try:
        await asyncio.gather(*(b.follow(circle(b)) for b in bots))
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(tiny_circle)
