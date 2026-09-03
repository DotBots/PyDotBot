"""The swarm splits across the pins on the map and rings each one.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Goals in the rail. Click to
set a pin, shift-click to add more.
"""

from __future__ import annotations

import asyncio
from typing import List, Sequence, Tuple

import numpy as np

from dotbot.examples.common.playground import (
    Announcement,
    PlaygroundApp,
    Point,
    assign_targets,
    demo_command,
    overlay_point,
    serve,
    slider,
)
from dotbot.examples.common.raster import clamp_to_arena, ring_points

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 90

ANNOUNCEMENT = Announcement(
    name="goals",
    title="Goals",
    hint="Click to set a pin, shift-click for more. Each group rings its pin.",
    inputs=["goals"],
    controls=[slider("radius", 100, 900, 320, step=20, label="Ring radius", unit="mm")],
    overlay=True,
)


def split_by_proximity(bots: np.ndarray, pins: np.ndarray) -> np.ndarray:
    """The pin each bot belongs to: the nearest one, by squared distance."""
    if len(bots) == 0 or len(pins) == 0:
        return np.zeros(len(bots), dtype=int)
    cost = ((bots[:, None, :] - pins[None, :, :]) ** 2).sum(axis=2)
    return cost.argmin(axis=1)


def ring_targets(
    bots: np.ndarray,
    pins: np.ndarray,
    radius: float,
    arena: Tuple[float, float],
) -> np.ndarray:
    """
    A target per bot: its group's ring around its pin, assigned within the
    group. A ring of one bot is the pin itself.
    """
    groups = split_by_proximity(bots, pins)
    targets = np.zeros_like(bots)
    for pin in range(len(pins)):
        members = np.flatnonzero(groups == pin)
        if len(members) == 0:
            continue
        if len(members) == 1:
            targets[members[0]] = pins[pin]
            continue
        slots = clamp_to_arena(
            ring_points(tuple(pins[pin]), len(members), radius), arena
        )
        order = assign_targets(bots[members], slots)
        targets[members] = slots[order]
    return targets


def as_array(points: Sequence[Point]) -> np.ndarray:
    return np.array([[p.x, p.y] for p in points], dtype=float).reshape(-1, 2)


async def drive(app: PlaygroundApp, period: float = 0.5) -> None:
    """The loop: split the swarm across the pins, ring each group, hold."""
    while True:
        await asyncio.sleep(period)
        bots = list(app.bots.values())
        pins = as_array(app.goals)
        if len(bots) == 0 or len(pins) == 0:
            app.publish_overlay([])
            app.publish_status("waiting for a pin on the map")
            continue

        radius = float(app.values.get("radius", 320))
        positions = np.array([[b.x, b.y] for b in bots], dtype=float)
        targets = ring_targets(positions, pins, radius, app.controller.map_size)
        for bot, target in zip(bots, targets):
            app.controller.waypoints(
                bot.address, [Point(target[0], target[1])], threshold=ARRIVE_MM
            )

        groups = split_by_proximity(positions, pins)
        overlay: List[dict] = []
        for i, pin in enumerate(pins):
            count = int((groups == i).sum())
            overlay.append(
                overlay_point(pin[0], pin[1], r=radius, label=f"{count}", color="accent")
            )
        app.publish_overlay(overlay)
        app.publish_status(f"{len(bots)} bots over {len(pins)} pins")


@demo_command
def cli(broker: str, controller: str, rate: float) -> None:
    """Ring the swarm around the pins the playground collects."""
    serve(
        ANNOUNCEMENT,
        lambda app: drive(app, period=1.0 / max(0.1, rate)),
        broker=broker,
        controller=controller,
        rate=rate,
    )


if __name__ == "__main__":
    cli()
