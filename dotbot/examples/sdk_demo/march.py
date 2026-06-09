# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The whole swarm marches together - right, up, left, down - back to start.

Every bot gets the same offset from its own home, so the formation translates
as a rigid block and relative spacing is preserved. Targets are taken from each
bot's home snapshot (not its live position), so the path closes exactly instead
of drifting. Watch the arena edges: keep STEP small enough that the outermost
bots do not run into a wall.

    python -m dotbot.examples.sdk_demo.march [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import settle
from dotbot.sdk import Swarm

STEP = 250  # mm per leg

# Offsets from home, in order: right, up, left, back to start.
LEGS = [(STEP, 0), (STEP, STEP), (0, STEP), (0, 0)]


async def march(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    home = {b.address: b.position for b in bots}
    print(f"marching {len(bots)} bots as one block ...")
    swarm.all.set_color("yellow")
    try:
        for ox, oy in LEGS:
            await asyncio.gather(
                *(
                    b.move_to(home[b.address].x + ox, home[b.address].y + oy)
                    for b in bots
                )
            )
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(march)
