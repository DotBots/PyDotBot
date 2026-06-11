# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The whole swarm marches together - right, up, left, down - back to start.

Every bot gets the same offset from its own home, so the formation translates
as a rigid block and relative spacing is preserved. Targets are taken from each
bot's home snapshot (not its live position), so the path closes exactly instead
of drifting. The step is shrunk automatically if the outermost bots would hit a
wall, and each leg is driven through the shared BVC drive() helper so a bot
that lags a leg never gets run over by a neighbour starting the next one.

    python -m dotbot.examples.sdk_demo.march [--swarm-url http://localhost:8000]
"""

from dotbot.examples.sdk_demo._lib import WALL_MARGIN, drive, settle
from dotbot.swarm import Swarm

STEP = 250  # mm per leg (shrunk automatically to fit the arena)

# Offsets from home, in order: right, up, left, back to start.
LEGS = [(1, 0), (1, 1), (0, 1), (0, 0)]


async def march(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return
    w, h = await swarm.map_size()
    home = {b.address: b.position for b in bots}

    # The block shifts right then up by STEP: shrink STEP if the bots nearest
    # the right/top walls would be pushed past the margin.
    room_x = min(w - WALL_MARGIN - p.x for p in home.values())
    room_y = min(h - WALL_MARGIN - p.y for p in home.values())
    step = max(0.0, min(STEP, room_x, room_y))
    if step < STEP:
        print(f"shrinking step to {step:.0f} mm to stay inside the arena")
    if step < 50:
        print("no room to march; aborting")
        return

    print(f"marching {len(bots)} bots as one block ...")
    swarm.all.set_color("yellow")
    try:
        for ox, oy in LEGS:
            goals = {a: (p.x + ox * step, p.y + oy * step) for a, p in home.items()}
            await drive(bots, goals, (w, h), timeout=30.0)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(march)
