# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The `Bot` - one DotBot's live state plus its domain verbs.

State is read-only and kept fresh by the `Swarm` from the `ws/status` stream;
the verbs (`set_color`, `move_raw`, `move_to`, `follow`, ...) issue commands.
`move_to`/`follow` are the primary motion primitives: they hand the bot a goal
it pursues autonomously off its own local fix (SDK plan section 3), so one
low-rate waypoint per bot is enough. `follow` absorbs the boilerplate every
example hand-rolls today - the <=12 chunking, resend-until-AUTO, and
poll-until-arrival.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from dotbot.models import DotBotModel, DotBotStatus
from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.sdk.action import Action
from dotbot.sdk.position import Position

if TYPE_CHECKING:
    from dotbot.sdk.swarm import Swarm

# Hardware limit: a single waypoint command carries at most this many points.
MAX_WAYPOINTS = 12

_COLORS: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "off": (0, 0, 0),
    "black": (0, 0, 0),
}


class Bot:
    """One DotBot. State is updated by the Swarm; verbs send commands."""

    def __init__(self, swarm: Swarm, model: DotBotModel):
        self._swarm = swarm
        self.address: str = model.address
        self.application: ApplicationType = model.application
        self._apply(model)

    def _apply(self, model: DotBotModel) -> None:
        """Refresh state from a controller DotBotModel (initial fetch or a
        ws/status UPDATE)."""
        self.application = model.application
        self._status: DotBotStatus = model.status
        self.mode: ControlModeType = model.mode
        self.direction: int | None = model.direction
        self.battery: float | None = model.battery
        self._lh2 = model.lh2_position
        self.waypoints = list(model.waypoints or [])
        self.waypoints_threshold: int = model.waypoints_threshold
        self.last_seen: float = model.last_seen

    # ---- read-only state ------------------------------------------------

    @property
    def position(self) -> Position | None:
        """The latest LH2 position, or None if the bot has no fix yet."""
        if self._lh2 is None:
            return None
        return Position(self._lh2.x, self._lh2.y)

    @property
    def is_online(self) -> bool:
        return self._status == DotBotStatus.ACTIVE

    def __repr__(self) -> str:
        p = self.position
        where = f"({p.x:.0f},{p.y:.0f})" if p else "no-fix"
        return f"<Bot {self.address} {self.application.name} {where} mode={self.mode.name}>"

    # ---- commands -------------------------------------------------------

    def set_color(
        self, color=None, *, red: int = 0, green: int = 0, blue: int = 0
    ) -> None:
        """Set the RGB LED. Accepts a name ("blue"), an (r, g, b) tuple, or
        red=/green=/blue= keywords. Fire-and-forget."""
        if color is not None:
            if isinstance(color, str):
                try:
                    red, green, blue = _COLORS[color.lower()]
                except KeyError as exc:
                    raise ValueError(f"unknown color name: {color!r}") from exc
            else:
                red, green, blue = color
        self._swarm._schedule(
            self._swarm._backend.send_rgb_led(
                self.address, self.application, red, green, blue
            )
        )

    def move_raw(
        self, *, left: tuple[int, int] = (0, 0), right: tuple[int, int] = (0, 0)
    ) -> None:
        """Direct per-wheel teleop (single-bot, high-rate). Fire-and-forget."""
        self._swarm._schedule(
            self._swarm._backend.send_move_raw(
                self.address, self.application, left, right
            )
        )

    def stop(self) -> None:
        self.move_raw(left=(0, 0), right=(0, 0))

    def move_to(self, x: float, y: float, *, speed: int = 50) -> Action:
        """Drive to a single point. Returns an Action; await it to wait for
        arrival."""
        return self.follow([(x, y)])

    def follow(self, waypoints, *, threshold: int = 100) -> Action:
        """Drive through a list of (x, y) waypoints. Returns an Action handle
        immediately; await it to wait until the bot reaches the last point.
        Absorbs the <=12 chunking, resend-until-AUTO, and poll-until-arrival."""
        return Action(
            self._drive([(float(x), float(y)) for x, y in waypoints], threshold)
        )

    async def _drive(self, points: list[tuple[float, float]], threshold: int) -> None:
        for i in range(0, len(points), MAX_WAYPOINTS):
            chunk = points[i : i + MAX_WAYPOINTS]
            await self._send_until_auto(chunk, threshold)
            await self._wait_until_arrived()

    async def _send_until_auto(self, chunk, threshold: int) -> None:
        """Send a waypoint batch, resending until the bot reports AUTO mode (so
        a dropped command does not stall the run). Bounded so it can't spin
        forever if the bot never engages."""
        for _ in range(100):
            await self._swarm._backend.send_waypoints(
                self.address, self.application, chunk, threshold
            )
            await asyncio.sleep(0.3)
            if self.mode == ControlModeType.AUTO:
                return

    async def _wait_until_arrived(self) -> None:
        """Wait until the bot leaves AUTO (reached the final waypoint) or its
        waypoint queue drains."""
        while self.mode == ControlModeType.AUTO and self.waypoints:
            await asyncio.sleep(0.2)
