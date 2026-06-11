"""The fleet "breathes" - expanding and contracting on a ring.

python pulse.py [--swarm-url http://localhost:8000]
"""

import asyncio
import math

from dotbot.swarm import Swarm

CENTER_X, CENTER_Y = 1000, 1000


async def pulse(swarm: Swarm) -> None:
    bots = sorted(swarm, key=lambda b: b.address)
    n = len(bots)

    def ring(radius: float):
        return [
            (
                CENTER_X + radius * math.cos(2 * math.pi * i / n),
                CENTER_Y + radius * math.sin(2 * math.pi * i / n),
            )
            for i in range(n)
        ]

    swarm.all.set_color("cyan")
    print(f"{n} bots breathing ...")
    for radius in (700, 250, 700, 250):
        targets = ring(radius)
        await asyncio.gather(*(bot.move_to(x, y) for bot, (x, y) in zip(bots, targets)))
    print("done")


if __name__ == "__main__":
    Swarm.run(pulse)
