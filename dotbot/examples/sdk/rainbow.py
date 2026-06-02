"""A rolling colour show across the fleet (no motion).

python rainbow.py [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.sdk import Swarm

PALETTE = ["red", "yellow", "green", "cyan", "blue", "magenta"]


async def rainbow(swarm: Swarm) -> None:
    bots = sorted(swarm, key=lambda b: b.address)
    print(f"colour show on {len(bots)} bots ...")
    for shift in range(len(PALETTE) * 3):
        for i, bot in enumerate(bots):
            bot.set_color(PALETTE[(i + shift) % len(PALETTE)])
        await asyncio.sleep(0.4)
    swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(rainbow)
