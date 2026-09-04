"""The swarm spells the word typed into the playground's text field.

Needs Pillow, which rasterises the word: pip install 'pydotbot[letters]'.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Spell a word in the rail.
The word wants room: at two bot footprints between neighbours, a six-letter
word needs an arena of a few metres to stay legible.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List

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
from dotbot.examples.common.raster import spare_ring, word_points

#: Approximate DotBot footprint, mm.
BOT_FOOTPRINT_MM = 80

#: Closest two bots are ever aimed. Two footprints, so a letter stroke reads
#: as a line of separate robots rather than a smudge.
MIN_SPACING_MM = 2 * BOT_FOOTPRINT_MM

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 40

ANNOUNCEMENT = Announcement(
    name="letters",
    title="Spell a word",
    hint="Type a word, press Go, and the swarm rasterises it.",
    inputs=["text"],
    controls=[
        slider("size", 200, 1600, 700, step=50, label="Height", unit="mm"),
        slider("arrive", 20, 150, ARRIVE_MM, step=5, label="Arrival radius", unit="mm"),
    ],
    overlay=True,
)


class Word:
    """The word being spelled, and the target each bot was given for it."""

    def __init__(self) -> None:
        self.text = ""
        #: Keyed by address: a bot that joins later has no target and waits.
        self.targets: Dict[str, Point] = {}
        #: The word's own points, which are what the ghost pins show.
        self.ink: np.ndarray = np.zeros((0, 2))

    def plan(
        self, text: str, addresses: List[str], positions: np.ndarray, app: PlaygroundApp
    ) -> None:
        """Rasterise, park the spares in a ring, and assign the lot."""
        arena = app.controller.map_size
        self.ink = word_points(
            text,
            budget=len(addresses),
            height_mm=float(app.values.get("size", 700)),
            arena=arena,
            min_spacing_mm=MIN_SPACING_MM,
        )
        spares = spare_ring(len(addresses) - len(self.ink), arena)
        slots = np.concatenate([self.ink, spares]) if len(spares) else self.ink
        self.text = text
        order = assign_targets(positions, slots)
        self.targets = {
            address: Point(slots[i][0], slots[i][1])
            for address, i in zip(addresses, order)
        }


async def drive(app: PlaygroundApp, period: float = 0.5) -> None:
    """The loop: on a new word, publish the ghost pins, then drive to them."""
    word = Word()
    pending: List[str] = []
    app.on_text(lambda message: pending.append(message.text))

    while True:
        await asyncio.sleep(period)
        bots = list(app.bots.values())
        if len(bots) == 0:
            app.publish_status("no bots")
            continue

        if pending:
            text = pending[-1]
            pending.clear()
            positions = np.array([[b.x, b.y] for b in bots], dtype=float)
            word.plan(text, [b.address for b in bots], positions, app)
            # The pins go out before the first waypoint, so the shape is on
            # the canvas while the swarm is still crossing the arena.
            app.publish_overlay(
                [
                    overlay_point(x, y, r=BOT_FOOTPRINT_MM / 2, color="muted")
                    for x, y in word.ink
                ]
            )
            app.publish_status(
                f"{word.text}: {len(word.ink)} bots spelling, "
                f"{len(bots) - len(word.ink)} parked"
            )

        for bot in bots:
            target = word.targets.get(bot.address)
            if target is not None:
                app.controller.waypoints(bot.address, [target], threshold=int(app.values.get("arrive", ARRIVE_MM)))


@demo_command
def cli(broker: str, controller: str, rate: float) -> None:
    """Spell the playground's text with the swarm."""
    serve(
        ANNOUNCEMENT,
        lambda app: drive(app, period=1.0 / max(0.1, rate)),
        broker=broker,
        controller=controller,
        rate=rate,
    )


if __name__ == "__main__":
    cli()
