"""A background app: low bots leave for a corner pad, charge, and come back.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground. It draws its pads and badges whether
or not it is the selected app, and takes no input from the map, so it runs
beside another demo.

On the simulator the battery only falls: `battery_discharge_model` in
`dotbot/dotbot_simulator.py` is a straight line from 3000 mV over three hours
and nothing raises it. A bot on a pad is therefore released on a timer rather
than on a voltage, and its charge is what this script believes rather than
what the fleet reports.
"""

from __future__ import annotations

import asyncio
import time

from dotbot.examples.common.playground import (
    Announcement,
    Bot,
    PlaygroundApp,
    Point,
    demo_command,
    overlay_badge,
    overlay_point,
    serve,
    slider,
)

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 90

#: How far from a corner each pad sits, mm.
PAD_INSET_MM = 350

#: Radius of a pad, mm. A bot within it counts as docked.
PAD_RADIUS_MM = 180

#: A bot released from a pad is left alone for this long, so it clears the
#: pad before anything can send it back to one.
COOLDOWN_S = 20.0

ANNOUNCEMENT = Announcement(
    name="charging",
    title="Charging cycle",
    hint="Background app: the corner pads, the battery threshold and the queue.",
    inputs=[],
    controls=[
        slider(
            "threshold",
            2000,
            3000,
            2960,
            step=10,
            label="Send to a pad below",
            unit="mV",
        ),
        slider("charge", 5, 120, 20, step=5, label="Time on the pad", unit="s"),
    ],
    overlay=True,
)


def pads(arena: tuple[float, float], inset: float = PAD_INSET_MM) -> list[Point]:
    """One pad per corner of the arena."""
    return [
        Point(inset, inset),
        Point(arena[0] - inset, inset),
        Point(inset, arena[1] - inset),
        Point(arena[0] - inset, arena[1] - inset),
    ]


def nearest_free(bot: Bot, free: list[int], places: list[Point]) -> int | None:
    """The closest unclaimed pad, or None when every pad is taken."""
    if not free:
        return None
    return min(
        free, key=lambda i: (places[i].x - bot.x) ** 2 + (places[i].y - bot.y) ** 2
    )


def docked(bot: Bot, pad: Point, radius: float = PAD_RADIUS_MM) -> bool:
    return (bot.x - pad.x) ** 2 + (bot.y - pad.y) ** 2 <= radius * radius


class Cycle:
    """Which bot holds which pad, and since when."""

    def __init__(self) -> None:
        #: address -> pad index
        self.holding: dict[str, int] = {}
        #: address -> when it docked, or None while it is still driving there
        self.since: dict[str, float | None] = {}
        #: address -> when it was released
        self.released: dict[str, float] = {}

    def free_pads(self, count: int) -> list[int]:
        taken = set(self.holding.values())
        return [i for i in range(count) if i not in taken]

    def release(self, address: str) -> None:
        self.holding.pop(address, None)
        self.since.pop(address, None)
        self.released[address] = time.monotonic()

    def resting(self, address: str, now: float) -> bool:
        return now - self.released.get(address, -COOLDOWN_S) < COOLDOWN_S


async def drive(app: PlaygroundApp, period: float = 0.5) -> None:
    """The loop: claim a pad for every low bot, hold it, then let it go."""
    cycle = Cycle()
    while True:
        await asyncio.sleep(period)
        bots = list(app.bots.values())
        arena = app.controller.map_size
        places = pads(arena)
        threshold_v = float(app.values.get("threshold", 2960)) / 1000.0
        charge_s = float(app.values.get("charge", 20))
        now = time.monotonic()

        for bot in bots:
            pad_index = cycle.holding.get(bot.address)
            if pad_index is None:
                if bot.battery >= threshold_v or cycle.resting(bot.address, now):
                    continue
                pad_index = nearest_free(bot, cycle.free_pads(len(places)), places)
                if pad_index is None:
                    continue
                cycle.holding[bot.address] = pad_index
                cycle.since[bot.address] = None

            pad = places[pad_index]
            arrived = cycle.since.get(bot.address)
            if arrived is None:
                app.controller.waypoints(bot.address, [pad], threshold=ARRIVE_MM)
                if docked(bot, pad):
                    cycle.since[bot.address] = now
            elif now - arrived >= charge_s:
                cycle.release(bot.address)

        # A bot that vanished from the fleet must not hold a pad forever.
        for address in list(cycle.holding):
            if address not in app.bots:
                cycle.release(address)

        charging = [b for b in bots if b.address in cycle.holding]
        overlay = [
            overlay_point(p.x, p.y, r=PAD_RADIUS_MM, label="pad", color="good")
            for p in places
        ]
        overlay += [
            overlay_badge(
                b.address,
                "charging" if cycle.since.get(b.address) else "to a pad",
                color="good" if cycle.since.get(b.address) else "warn",
            )
            for b in charging
        ]
        app.publish_overlay(overlay)
        low = sum(1 for b in bots if b.battery < threshold_v)
        app.publish_status(
            f"{len(charging)} on pads, {low} of {len(bots)} below "
            f"{threshold_v * 1000:.0f} mV"
        )


@demo_command
def cli(broker: str, controller: str, rate: float) -> None:
    """Send low bots to a charging pad and release them when they are full."""
    serve(
        ANNOUNCEMENT,
        lambda app: drive(app, period=1.0 / max(0.1, rate)),
        broker=broker,
        controller=controller,
        rate=rate,
    )


if __name__ == "__main__":
    cli()
