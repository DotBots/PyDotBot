# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Spread the swarm out by mutual repulsion - bots push apart, not through each
other.

Each round, every bot wants a small step directly *away* from whoever is
crowding it (near bots weigh most), and the step shrinks each round so the
fleet settles into an even spread. Every step is issued through the buffered
Voronoi cell projection from _lib, so even bots that start overlapping (or get
boxed in mid-bloom) separate cleanly instead of arcing through a neighbour -
the repulsion field picks the direction, the BVC guarantees the safety.

It works from any start - a tight clump blooms outward, an already-spread fleet
just evens out its spacing - and reads the arena size from the controller, so
it matches whatever `-m <W>x<H>` you launched with. With --loop it re-gathers
the fleet into a tight (but touch-free) block and disperses again.

    python -m dotbot.examples.sdk_demo.disperse [--loop] [--swarm-url http://localhost:8000]
"""

import argparse
import asyncio
import math

from dotbot.examples.sdk_demo._lib import drive, hop_goto, pace_tick, safe_hop, settle
from dotbot.swarm import Swarm

ROUNDS = 22  # repulsion iterations
STEP0 = 160  # mm: desired step on the first round (anneals to ~0)
TICK = 1.0  # s per round (paces the ~2 Hz position refresh and the link budget)
GATHER_PITCH = 380  # mm grid pitch of the --loop re-gather block


def _repulsion(me: str, positions: dict, step: float) -> tuple:
    """Where `me` wants to go this round: `step` mm away from the net 1/d^2
    pull of its neighbours (near bots dominate)."""
    px, py = positions[me]
    fx = fy = 0.0
    for other, (qx, qy) in positions.items():
        if other == me:
            continue
        dx, dy = px - qx, py - qy
        d2 = max(dx * dx + dy * dy, 1.0)
        fx += dx / d2
        fy += dy / d2
    mag = math.hypot(fx, fy)
    if mag < 1e-9:
        return (px, py)
    return (px + fx / mag * step, py + fy / mag * step)


async def _disperse(bots: list, arena: tuple) -> None:
    for r in range(ROUNDS):
        step = STEP0 * (1 - r / ROUNDS)  # anneal so the fleet settles
        positions = {b.address: (b.position.x, b.position.y) for b in bots if b.position}
        for b in bots:
            if b.address not in positions:
                continue
            want = _repulsion(b.address, positions, step)
            px, py = positions[b.address]
            hop_goto(b, safe_hop(b, positions, want, arena), px, py)
        await asyncio.sleep(pace_tick(len(bots), TICK))


async def disperse(swarm: Swarm) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--loop", action="store_true", help="re-gather then disperse again"
    )
    opts, _ = parser.parse_known_args()

    bots = await settle(swarm)
    if not bots:
        return
    w, h = await swarm.map_size()
    print(f"arena {w}x{h} mm; dispersing {len(bots)} bots ...")

    try:
        while True:
            swarm.all.set_color("cyan")
            await _disperse(bots, (w, h))
            await asyncio.sleep(1.5)
            if not opts.loop:
                break
            print("re-gathering to the centre ...")
            swarm.all.set_color("red")
            cols = max(1, round(math.sqrt(len(bots))))
            goals = {
                b.address: (
                    w / 2 + (k % cols - (cols - 1) / 2) * GATHER_PITCH,
                    h / 2 + (k // cols - (cols - 1) / 2) * GATHER_PITCH,
                )
                for k, b in enumerate(bots)
            }
            await drive(bots, goals, (w, h))
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(disperse)
