"""sdk_demo.py - a short guided tour of the DotBot Swarm SDK.

A quick way to see the SDK in action against the simulator. It connects, colours
the whole fleet, prints live events as they happen, then drives two bots to
opposite corners concurrently and waits for both to arrive.

Run a simulator/controller on :8000 first, then run this. If you started the
simulator with its web UI, open http://localhost:8000 to watch the bots move on
the map while this script drives them.

    python sdk_demo.py [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.sdk import ModeChanged, Swarm


async def demo(swarm: Swarm) -> None:
    await asyncio.sleep(1.0)  # let the first round of state arrive
    bots = sorted(swarm, key=lambda b: b.address)
    print(f"connected to {len(bots)} bot(s):")
    for bot in bots:
        print("   ", bot)
    if len(bots) < 2:
        print("need at least 2 bots for the drive part; colouring only")

    # 1) one call colours the whole fleet (swarm.all is the broadcast/fleet handle)
    swarm.all.set_color("cyan")

    # 2) print mode changes as discrete events while we drive
    async def watch_events() -> None:
        async for event in swarm.events():
            if isinstance(event, ModeChanged):
                print(f"    event: {event.address[:8]} -> {event.mode.name}")

    watcher = asyncio.create_task(watch_events())

    # 3) drive two bots to opposite corners, concurrently, and wait for arrival
    if len(bots) >= 2:
        blue, red = bots[0], bots[1]
        blue.set_color("blue")
        red.set_color("red")
        print(
            f"driving {blue.address[:8]} -> (300, 300)  and  {red.address[:8]} -> (1700, 1700) ..."
        )
        await asyncio.gather(blue.move_to(300, 300), red.move_to(1700, 1700))
        print("both arrived:")
        print("   ", blue)
        print("   ", red)

    watcher.cancel()


if __name__ == "__main__":
    Swarm.run(demo)
