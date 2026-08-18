"""One DotBot shuttles between two points, changing colour each leg.

python shuttle.py [--swarm-url http://localhost:8000]
"""

from dotbot.swarm import Swarm

LEFT = (400, 1000)
RIGHT = (1600, 1000)
COLORS = ["red", "green", "blue", "yellow"]


async def shuttle(swarm: Swarm) -> None:
    bot = sorted(swarm, key=lambda b: b.address)[0]
    print(f"{bot.address[:8]} shuttling back and forth ...")
    for i, color in enumerate(COLORS):
        bot.set_color(color)
        await bot.move_to(*(RIGHT if i % 2 == 0 else LEFT))
    print("done")


if __name__ == "__main__":
    Swarm.run(shuttle)
