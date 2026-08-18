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
import time
from typing import TYPE_CHECKING

from dotbot.models import DotBotModel, DotBotStatus
from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.swarm.action import Action
from dotbot.swarm.position import Position

if TYPE_CHECKING:
    from dotbot.swarm.swarm import Swarm

# Hardware limit: a single waypoint command carries at most this many points.
MAX_WAYPOINTS = 12

# Motion-loop pacing. A bot reports its mode/position roughly once per position
# report period (~0.5 s on Mari / the simulator advertisement). Resend no faster
# than that, so a re-send can't rewind a bot that has already engaged its goal.
_RESEND_PERIOD = 0.6  # s, between waypoint re-sends while not yet engaged
_ARRIVAL_POLL = 0.2  # s, between arrival checks
# A move that never arrives must not hang the script forever (a bot can be stuck,
# lost, or chasing an unreachable goal). Past this budget the awaited Action
# raises TimeoutError instead of blocking or falsely reporting success.
DEFAULT_MOVE_TIMEOUT = 60.0  # s

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
        self._lh2 = None
        self._lh2_ts = 0.0
        self._lh2_candidate = None
        self._battery_emitted: float | None = None
        self._moves: set[asyncio.Task] = set()
        self._apply(model)

    def _apply(self, model: DotBotModel) -> None:
        """Refresh state from a controller DotBotModel (initial fetch or a
        ws/status UPDATE)."""
        self.application = model.application
        self._status: DotBotStatus = model.status
        self.mode: ControlModeType = model.mode
        # -1000 is the firmware's "no heading yet" sentinel.
        direction = model.direction
        self.direction: int | None = (
            None if direction is None or direction <= -1000 else direction
        )
        self.battery: float | None = model.battery
        self._gate_position(model.lh2_position)
        self.waypoints = list(model.waypoints or [])
        self.waypoints_threshold: int = model.waypoints_threshold
        self.last_seen: float = model.last_seen

    # Real LH2 feeds glitch: a fix can jump metres between two 2 Hz reports.
    # Gate updates to a plausible speed; a jump is held as a candidate and
    # accepted only when the next report lands near it (a real relocation).
    _MAX_PLAUSIBLE_MM_S = 500.0
    _CANDIDATE_CONFIRM_MM = 200.0

    def _gate_position(self, new) -> None:
        if new is not None and new.x == 0 and new.y == 0:
            return  # the firmware's "no fix" sentinel; keep the last real fix
        if new is None:
            return
        now = time.monotonic()
        accepted = self._lh2
        if accepted is None:
            self._lh2, self._lh2_ts, self._lh2_candidate = new, now, None
            return
        dt = max(now - self._lh2_ts, 0.05)
        jump = ((new.x - accepted.x) ** 2 + (new.y - accepted.y) ** 2) ** 0.5
        candidate = getattr(self, "_lh2_candidate", None)
        if jump / dt <= self._MAX_PLAUSIBLE_MM_S:
            self._lh2, self._lh2_ts, self._lh2_candidate = new, now, None
        elif (
            candidate is not None
            and ((new.x - candidate.x) ** 2 + (new.y - candidate.y) ** 2) ** 0.5
            < self._CANDIDATE_CONFIRM_MM
        ):
            # Second consistent report from the new place: the bot really moved.
            self._lh2, self._lh2_ts, self._lh2_candidate = new, now, None
        else:
            self._lh2_candidate = new  # hold the outlier; keep the last good fix

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
        """Direct per-wheel teleop (single-bot, high-rate). Fire-and-forget.
        Always takes over: in-flight move_to/follow Actions are cancelled
        (awaiting one raises CancelledError) and any shepherded goal is
        cleared - otherwise the move's resend loop would re-engage the bot
        moments after an operator stop."""
        for task in list(self._moves):
            task.cancel()
        if self._swarm._shepherd is not None:
            self._swarm._shepherd.clear(self.address)
        self._swarm._schedule(
            self._swarm._backend.send_move_raw(
                self.address, self.application, left, right
            )
        )

    def stop(self) -> None:
        self.move_raw(left=(0, 0), right=(0, 0))

    def goto(self, x: float, y: float, *, threshold: int = 100) -> None:
        """Fire-and-forget: set a single waypoint and return immediately,
        without waiting for arrival. The streaming counterpart to move_to/follow
        - for control loops (e.g. ORCA) that send a fresh target every tick. Use
        move_to/follow when you want to await arrival. With collision avoidance
        on, the waypoint becomes the bot's shepherded goal instead of a direct
        send."""
        if self._swarm._shepherd is not None:
            self._swarm._shepherd.set_goal(self.address, x, y, threshold)
            return
        self._swarm._schedule(
            self._swarm._backend.send_waypoints(
                self.address, self.application, [(float(x), float(y))], threshold
            )
        )

    def move_to(
        self,
        x: float,
        y: float,
        *,
        threshold: int = 100,
        timeout: float = DEFAULT_MOVE_TIMEOUT,
    ) -> Action:
        """Drive to a single point. Returns an Action; await it to wait for
        arrival (it raises TimeoutError if the bot does not arrive in
        `timeout` seconds)."""
        return self.follow([(x, y)], threshold=threshold, timeout=timeout)

    def follow(
        self, waypoints, *, threshold: int = 100, timeout: float = DEFAULT_MOVE_TIMEOUT
    ) -> Action:
        """Drive through a list of (x, y) waypoints. Returns an Action handle
        immediately; await it to wait until the bot reaches the last point.
        Absorbs the <=12 chunking and resend-until-engaged (with collision
        avoidance on, the points instead become the bot's shepherded goals,
        one at a time). Arrival is detected by position, and a bot that never
        arrives raises TimeoutError rather than hanging or reporting a false
        'done'."""
        points = [(float(x), float(y)) for x, y in waypoints]
        task = self._swarm._schedule(self._drive(points, threshold, timeout))
        self._moves.add(task)
        task.add_done_callback(self._moves.discard)
        return Action(task)

    async def _drive(
        self, points: list[tuple[float, float]], threshold: int, timeout: float
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        if self._swarm._shepherd is not None:
            from dotbot.swarm._shepherd import MIN_GOAL_THRESHOLD

            # Shepherded: each point becomes the bot's goal in turn; the
            # shepherd streams the safe hops, we only watch for arrival.
            # Avoidance cannot place a bot more precisely than the LH2 noise
            # floor, so sub-floor thresholds are clamped (here AND in the
            # shepherd) instead of stalling forever short of the goal.
            threshold = max(threshold, MIN_GOAL_THRESHOLD)
            for x, y in points:
                self._swarm._shepherd.set_goal(self.address, x, y, threshold)
                await self._await_arrival(Position(x, y), threshold, deadline)
            return
        for i in range(0, len(points), MAX_WAYPOINTS):
            await self._follow_chunk(points[i : i + MAX_WAYPOINTS], threshold, deadline)

    async def _await_arrival(
        self, target: Position, threshold: int, deadline: float
    ) -> None:
        loop = asyncio.get_running_loop()
        while True:
            pos = self.position
            if pos is not None and pos.distance_to(target) <= threshold:
                return
            if loop.time() > deadline:
                # Stop chasing an unreachable goal before surfacing the error.
                self._swarm._shepherd.clear(self.address)
                raise TimeoutError(
                    f"{self.address} did not reach "
                    f"({target.x:.0f}, {target.y:.0f}) within the move timeout"
                )
            await asyncio.sleep(_ARRIVAL_POLL)

    async def _follow_chunk(
        self, chunk: list[tuple[float, float]], threshold: int, deadline: float
    ) -> None:
        """Send a waypoint batch and wait until the bot is within `threshold` of
        the final point. Sends once, then re-sends only while the bot has not
        engaged (AUTO) and no faster than the report period, so a dropped command
        can't stall the run but an engaged bot is never rewound. Raises
        TimeoutError past `deadline` so the awaited Action surfaces a
        stuck/unreachable bot instead of hanging or claiming false success."""
        loop = asyncio.get_running_loop()
        target = Position(*chunk[-1])
        await self._swarm._backend.send_waypoints(
            self.address, self.application, chunk, threshold
        )
        last_send = loop.time()
        while True:
            pos = self.position
            if pos is not None and pos.distance_to(target) <= threshold:
                return
            if loop.time() > deadline:
                raise TimeoutError(
                    f"{self.address} did not reach "
                    f"({target.x:.0f}, {target.y:.0f}) within the move timeout"
                )
            if self.mode != ControlModeType.AUTO and (
                loop.time() - last_send >= _RESEND_PERIOD
            ):
                await self._swarm._backend.send_waypoints(
                    self.address, self.application, chunk, threshold
                )
                last_send = loop.time()
            await asyncio.sleep(_ARRIVAL_POLL)
