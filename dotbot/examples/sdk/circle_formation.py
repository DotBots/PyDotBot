"""The fleet spreads out evenly onto a circle.

python circle_formation.py [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.swarm import Swarm

CENTER_X, CENTER_Y = 1000, 1000
RADIUS = 600  # mm


async def circle_formation(swarm: Swarm) -> None:
    bots = sorted(swarm, key=lambda b: b.address)
    n = len(bots)
    targets = [
        (
            CENTER_X + RADIUS * math.cos(2 * math.pi * i / n),
            CENTER_Y + RADIUS * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]
    swarm.all.set_color("magenta")
    print(f"{n} bots forming a circle ...")
    await asyncio.gather(*(bot.move_to(x, y) for bot, (x, y) in zip(bots, targets)))
    print("circle formed")


if __name__ == "__main__":
    Swarm.run(circle_formation)
