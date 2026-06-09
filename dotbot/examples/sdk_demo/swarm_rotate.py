# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The whole swarm rotates as one rigid formation about its centroid.

The showpiece - and the highest collision risk on real hardware: outer bots
sweep through a lot of space and cross inner bots' paths. Test in the simulator
first; on real hardware use a small TOTAL_ANGLE and/or a sparse field. The turn
is done in small incremental steps so it reads as one smooth rotation, and each
bot is coloured by its bearing so the rotating "spokes" are easy to see.

    python -m dotbot.examples.sdk_demo.swarm_rotate [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import angle_deg, centroid, hsv, rotate, settle
from dotbot.sdk import Swarm

TOTAL_ANGLE = 90  # degrees to rotate the whole formation
STEPS = 6  # number of incremental sub-rotations


async def swarm_rotate(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    center = centroid(bots)
    home = {b.address: b.position for b in bots}

    for b in bots:  # colour by bearing so the rotation is legible
        b.set_color(hsv((angle_deg(b, center) % 360) / 360))

    print(f"rotating {len(bots)} bots {TOTAL_ANGLE} deg about the centroid ...")
    try:
        for s in range(1, STEPS + 1):
            angle = TOTAL_ANGLE * s / STEPS
            targets = {a: rotate(p, center, angle) for a, p in home.items()}
            await asyncio.gather(
                *(
                    b.move_to(targets[b.address].x, targets[b.address].y)
                    for b in bots
                )
            )
    finally:
        swarm.all.stop()
    print("done")


if __name__ == "__main__":
    Swarm.run(swarm_rotate)
