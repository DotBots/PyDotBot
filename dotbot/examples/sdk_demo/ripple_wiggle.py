# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""A wiggle that ripples out from the centre of the swarm, ring by ring.

Like `wiggle`, every bot only rocks in place - it rotates back and forth and
never leaves its spot, so this is collision-safe on real hardware. But the
motion is localised by position: the centre ring wiggles first, then the next
ring out, then the next, so a wave of wiggling travels from the middle to the
edge. Each ring lights up as it wiggles, building an expanding rainbow; at the
rim the fleet fades and the wave repeats from the centre.

One sweep takes about N_RINGS * BEATS_PER_RING * BEAT seconds (~10 s by default).

    python -m dotbot.examples.sdk_demo.ripple_wiggle [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import centroid, hsv, make_rings, settle
from dotbot.sdk import Swarm

N_RINGS = 7
SPEED = 70  # wheel PWM magnitude of each twist, 0..100
BEATS_PER_RING = 4  # twists a ring does while the wave dwells on it
BEAT = 0.35  # seconds per twist
RING_HUE_STEP = 0.13  # colour shift from one ring to the next
CYCLE_PAUSE = 0.8  # seconds of stillness between sweeps


async def _wiggle_ring(ring: list, color: tuple) -> None:
    """Light a ring and rock it in place for BEATS_PER_RING twists, then stop -
    the bots rotate back and forth without leaving their spot."""
    for bot in ring:
        bot.set_color(color)
    direction = 1
    for _ in range(BEATS_PER_RING):
        for bot in ring:
            bot.move_raw(left=(0, direction * SPEED), right=(0, -direction * SPEED))
        direction = -direction
        await asyncio.sleep(BEAT)
    for bot in ring:
        bot.stop()


async def ripple_wiggle(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    rings = [r for r in make_rings(bots, centroid(bots), N_RINGS) if r]

    print(f"wiggling outward through {len(rings)} rings ... (Ctrl-C to stop)")
    base = 0.0
    try:
        while True:
            hue = base
            for ring in rings:  # centre -> edge: one ring wiggles at a time
                await _wiggle_ring(ring, hsv(hue))
                hue += RING_HUE_STEP
            await asyncio.sleep(CYCLE_PAUSE)
            swarm.all.set_color("off")
            base = (base + 0.07) % 1.0
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")


if __name__ == "__main__":
    Swarm.run(ripple_wiggle)
