"""The fleet forms a square - one bot per corner.

python square_formation.py [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.swarm import Swarm

CENTER_X, CENTER_Y = 1000, 1000
HALF = 500  # half the side length, in mm


async def square_formation(swarm: Swarm) -> None:
    bots = sorted(swarm, key=lambda b: b.address)
    corners = [
        (CENTER_X - HALF, CENTER_Y - HALF),
        (CENTER_X + HALF, CENTER_Y - HALF),
        (CENTER_X + HALF, CENTER_Y + HALF),
        (CENTER_X - HALF, CENTER_Y + HALF),
    ]
    swarm.all.set_color("cyan")
    print(f"{len(bots)} bots forming a square ...")
    await asyncio.gather(*(bot.move_to(x, y) for bot, (x, y) in zip(bots, corners)))
    print("square formed")


if __name__ == "__main__":
    Swarm.run(square_formation)
