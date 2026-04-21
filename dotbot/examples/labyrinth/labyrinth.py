"""
labyrinth.py
============
Two-robot labyrinth navigation example for DotBot.

Robot 1 (blue) starts in the top-left pocket and Robot 2 (red) starts in
the top-right pocket. Both navigate through the maze to the middle-top
region, exploring dead ends along the way, and settle at different targets.

Usage
-----
    python labyrinth.py [--host HOST] [--port PORT]

The dotbot-controller must be running with the labyrinth map::

    dotbot-controller -p dotbot-simulator \\
        --simulator-init-state dotbot/examples/labyrinth/init_simulator_state.toml \\
        --background-map dotbot/examples/labyrinth/labyrinth-2000x2000.png
"""

import asyncio

import click

from dotbot.models import (
    DotBotLH2Position,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.rest import rest_client
from dotbot.websocket import DotBotWsClient

WAYPOINT_THRESHOLD = 100  # mm — proximity to consider a waypoint reached
MAX_WAYPOINTS = 12  # hardware limit per waypoint batch

# Robot 1 (blue): exits the top-left dead end, routes around wall D in the
# lower area, crosses to the right of wall C, then goes north through the
# gap (x=1150–1500) into the top corridor and explores the dead end.
ROBOT1_WAYPOINTS = [
    (200, 680),  # explore toward bottom of left pocket (wall A ends at y=750)
    (1000, 1600),  # go south past wall D (y=1400–1450)
    (1300, 1400),  # go east past wall C bottom (wall C ends at y=1450)
    (1000, 1000),  # go north through the gap into the top corridor
    (1300, 750),  # explore the middle-right dead end (wall C ends at y=750)
    (1300, 500),  # explore the top-right dead end (wall E ends at y=600)
    (600, 500),  # final target (blue disk)
]

# Robot 2 (red): exits the top-right dead end by navigating all the way south
# (wall F ends at y=1600), crosses left through the main area, then goes north
# through the same gap into the top corridor and explores.
ROBOT2_WAYPOINTS = [
    (1800, 1700),  # exit top-right pocket below wall F (y=1600)
    (1300, 1700),  # navigate west past wall E/F
    (300, 1700),  # explore the top-left dead end (wall A ends at y=750)
    (300, 900),  # explore the left pocket
    (600, 900),  # explore the middle-left dead end (wall B ends at x=700)
    (600, 1200),  # explore the bottom-middle dead end (wall D ends at y=1400–1450)
    (200, 1200),  # explore the bottom-left dead end
    (200, 1650),  # explore the bottom-left corner
    (1300, 1650),  # explore the bottom-right corner
    (1300, 400),  # go north through the gap into the top corridor
    (900, 200),  # explore the top-middle dead end
    (600, 200),  # final target (red disk)
]

ROBOT1_COLOR = (0, 0, 255)
ROBOT2_COLOR = (255, 0, 0)


async def _wait_for_auto_mode(
    ws: DotBotWsClient,
    address: str,
    chunk: list[tuple[int, int]],
    host: str,
    port: int,
) -> None:
    async with rest_client(host, port, False) as client:
        while True:
            await ws.send(
                WSWaypoints(
                    cmd="waypoints",
                    address=address,
                    application=ApplicationType.DotBot,
                    data=DotBotWaypoints(
                        threshold=WAYPOINT_THRESHOLD,
                        waypoints=[DotBotLH2Position(x=x, y=y) for x, y in chunk],
                    ),
                )
            )
            await asyncio.sleep(0.1)
            bots = await client.fetch_dotbots(query=DotBotQueryModel(address=address))
            if bots and bots[0].mode == ControlModeType.AUTO:
                break


async def _wait_for_completion(address: str, host: str, port: int) -> None:
    async with rest_client(host, port, False) as client:
        while True:
            bots = await client.fetch_dotbots(query=DotBotQueryModel(address=address))
            if bots:
                bot = bots[0]
                if not bot.waypoints or bot.mode == ControlModeType.MANUAL:
                    break
            await asyncio.sleep(0.5)


async def navigate_robot(
    address: str,
    color: tuple[int, int, int],
    waypoints: list[tuple[int, int]],
    host: str,
    port: int,
) -> None:
    ws = DotBotWsClient(host, port)
    await ws.connect()
    try:
        await ws.send(
            WSRgbLed(
                cmd="rgb_led",
                address=address,
                application=ApplicationType.DotBot,
                data=DotBotRgbLedCommandModel(
                    red=color[0], green=color[1], blue=color[2]
                ),
            )
        )
        chunks = [
            waypoints[i : i + MAX_WAYPOINTS]
            for i in range(0, len(waypoints), MAX_WAYPOINTS)
        ]
        for chunk in chunks:
            await _wait_for_auto_mode(ws, address, chunk, host, port)
            await _wait_for_completion(address, host, port)
    finally:
        await ws.close()


async def main_async(host: str, port: int) -> None:
    async with rest_client(host, port, False) as client:
        dotbots = await client.fetch_dotbots(
            query=DotBotQueryModel(status=DotBotStatus.ACTIVE)
        )

    if len(dotbots) < 2:
        print(f"Need at least 2 active DotBots, found {len(dotbots)}")
        return

    dotbots = sorted(dotbots, key=lambda b: b.address)[:2]
    await asyncio.gather(
        navigate_robot(dotbots[0].address, ROBOT1_COLOR, ROBOT1_WAYPOINTS, host, port),
        navigate_robot(dotbots[1].address, ROBOT2_COLOR, ROBOT2_WAYPOINTS, host, port),
    )


@click.command()
@click.option(
    "--host",
    default="localhost",
    show_default=True,
    help="Controller host.",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    help="Controller port.",
)
def main(host: str, port: int) -> None:
    """Two-robot labyrinth navigation example."""
    asyncio.run(main_async(host, port))


if __name__ == "__main__":
    main()
