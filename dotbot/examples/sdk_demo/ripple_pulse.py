# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""A ripple that travels out from the centre of the swarm in BOTH light and
motion - the moving cousin of led_ripple.

As the wave reaches each ring (centre -> edge), those bots flash a colour and
hop a little outward; once it reaches the rim the whole fleet eases back home
and dims, then the ripple repeats with the next hue. The outward hop gives the
"drop in a pond" read that the colour-only led_ripple only hints at.

Collision note: each bot hops ~NUDGE mm outward and returns to its exact start,
so net motion is zero - but keep NUDGE well under your inter-bot spacing on real
hardware (it is collision-free in the simulator). Motion uses fire-and-forget
waypoints, so a radial hop turns the bot toward the target before easing out.

    python -m dotbot.examples.sdk_demo.ripple_pulse [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.examples.sdk_demo._lib import centroid, hsv, make_rings, settle
from dotbot.sdk import Swarm

N_RINGS = 7
NUDGE = 160  # mm each bot hops outward as the wave passes (keep < spacing)
ARRIVE = 50  # mm arrival threshold for the hop (tighter = more visible travel)
STEP_DELAY = 0.28  # s between rings (the wave speed)
HOLD = 1.3  # s to let the outward hop become visible before recall
RETURN = 1.8  # s to let bots ease back home
CYCLE_PAUSE = 0.4  # s between ripples
HUE_STEP = 0.13  # colour advance per ripple


def _outward(pos, center) -> tuple:
    """Unit vector pointing from the swarm centre out through `pos`."""
    dx, dy = pos.x - center.x, pos.y - center.y
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1.0 else (0.0, 0.0)


async def ripple_pulse(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    center = centroid(bots)
    home = {b.address: b.position for b in bots}
    out = {b.address: _outward(home[b.address], center) for b in bots}
    rings = make_rings(bots, center, N_RINGS)

    print(f"rippling light + motion through {N_RINGS} rings ... (Ctrl-C to stop)")
    hue = 0.0
    try:
        while True:
            # wave travels centre -> edge: each ring flashes and hops outward
            for ring in rings:
                color = hsv(hue)
                for b in ring:
                    b.set_color(color)
                    ox, oy = out[b.address]
                    b.goto(
                        home[b.address].x + ox * NUDGE,
                        home[b.address].y + oy * NUDGE,
                        threshold=ARRIVE,
                    )
                await asyncio.sleep(STEP_DELAY)
            await asyncio.sleep(HOLD)
            # the whole fleet eases back home and dims
            for b in bots:
                b.goto(home[b.address].x, home[b.address].y, threshold=ARRIVE)
                b.set_color("off")
            await asyncio.sleep(RETURN)
            hue = (hue + HUE_STEP) % 1.0
            await asyncio.sleep(CYCLE_PAUSE)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")


if __name__ == "__main__":
    Swarm.run(ripple_pulse)
