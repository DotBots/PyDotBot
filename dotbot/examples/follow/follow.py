"""The swarm follows the pointer, and wanders when there is none.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Follow in the rail.
"""

from __future__ import annotations

import asyncio
import random
from math import hypot
from typing import Dict, List, Optional, Sequence, Tuple

import click

from dotbot.examples.common.playground import (
    DEFAULT_BROKER,
    DEFAULT_CONTROLLER,
    Announcement,
    PlaygroundApp,
    Point,
    slider,
    toggle,
)

#: Approximate DotBot footprint, mm. The spread control counts in these.
BOT_FOOTPRINT_MM = 80

#: How far ahead a bot is aimed at full speed, per update. Larger than a bot
#: can travel in one period on purpose: the carrot stays out of reach while
#: the pointer moves, and only a still pointer lets the swarm close on it.
MAX_STEP_MM = 400

#: Waypoint threshold handed to the bot's own controller, mm.
ARRIVE_MM = 90

#: How hard separation bends the seek. Above 1 the swarm never converges.
SEPARATION_WEIGHT = 0.9

#: A wander goal is replaced once the bot is this close, or this long after
#: it was chosen - a bot that cannot reach its goal must not sit on it.
WANDER_ARRIVE_MM = 150
WANDER_TIMEOUT_TICKS = 60

ANNOUNCEMENT = Announcement(
    name="follow",
    title="Follow the pointer",
    hint="Move over the arena and the swarm follows. Leave, and they wander.",
    inputs=["pointer"],
    controls=[
        slider("speed", 0, 100, 60, unit="%"),
        slider("spread", 1, 6, 2, unit="bots"),
        toggle("wander", True, label="Wander when idle"),
    ],
    overlay=True,
)


def separation(
    at: Point, neighbours: Sequence[Point], radius: float
) -> Tuple[float, float]:
    """
    Reynolds separation: a unit-or-shorter push away from close neighbours.

    Weighted by 1/d, so the push grows sharply as two bots close on each
    other. A neighbour at exactly `at` is skipped, which is how the bot's own
    position can be left in the list.
    """
    sx = sy = 0.0
    for other in neighbours:
        dx = at.x - other.x
        dy = at.y - other.y
        distance = hypot(dx, dy)
        if distance < 1e-6 or distance > radius:
            continue
        weight = radius / distance - 1.0
        sx += dx / distance * weight
        sy += dy / distance * weight
    magnitude = hypot(sx, sy)
    if magnitude < 1e-9:
        return (0.0, 0.0)
    scale = min(1.0, magnitude) / magnitude
    return (sx * scale, sy * scale)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def follow_target(
    bot: Point,
    pointer: Point,
    neighbours: Sequence[Point],
    *,
    spread_mm: float,
    step_mm: float,
    arena: Tuple[int, int],
    margin: float = BOT_FOOTPRINT_MM,
) -> Point:
    """Where one bot should head: at the pointer, pushed off its neighbours."""
    dx = pointer.x - bot.x
    dy = pointer.y - bot.y
    distance = hypot(dx, dy)
    seek = (dx / distance, dy / distance) if distance > 1e-6 else (0.0, 0.0)
    push = separation(bot, neighbours, spread_mm)
    vx = seek[0] + push[0] * SEPARATION_WEIGHT
    vy = seek[1] + push[1] * SEPARATION_WEIGHT
    magnitude = hypot(vx, vy)
    if magnitude < 1e-6:
        return Point(bot.x, bot.y)
    step = min(step_mm, distance) if push == (0.0, 0.0) else step_mm
    return Point(
        clamp(bot.x + vx / magnitude * step, margin, arena[0] - margin),
        clamp(bot.y + vy / magnitude * step, margin, arena[1] - margin),
    )


def wander_target(
    rng: random.Random, arena: Tuple[int, int], margin: float = 200
) -> Point:
    """A point somewhere in the arena, well clear of the walls."""
    return Point(
        rng.uniform(margin, arena[0] - margin),
        rng.uniform(margin, arena[1] - margin),
    )


class _Wander:
    """Per-bot wander goals, replaced on arrival or on timeout."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._goals: Dict[str, Tuple[Point, int]] = {}

    def clear(self) -> None:
        self._goals.clear()

    def goal(self, address: str, at: Point, arena: Tuple[int, int]) -> Point:
        goal, age = self._goals.get(address, (None, 0))
        reached = (
            goal is not None and hypot(goal.x - at.x, goal.y - at.y) < WANDER_ARRIVE_MM
        )
        if goal is None or reached or age > WANDER_TIMEOUT_TICKS:
            goal, age = wander_target(self._rng, arena), 0
        self._goals[address] = (goal, age + 1)
        return goal


async def drive(app: PlaygroundApp, period: float = 0.2) -> None:
    """The loop: read the pointer, aim every bot, hand over the waypoints."""
    wander = _Wander()
    while True:
        await asyncio.sleep(period)
        bots = list(app.bots.values())
        arena = app.controller.map_size
        pointer = app.pointer.at if app.pointer is not None else None
        step_mm = (
            MAX_STEP_MM * clamp(float(app.values.get("speed", 60)), 0.0, 100.0) / 100.0
        )
        spread_mm = float(app.values.get("spread", 2)) * BOT_FOOTPRINT_MM

        if pointer is not None:
            wander.clear()
            positions: List[Point] = [Point(b.x, b.y) for b in bots]
            for bot in bots:
                target = follow_target(
                    Point(bot.x, bot.y),
                    pointer,
                    positions,
                    spread_mm=spread_mm,
                    step_mm=step_mm,
                    arena=arena,
                )
                app.controller.waypoints(bot.address, [target], threshold=ARRIVE_MM)
            app.publish_overlay([{"type": "point", "x": pointer.x, "y": pointer.y}])
            app.publish_status(f"following the pointer, {len(bots)} bots")
        elif bool(app.values.get("wander", True)):
            for bot in bots:
                goal = wander.goal(bot.address, Point(bot.x, bot.y), arena)
                app.controller.waypoints(
                    bot.address, [goal], threshold=WANDER_ARRIVE_MM
                )
            app.publish_overlay([])
            app.publish_status(f"wandering, {len(bots)} bots")
        else:
            app.publish_overlay([])
            app.publish_status(f"idle, {len(bots)} bots")


async def main(broker: str, controller: str, rate: float) -> None:
    app = PlaygroundApp(
        ANNOUNCEMENT, broker=broker, controller=controller, command_rate_hz=rate
    )
    await app.start()
    announce, _, _ = app.topics
    click.echo(f"follow announced on {announce}, driving {controller}")
    try:
        await drive(app, period=1.0 / max(0.1, rate))
    finally:
        await app.stop()


@click.command()
@click.option(
    "--broker", default=DEFAULT_BROKER, show_default=True, help="MQTT broker URL."
)
@click.option(
    "--controller",
    default=DEFAULT_CONTROLLER,
    show_default=True,
    help="Controller base URL.",
)
@click.option(
    "--rate", default=5.0, show_default=True, help="Command rate per bot, in hertz."
)
def cli(broker: str, controller: str, rate: float) -> None:
    """Drive the swarm after the playground's pointer."""
    try:
        asyncio.run(main(broker, controller, rate))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
