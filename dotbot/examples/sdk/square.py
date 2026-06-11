"""One DotBot walks a square.

python square.py [--swarm-url http://localhost:8000]
"""

from dotbot.swarm import Swarm

CENTER_X, CENTER_Y = 1000, 1000
HALF = 400  # half the side length, in mm


async def walk_square(swarm: Swarm) -> None:
    bot = sorted(swarm, key=lambda b: b.address)[0]
    bot.set_color("blue")
    corners = [
        (CENTER_X - HALF, CENTER_Y - HALF),
        (CENTER_X + HALF, CENTER_Y - HALF),
        (CENTER_X + HALF, CENTER_Y + HALF),
        (CENTER_X - HALF, CENTER_Y + HALF),
        (CENTER_X - HALF, CENTER_Y - HALF),  # close the loop
    ]
    print(f"{bot.address[:8]} walking a square ...")
    await bot.follow(corners)
    print("done")


if __name__ == "__main__":
    Swarm.run(walk_square)
