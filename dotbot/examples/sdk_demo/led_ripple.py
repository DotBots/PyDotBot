# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""A ring of colour that ripples out from the centre of the swarm.

Pure LED, no motion - collision-free and the safest demo to run on the real
testbed. Bots are bucketed into concentric rings by distance from the live
swarm centroid, then a single bright ring travels outward over a dark field,
over and over, shifting hue each pass.

Only the two rings that change each step are re-sent, so the fleet is never
re-coloured all at once (kind to the downlink budget on real hardware).

Set OUTWARD = False to ripple inward instead (edge first, then inner rings).

    python -m dotbot.examples.sdk_demo.led_ripple [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import centroid, hsv, make_rings, settle
from dotbot.swarm import Swarm

N_RINGS = 7
STEP_DELAY = 0.18  # seconds between successive rings (the wave speed)
CYCLE_PAUSE = 0.5  # seconds of dark between waves
HUE_SHIFT = 0.15  # colour advance per pass
OUTWARD = True  # True: centre -> edge; False: edge -> centre


async def led_ripple(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    rings = make_rings(bots, centroid(bots), N_RINGS)
    if not OUTWARD:
        rings = list(reversed(rings))

    print(f"rippling a ring of light through {N_RINGS} rings ... (Ctrl-C to stop)")
    hue = 0.0
    try:
        while True:
            prev = None
            for ring in rings:
                color = hsv(hue)
                for b in ring:
                    b.set_color(color)
                if prev is not None:
                    for b in prev:
                        b.set_color("off")
                prev = ring
                await asyncio.sleep(STEP_DELAY)
            for b in prev:  # extinguish the last ring before the next wave
                b.set_color("off")
            hue = (hue + HUE_SHIFT) % 1.0
            await asyncio.sleep(CYCLE_PAUSE)
    finally:
        swarm.all.set_color("off")


if __name__ == "__main__":
    Swarm.run(led_ripple)
