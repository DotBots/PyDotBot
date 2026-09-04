"""A drone show on the floor: rings, a spiral, a pulse and a wave.

Run the controller (or the simulator), a broker with a websockets listener,
then this script, then open /playground and pick Drone show in the rail.
"""

from __future__ import annotations

import asyncio
import colorsys
from typing import Dict, List, Tuple

import numpy as np

from dotbot.examples.common.playground import (
    Announcement,
    PlaygroundApp,
    Point,
    assign_targets,
    button,
    demo_command,
    overlay_polyline,
    select,
    serve,
    slider,
    toggle,
)
from dotbot.examples.common.raster import clamp_to_arena, ring_points

FIGURES = ["ring", "double ring", "spiral", "pulse", "wave"]

#: How often the formation is re-sent. A re-sent waypoint set restarts the
#: bot on it, so a keyframe is as fast as a moving figure can be driven.
KEYFRAME_S = 1.0

#: Radians the phase advances per second at 100% tempo. A bot drives at a
#: couple of hundred mm/s, so a figure that turns much faster than this is one
#: the swarm can only trail.
PHASE_RATE = 0.12

#: Waypoint threshold, mm. Looser than a formation demo would like, but a bot
#: that keeps hunting its slot never gets to the next keyframe.
ARRIVE_MM = 100

ANNOUNCEMENT = Announcement(
    name="show",
    title="Drone show",
    hint="Pick a figure and press play. The LEDs colour by angle.",
    inputs=[],
    controls=[
        select("figure", FIGURES, "ring", label="Figure"),
        slider("tempo", 10, 800, 100, step=5, label="Tempo", unit="%"),
        button("play", label="Play / pause"),
        toggle("guides", True, label="Show guides"),
        slider("arrive", 20, 150, ARRIVE_MM, step=5, label="Arrival radius", unit="mm"),
    ],
    overlay=True,
)


def formation(
    figure: str, count: int, arena: Tuple[float, float], phase: float
) -> np.ndarray:
    """`count` points making one figure at `phase` radians, inside the arena."""
    if count <= 0:
        return np.zeros((0, 2))
    center = (arena[0] / 2, arena[1] / 2)
    reach = min(arena[0], arena[1]) / 2 - 200

    if figure == "double ring":
        inner = count // 2
        points = np.concatenate(
            [
                ring_points(center, inner, reach * 0.5, phase=phase),
                ring_points(center, count - inner, reach, phase=-phase),
            ]
        )
    elif figure == "spiral":
        turns = 2.5
        t = np.linspace(0.0, 1.0, count)
        angle = phase + t * turns * 2 * np.pi
        radius = reach * (0.15 + 0.85 * t)
        points = np.stack(
            [center[0] + radius * np.cos(angle), center[1] + radius * np.sin(angle)],
            axis=1,
        )
    elif figure == "pulse":
        radius = reach * (0.55 + 0.45 * np.sin(phase))
        points = ring_points(center, count, radius, phase=phase * 0.2)
    elif figure == "wave":
        columns = max(1, int(np.ceil(np.sqrt(count * 2))))
        index = np.arange(count)
        column, row = index % columns, index // columns
        rows = int(np.ceil(count / columns))
        x = center[0] + (column / max(1, columns - 1) - 0.5) * 2 * reach
        y = center[1] + (row - (rows - 1) / 2) * 180
        points = np.stack([x, y + reach * 0.45 * np.sin(phase + column * 0.7)], axis=1)
    else:
        points = ring_points(center, count, reach, phase=phase)
    return clamp_to_arena(points, arena)


def hue_by_angle(points: np.ndarray, arena: Tuple[float, float]) -> np.ndarray:
    """Each point's bearing from the arena centre, in degrees."""
    if len(points) == 0:
        return np.zeros(0)
    dx = points[:, 0] - arena[0] / 2
    dy = points[:, 1] - arena[1] / 2
    return np.degrees(np.arctan2(dy, dx)) % 360.0


def rgb(hue: float) -> Tuple[int, int, int]:
    """One LED colour, full saturation, at `hue` degrees."""
    r, g, b = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def figure_overlay(figure: str, points: np.ndarray) -> List[dict]:
    """The figure as a path: closed for a ring, open for a spiral or a wave."""

    def path(part: np.ndarray, closed: bool) -> List[dict]:
        if len(part) < 2:
            return []
        return [
            overlay_polyline(
                [Point(p[0], p[1]) for p in part], closed=closed, color="muted"
            )
        ]

    if figure == "double ring":
        half = len(points) // 2
        return path(points[:half], True) + path(points[half:], True)
    return path(points, figure in ("ring", "pulse"))


class Choreography:
    """
    Which slot each bot holds, and where the figure is in its cycle.

    A bot keeps its slot while the figure runs, so a rotating ring turns
    rather than re-shuffling: the assignment is redone only when the figure
    or the fleet changes.
    """

    def __init__(self) -> None:
        self.phase = 0.0
        self.playing = True
        self._slots: Dict[str, int] = {}
        self._for: Tuple[str, int] = ("", 0)
        self._hue: Dict[str, float] = {}

    def slots(
        self,
        figure: str,
        addresses: List[str],
        positions: np.ndarray,
        arena: Tuple[float, float],
    ) -> Dict[str, int]:
        if self._for == (figure, len(addresses)) and set(self._slots) == set(addresses):
            return self._slots
        points = formation(figure, len(addresses), arena, self.phase)
        order = assign_targets(positions, points)
        self._slots = {a: int(i) for a, i in zip(addresses, order)}
        self._for = (figure, len(addresses))
        self._hue.clear()
        return self._slots

    def needs_led(self, address: str, hue: float, step: float = 8.0) -> bool:
        """
        Whether this bot's LED is far enough off to be worth a command.

        Every bot lit every keyframe is a command per bot per second on top
        of the waypoints, and most of those repaint a colour nobody can tell
        from the one already showing.
        """
        was = self._hue.get(address)
        if was is not None and abs((hue - was + 180) % 360 - 180) < step:
            return False
        self._hue[address] = hue
        return True


async def drive(app: PlaygroundApp, keyframe: float = KEYFRAME_S) -> None:
    """The loop: advance the phase, re-send the formation, colour the LEDs."""
    show = Choreography()

    def on_play(action) -> None:
        if action.id == "play":
            show.playing = not show.playing

    app.on_action(on_play)

    while True:
        await asyncio.sleep(keyframe)
        bots = list(app.bots.values())
        arena = app.controller.map_size
        figure = str(app.values.get("figure", "ring"))
        tempo = float(app.values.get("tempo", 100)) / 100.0
        if len(bots) == 0:
            app.publish_status("no bots")
            continue

        addresses = [b.address for b in bots]
        positions = np.array([[b.x, b.y] for b in bots], dtype=float)
        slots = show.slots(figure, addresses, positions, arena)
        if show.playing:
            show.phase += PHASE_RATE * tempo * keyframe

        points = formation(figure, len(bots), arena, show.phase)
        hues = hue_by_angle(points, arena)
        for bot in bots:
            slot = slots.get(bot.address, 0)
            target = points[slot]
            app.controller.waypoints(
                bot.address, [Point(target[0], target[1])], threshold=int(app.values.get("arrive", ARRIVE_MM))
            )
            if show.needs_led(bot.address, hues[slot]):
                app.controller.rgb_led(bot.address, *rgb(hues[slot]))

        app.publish_overlay(
            figure_overlay(figure, points) if bool(app.values.get("guides", True)) else []
        )
        app.publish_status(
            f"{figure}, {'playing' if show.playing else 'paused'}, {len(bots)} bots"
        )


@demo_command
def cli(broker: str, controller: str, rate: float) -> None:
    """Run the swarm through a set of choreographies."""
    serve(
        ANNOUNCEMENT, drive, broker=broker, controller=controller, rate=rate
    )


if __name__ == "__main__":
    cli()
