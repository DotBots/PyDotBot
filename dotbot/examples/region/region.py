"""The swarm fills the rectangles drawn on the map, split by area.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Regions in the rail.
Shift-drag on the map to draw a region; drag an edge to resize it.
"""

from __future__ import annotations

import asyncio
from typing import List, Sequence

import numpy as np

from dotbot.examples.common.playground import (
    Announcement,
    PlaygroundApp,
    Point,
    Rect,
    assign_targets,
    demo_command,
    overlay_rect,
    serve,
    slider,
)

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 40

#: Bots keep this far from a region's edge, so none is parked in a wall.
INSET_MM = 60

ANNOUNCEMENT = Announcement(
    name="region",
    title="Regions",
    hint="Shift-drag a rectangle. The swarm splits across the regions by area.",
    inputs=["rects"],
    controls=[slider("arrive", 20, 150, ARRIVE_MM, step=5, label="Arrival radius", unit="mm")],
    overlay=True,
)


def share_by_area(rects: Sequence[Rect], bots: int) -> List[int]:
    """
    How many bots each region gets: its share of the total area, with the
    rounding leftovers going to the largest regions. Every region gets at
    least one bot as long as there are bots to go round.
    """
    if not rects or bots <= 0:
        return [0] * len(rects)
    areas = np.array([max(r.area, 1.0) for r in rects], dtype=float)
    if bots <= len(rects):
        # Too few to fill every region: the largest ones get the bots.
        counts = [0] * len(rects)
        for i in np.argsort(-areas)[:bots]:
            counts[int(i)] = 1
        return counts
    exact = areas / areas.sum() * (bots - len(rects))
    counts = np.floor(exact).astype(int) + 1
    for i in np.argsort(-(exact - np.floor(exact)))[: bots - int(counts.sum())]:
        counts[int(i)] += 1
    return [int(c) for c in counts]


def fill_points(rect: Rect, count: int) -> np.ndarray:
    """
    `count` points spread over a rectangle on the squarest grid that holds
    them, inset from the edges. The last row is centred, so a partly filled
    grid still looks deliberate.
    """
    if count <= 0:
        return np.zeros((0, 2))
    x0, y0 = rect.x + INSET_MM, rect.y + INSET_MM
    w, h = max(rect.w - 2 * INSET_MM, 1.0), max(rect.h - 2 * INSET_MM, 1.0)
    columns = max(1, int(round(np.sqrt(count * w / h))))
    rows = int(np.ceil(count / columns))
    points = []
    for index in range(count):
        row, column = divmod(index, columns)
        in_row = min(columns, count - row * columns)
        fx = (column + 0.5) / in_row
        fy = (row + 0.5) / rows
        points.append((x0 + fx * w, y0 + fy * h))
    return np.asarray(points, dtype=float)


def region_targets(bots: np.ndarray, rects: Sequence[Rect]) -> np.ndarray:
    """A target per bot: a slot in one region, assigned across the whole set."""
    counts = share_by_area(rects, len(bots))
    slots = np.concatenate(
        [fill_points(rect, count) for rect, count in zip(rects, counts)]
        + [np.zeros((0, 2))]
    )
    if len(slots) < len(bots):
        # Rounding can leave a bot without a slot; it stays where it is.
        slots = np.concatenate([slots, bots[len(slots) :]])
    return slots[assign_targets(bots, slots)]


async def drive(app: PlaygroundApp, period: float = 0.5) -> None:
    """The loop: sample every rectangle into slots, assign, hold."""
    while True:
        await asyncio.sleep(period)
        bots = list(app.bots.values())
        rects = list(app.rects)
        if len(bots) == 0 or len(rects) == 0:
            app.publish_overlay([])
            app.publish_status("waiting for a region on the map")
            continue

        positions = np.array([[b.x, b.y] for b in bots], dtype=float)
        targets = region_targets(positions, rects)
        for bot, target in zip(bots, targets):
            app.controller.waypoints(
                bot.address, [Point(target[0], target[1])], threshold=int(app.values.get("arrive", ARRIVE_MM))
            )

        counts = share_by_area(rects, len(bots))
        app.publish_overlay(
            [
                overlay_rect(r.x, r.y, r.w, r.h, label=f"{c} bots", color="accent")
                for r, c in zip(rects, counts)
            ]
        )
        app.publish_status(f"{len(bots)} bots over {len(rects)} regions")


@demo_command
def cli(broker: str, controller: str, rate: float) -> None:
    """Fill the regions the playground collects."""
    serve(
        ANNOUNCEMENT,
        lambda app: drive(app, period=1.0 / max(0.1, rate)),
        broker=broker,
        controller=controller,
        rate=rate,
    )


if __name__ == "__main__":
    cli()
