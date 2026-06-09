# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Re-arrange a clustered swarm into an even distribution across the arena.

The algorithm: lay down N evenly spaced target points over the arena, assign
each bot to the nearest still-free target (greedy - keeps total travel short and
avoids long crossing paths), then drive everyone to their target at once. A
clustered fleet fans out into a tidy, lightly jittered lattice.

With --loop it gathers the fleet into a random cluster and then re-distributes,
over and over, so you can watch the rearrangement from different starting clumps.

Set MAP_SIZE to match the controller's arena, i.e. the `-m <S>x<S>` you launched
it with (default 2500).

    python -m dotbot.examples.sdk_demo.distribute [--loop] [--swarm-url http://localhost:8000]
"""

import argparse
import asyncio
import math
import random

from dotbot.examples.sdk_demo._lib import settle
from dotbot.sdk import Swarm

MAP_SIZE = 2500  # arena side in mm; match `dotbot run controller ... -m <S>x<S>`
MARGIN = 250  # keep targets this far from the walls
JITTER_MM = 40  # randomise targets a touch so the lattice looks organic
CLUSTER_SPREAD = 250  # mm radius of the random clump in --loop mode
SETTLE = 2.5  # s to hold each arrangement
DRIVE_SECS = 14.0  # s spent driving to each arrangement
DRIVE_TICK = 1.0  # s between target re-asserts (67 bots -> ~67 cmd/s, in budget)


def _clamp(p: tuple) -> tuple:
    x, y = p
    lo, hi = MARGIN, MAP_SIZE - MARGIN
    return (min(max(x, lo), hi), min(max(y, lo), hi))


def even_targets(n: int) -> list:
    """n points on an even, lightly jittered lattice filling the arena."""
    lo, hi = MARGIN, MAP_SIZE - MARGIN
    span = hi - lo
    rows = max(1, round(math.sqrt(n)))
    pts = []
    for r in range(rows):
        in_row = n // rows + (1 if r < n % rows else 0)
        y = lo + (r + 0.5) * span / rows
        for c in range(in_row):
            x = lo + (c + 0.5) * span / in_row
            pts.append(
                _clamp(
                    (
                        x + random.uniform(-JITTER_MM, JITTER_MM),
                        y + random.uniform(-JITTER_MM, JITTER_MM),
                    )
                )
            )
    return pts


def assign(bots: list, targets: list) -> dict:
    """Greedy nearest assignment: pair up the closest free (bot, target) first,
    which keeps total travel short and long crossing paths rare."""
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
    return out


async def _drive_all(bots: list, target_of: dict) -> None:
    """Keep asserting each bot's target for DRIVE_SECS, re-sending it every tick.
    A dropped command is simply retried next tick - robust under load - and the
    demo never hangs waiting on a straggler to report arrival."""
    loop = asyncio.get_running_loop()
    end = loop.time() + DRIVE_SECS
    while loop.time() < end:
        for b in bots:
            target = target_of.get(b.address)
            if target is not None:
                b.goto(*target)
        await asyncio.sleep(DRIVE_TICK)


async def distribute(swarm: Swarm) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--loop", action="store_true", help="cluster then re-distribute, repeatedly"
    )
    opts, _ = parser.parse_known_args()

    bots = await settle(swarm)
    if not bots:
        return

    try:
        while True:
            print("distributing ...")
            swarm.all.set_color("green")
            await _drive_all(bots, assign(bots, even_targets(len(bots))))
            await asyncio.sleep(SETTLE)
            if not opts.loop:
                break
            print("clustering ...")
            swarm.all.set_color("red")
            cx = random.uniform(MARGIN, MAP_SIZE - MARGIN)
            cy = random.uniform(MARGIN, MAP_SIZE - MARGIN)
            clump = {
                b.address: _clamp(
                    (
                        cx + random.uniform(-CLUSTER_SPREAD, CLUSTER_SPREAD),
                        cy + random.uniform(-CLUSTER_SPREAD, CLUSTER_SPREAD),
                    )
                )
                for b in bots
            }
            await _drive_all(bots, clump)
            await asyncio.sleep(SETTLE)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(distribute)
