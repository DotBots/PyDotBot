# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Spread a clustered swarm out without collisions, edge-first.

The idea you sketched: the bots on the border move first (there is open space
beyond them, nobody to hit), then the next layer out into the room they vacate,
and so on. Two rules together make the whole bloom collision-free:

  1. every bot moves *straight outward* from the swarm centre, never sideways -
     so the paths are radial spokes that never cross each other;
  2. a bot's target radius grows with its current rank from the centre, so the
     outermost bot ends up outermost - no bot ever overtakes the one ahead of it
     on its spoke.

Released in waves from the outside in, a clump blooms into an even disc and no
bot drives into an occupied spot. Contrast `distribute`, which reaches a tidy
grid but lets paths cross - this one is the collision-safe option for hardware.

Best run from a clustered start (that is the case it is built for). With --loop
it re-gathers the fleet first - a sim-only replay step that *does* crowd them -
then blooms again.

    python -m dotbot.examples.sdk_demo.disperse [--loop] [--swarm-url http://localhost:8000]
"""

import argparse
import asyncio
import math
import random

from dotbot.examples.sdk_demo._lib import centroid, hsv, settle
from dotbot.sdk import Swarm

MAP_SIZE = 2500  # arena side in mm; match `dotbot run controller ... -m <S>x<S>`
MARGIN = 250  # keep targets this far from the walls
WAVES = 6  # number of outside-in release waves
WAVE_GAP = 1.3  # s between waves (let the border clear before the next layer)
SETTLE_SECS = 5.0  # s of re-asserting targets so every bot reaches the disc
HOLD = 2.5  # s to hold the spread
REGATHER_SPREAD = 150  # mm clump radius for the --loop replay


def _clamp(x: float, y: float) -> tuple:
    lo, hi = MARGIN, MAP_SIZE - MARGIN
    return (min(max(x, lo), hi), min(max(y, lo), hi))


def _disc_targets(bots: list, center) -> dict:
    """Each bot keeps its bearing from the centre and is pushed out to a radius
    set by its rank, filling an even disc that fits inside the arena. Rank order
    is preserved, so every bot moves only outward and none overtakes another."""
    n = len(bots)
    radius = min(
        center.x - MARGIN,
        MAP_SIZE - MARGIN - center.x,
        center.y - MARGIN,
        MAP_SIZE - MARGIN - center.y,
    )
    radius = max(radius, 1.0)
    ranked = sorted(bots, key=lambda b: b.position.distance_to(center))
    out = {}
    for k, b in enumerate(ranked):
        ang = math.atan2(b.position.y - center.y, b.position.x - center.x)
        r = radius * math.sqrt((k + 0.5) / n)
        out[b.address] = _clamp(center.x + r * math.cos(ang), center.y + r * math.sin(ang))
    return out


async def _bloom(bots: list) -> None:
    center = centroid(bots)
    targets = _disc_targets(bots, center)
    outward = sorted(bots, key=lambda b: b.position.distance_to(center), reverse=True)
    size = max(1, math.ceil(len(outward) / WAVES))
    released: list = []
    for w in range(0, len(outward), size):
        wave = outward[w : w + size]
        for b in wave:
            b.set_color(hsv(0.33 + 0.5 * w / len(outward)))  # outer green -> inner blue
        released += wave
        for b in released:  # re-assert every released bot (a dropped goto is retried)
            b.goto(*targets[b.address])
        await asyncio.sleep(WAVE_GAP)
    loop = asyncio.get_running_loop()
    end = loop.time() + SETTLE_SECS
    while loop.time() < end:
        for b in bots:
            b.goto(*targets[b.address])
        await asyncio.sleep(1.0)


async def disperse(swarm: Swarm) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--loop", action="store_true", help="re-gather (sim replay) then bloom again"
    )
    opts, _ = parser.parse_known_args()
    bots = await settle(swarm)
    if not bots:
        return
    try:
        while True:
            print("blooming outward, edge-first (collision-free) ...")
            await _bloom(bots)
            await asyncio.sleep(HOLD)
            if not opts.loop:
                break
            print("re-gathering to the centre (sim replay) ...")
            swarm.all.set_color("red")
            cx, cy = MAP_SIZE / 2, MAP_SIZE / 2
            for _ in range(6):
                for b in bots:
                    b.goto(
                        cx + random.uniform(-REGATHER_SPREAD, REGATHER_SPREAD),
                        cy + random.uniform(-REGATHER_SPREAD, REGATHER_SPREAD),
                    )
                await asyncio.sleep(1.0)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(disperse)
