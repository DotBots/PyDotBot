"""labyrinth_sdk.py - the labyrinth example rewritten on the Swarm SDK.

Same behaviour as labyrinth.py (two robots navigate the maze), but the REST
polling, the ws client, the <=12 waypoint chunking, the resend-until-AUTO and
poll-until-arrival loops, and the pydantic message towers are all absorbed by
`Bot.follow`. Run a controller/simulator on :8000, then:

    python labyrinth_sdk.py [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.swarm import Swarm

ROBOT1_WAYPOINTS = [
    (200, 680),
    (200, 1600),
    (1000, 1600),
    (1300, 1400),
    (1000, 1100),
    (1300, 750),
    (1300, 500),
    (600, 500),
]
ROBOT2_WAYPOINTS = [
    (1800, 1700),
    (1300, 1700),
    (300, 1700),
    (300, 900),
    (600, 900),
    (600, 1200),
    (200, 1200),
    (200, 1650),
    (1300, 1650),
    (1300, 400),
    (900, 200),
    (600, 200),
]


async def labyrinth(swarm: Swarm) -> None:
    bots = sorted(swarm, key=lambda b: b.address)[:2]
    if len(bots) < 2:
        print(f"need 2 active DotBots, found {len(bots)}")
        return
    blue, red = bots
    print(f"blue={blue.address}  red={red.address}")
    blue.set_color("blue")
    red.set_color("red")
    await asyncio.gather(
        blue.follow(ROBOT1_WAYPOINTS),
        red.follow(ROBOT2_WAYPOINTS),
    )
    print("both robots reached their targets")


if __name__ == "__main__":
    Swarm.run(labyrinth)
