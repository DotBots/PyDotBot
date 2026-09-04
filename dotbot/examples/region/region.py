"""The swarm fills the rectangles drawn on the map, split by area.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Regions in the rail.
Shift-drag on the map to draw a region; drag an edge to resize it.
"""

from __future__ import annotations

import asyncio
from typing import Sequence

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
from dotbot.examples.common.raster import spare_ring

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 40

#: Bots keep this far from a region's edge, so none is parked in a wall.
INSET_MM = 60

#: Closest two bots are ever aimed inside a region: two footprints, mm.
SPACING_MM = 160

ANNOUNCEMENT = Announcement(
    name="region",
    title="Regions",
    hint="Shift-drag a rectangle. The swarm splits across the regions by area.",
    inputs=["rects"],
    controls=[
        slider("arrive", 20, 150, ARRIVE_MM, step=5, label="Arrival radius", unit="mm")
    ],
    overlay=True,
)


def share_by_area(rects: Sequence[Rect], bots: int) -> list[int]:
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


def capacity(rect: Rect) -> int:
    """How many bots a rectangle holds at SPACING_MM, inside the inset."""
    w, h = rect.w - 2 * INSET_MM, rect.h - 2 * INSET_MM
    if w <= 0 or h <= 0:
        return 0
    return max(1, int(w * h // (SPACING_MM * SPACING_MM)))


def share_by_capacity(rects: Sequence[Rect], bots: int) -> list[int]:
    """`share_by_area`, capped at what each region holds; the rest stay unassigned."""
    caps = [capacity(r) for r in rects]
    counts = [0] * len(rects)
    remaining = min(bots, sum(caps))
    while remaining > 0:
        open_idx = [i for i in range(len(rects)) if counts[i] < caps[i]]
        if not open_idx:
            break
        share = share_by_area([rects[i] for i in open_idx], remaining)
        for i, c in zip(open_idx, share):
            take = min(c, caps[i] - counts[i])
            counts[i] += take
            remaining -= take
    return counts


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


def region_targets(
    bots: np.ndarray, rects: Sequence[Rect], arena: tuple[float, float]
) -> np.ndarray:
    """A target per bot: a slot in one region, or a spot on the parking ring."""
    counts = share_by_capacity(rects, len(bots))
    slots = np.concatenate(
        [fill_points(rect, count) for rect, count in zip(rects, counts)]
        + [np.zeros((0, 2))]
    )
    spares = spare_ring(len(bots) - len(slots), arena)
    if len(spares):
        slots = np.concatenate([slots, spares])
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
        targets = region_targets(positions, rects, app.controller.map_size)
        for bot, target in zip(bots, targets):
            app.controller.waypoints(
                bot.address,
                [Point(target[0], target[1])],
                threshold=int(app.values.get("arrive", ARRIVE_MM)),
            )

        counts = share_by_capacity(rects, len(bots))
        app.publish_overlay(
            [
                overlay_rect(r.x, r.y, r.w, r.h, label=f"{c} bots", color="accent")
                for r, c in zip(rects, counts)
            ]
        )
        parked = len(bots) - sum(counts)
        app.publish_status(
            f"{sum(counts)} of {len(bots)} bots fit in {len(rects)} regions, {parked} parked"
            if parked
            else f"{len(bots)} bots over {len(rects)} regions"
        )


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
