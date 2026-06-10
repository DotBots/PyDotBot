# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Re-arrange the swarm into an even distribution across the arena.

The algorithm: lay down N evenly spaced target points over the arena, assign
each bot to the nearest still-free target (greedy - keeps total travel short),
then shepherd everyone there collision-free with the shared BVC drive() helper:
each bot only ever steps inside its own buffered Voronoi cell, so paths that
would cross simply flow around each other, like real robots have to.

With --loop it gathers the fleet into a compact block (spaced so the bots still
fit without touching) and then re-distributes, over and over. The arena size is
read from the controller, so it matches whatever `-m <W>x<H>` you launched
with.

    python -m dotbot.examples.sdk_demo.distribute [--loop] [--swarm-url http://localhost:8000]
"""

import argparse
import asyncio
import math
import random

from dotbot.examples.sdk_demo._lib import SAFE_RADIUS, WALL_MARGIN, drive, settle
from dotbot.sdk import Swarm

JITTER_MM = 40  # randomise targets a touch so the lattice looks organic
HOLD = 2.5  # s to hold each arrangement
GATHER_PITCH = 2.4 * SAFE_RADIUS  # grid pitch of the --loop gather block


def even_targets(n: int, w: float, h: float) -> list:
    """n points on an even, lightly jittered lattice filling the arena."""
    lo_x, hi_x = WALL_MARGIN, w - WALL_MARGIN
    lo_y, hi_y = WALL_MARGIN, h - WALL_MARGIN
    rows = max(1, round(math.sqrt(n)))
    pts = []
    for r in range(rows):
        in_row = n // rows + (1 if r < n % rows else 0)
        y = lo_y + (r + 0.5) * (hi_y - lo_y) / rows
        for c in range(in_row):
            x = lo_x + (c + 0.5) * (hi_x - lo_x) / in_row
            pts.append(
                (
                    min(max(x + random.uniform(-JITTER_MM, JITTER_MM), lo_x), hi_x),
                    min(max(y + random.uniform(-JITTER_MM, JITTER_MM), lo_y), hi_y),
                )
            )
    return pts


def assign(bots: list, targets: list) -> dict:
    """Assign each bot a target so that routes do not cross: greedy nearest
    first, then 2-opt swaps minimising total *squared* distance - the squared
    metric is what makes straight-line routes provably non-crossing, which is
    most of the collision-avoidance battle won before anyone moves."""
    pairs = sorted(
        (bots[bi].position.distance_to(targets[ti]), bi, ti)
        for bi in range(len(bots))
        for ti in range(len(targets))
    )
    bot_seen: set = set()
    tgt_seen: set = set()
    out: dict = {}
    for _, bi, ti in pairs:
        if bi in bot_seen or ti in tgt_seen:
            continue
        out[bots[bi].address] = targets[ti]
        bot_seen.add(bi)
        tgt_seen.add(ti)

    pos = {b.address: (b.position.x, b.position.y) for b in bots}

    def d2(a: str, t: tuple) -> float:
        return (pos[a][0] - t[0]) ** 2 + (pos[a][1] - t[1]) ** 2

    addrs = list(out)
    improved = True
    while improved:
        improved = False
        for i, a in enumerate(addrs):
            for b in addrs[i + 1 :]:
                if d2(a, out[b]) + d2(b, out[a]) < d2(a, out[a]) + d2(b, out[b]) - 1e-6:
                    out[a], out[b] = out[b], out[a]
                    improved = True
    return out


def gather_targets(bots: list, w: float, h: float) -> list:
    """A compact grid block at a random spot, spaced so the bots fit without
    touching (pitch > 2*SAFE_RADIUS)."""
    cols = max(1, round(math.sqrt(len(bots))))
    rows_n = math.ceil(len(bots) / cols)
    half_w = (cols - 1) / 2 * GATHER_PITCH
    half_h = (rows_n - 1) / 2 * GATHER_PITCH
    cx = random.uniform(WALL_MARGIN + half_w + 1, w - WALL_MARGIN - half_w - 1)
    cy = random.uniform(WALL_MARGIN + half_h + 1, h - WALL_MARGIN - half_h - 1)
    return [
        (cx + (k % cols) * GATHER_PITCH - half_w, cy + (k // cols) * GATHER_PITCH - half_h)
        for k in range(len(bots))
    ]


async def distribute(swarm: Swarm) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--loop", action="store_true", help="gather then re-distribute, repeatedly"
    )
    opts, _ = parser.parse_known_args()

    bots = await settle(swarm)
    if not bots:
        return
    w, h = await swarm.map_size()
    print(f"arena {w}x{h} mm; distributing {len(bots)} bots ...")

    try:
        while True:
            print("distributing ...")
            swarm.all.set_color("green")
            arrived = await drive(bots, assign(bots, even_targets(len(bots), w, h)), (w, h))
            print(f"{len(arrived)}/{len(bots)} arrived")
            await asyncio.sleep(HOLD)
            if not opts.loop:
                break
            print("gathering ...")
            swarm.all.set_color("red")
            await drive(bots, assign(bots, gather_targets(bots, w, h)), (w, h))
            await asyncio.sleep(HOLD)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(distribute)
