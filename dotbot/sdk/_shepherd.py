# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The collision-avoidance shepherd behind `collision_avoidance=True`.

When a Swarm is connected with collision avoidance on, `goto` / `move_to` /
`follow` no longer send the user's waypoint to the bot directly. They register
the waypoint as a *goal* here, and this loop streams safe intermediate hops
toward it - each hop the goal projected into the bot's buffered Voronoi cell
(see `dotbot.sdk.avoid`) - until the bot is within the goal's threshold. The
placement mirrors what Crazyswarm does on board and the Robotarium does on its
server: a setpoint filter *under* the user's commands, so user code stays a
plain "go there".

Liveness is the shepherd's job too: a bot that stops progressing detours to
its right (the standard BVC deadlock heuristic) and stops yielding to crowded
neighbours, so a blocked fleet unjams itself instead of freezing.

The loop is paced to the gateway downlink budget: with more active goals than
the link can refresh once per second, the tick stretches instead of flooding
the link (and the per-send pacing in the backend still applies).
"""

from __future__ import annotations

import asyncio
import math

from dotbot.logger import LOGGER
from dotbot.sdk._backend import DEFAULT_DOWNLINK_HZ
from dotbot.sdk.avoid import safe_hop

_TICK = 1.0  # s between hop refreshes per bot, when the link allows it
_PLAN_BUDGET = 0.75  # fraction of the downlink budget a shepherd may consume
_STUCK_MM = 25.0  # progress below this per tick counts as stalled
_SIDESTEP = 350.0  # mm: detour length when stalled (right-hand rule; > the floor)
_DETOUR_TICKS = 4  # commit to a detour this long, or it just oscillates


class Shepherd:
    """Streams BVC-safe hops for every registered (bot, goal) pair."""

    def __init__(self, swarm, min_separation: float):
        self._swarm = swarm
        self._safe_radius = min_separation / 2
        self._goals: dict[str, tuple[float, float, int]] = {}
        self._stuck: dict[str, int] = {}
        self._detour: dict[str, tuple[float, float, int]] = {}  # (x, y, ticks left)
        self._last_pos: dict[str, tuple[float, float]] = {}
        self._task: asyncio.Task | None = None
        self._arena: tuple[float, float] | None = None

    def set_goal(self, address: str, x: float, y: float, threshold: int) -> None:
        """Register (or replace) a bot's goal and make sure the loop runs."""
        self._goals[address] = (float(x), float(y), threshold)
        self._stuck.pop(address, None)
        self._detour.pop(address, None)
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._loop())

    def clear(self, address: str) -> None:
        """Drop a bot's goal (an explicit stop/move_raw takes back control)."""
        self._goals.pop(address, None)
        self._detour.pop(address, None)

    async def close(self) -> None:
        self._goals.clear()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ---- the loop --------------------------------------------------------

    def _tick(self) -> float:
        budget = DEFAULT_DOWNLINK_HZ * _PLAN_BUDGET
        return max(_TICK, len(self._goals) / budget) if budget > 0 else _TICK

    async def _loop(self) -> None:
        while self._goals:
            try:
                await self._step()
            except Exception:  # noqa: BLE001 - a failed send must not kill the loop
                LOGGER.exception("collision-avoidance shepherd step failed")
            await asyncio.sleep(self._tick())

    async def _step(self) -> None:
        if self._arena is None:
            self._arena = await self._swarm._backend.fetch_map_size()
        bots = {b.address: b for b in self._swarm}
        positions = {
            a: (b.position.x, b.position.y)
            for a, b in bots.items()
            if b.position is not None
        }
        for address in list(self._goals):
            bot = bots.get(address)
            if bot is None or address not in positions:
                continue  # no fix yet; keep the goal pending
            gx, gy, threshold = self._goals[address]
            px, py = positions[address]
            if math.hypot(gx - px, gy - py) <= threshold:
                self._goals.pop(address, None)  # arrived; the bot stops itself
                continue
            goal = (gx, gy)
            patience = self._stuck.get(address, 0)
            detour = self._detour.get(address)
            if detour is not None:
                dx_, dy_, left = detour
                if left <= 0:
                    self._detour.pop(address, None)
                else:
                    goal = (dx_, dy_)
                    self._detour[address] = (dx_, dy_, left - 1)
            elif patience >= 2:  # blocked: commit to a right-hand detour
                d = math.hypot(gx - px, gy - py) or 1.0
                ux, uy = (gx - px) / d, (gy - py) / d
                goal = (px + uy * _SIDESTEP, py - ux * _SIDESTEP)
                self._detour[address] = (goal[0], goal[1], _DETOUR_TICKS)
                self._stuck[address] = 0
                patience = 0
            wp = safe_hop(
                address,
                positions,
                goal,
                self._arena,
                heading=bot.direction,
                # A bot on a committed detour must execute it, not yield.
                yield_ok=patience < 2 and address not in self._detour,
                safe_radius=self._safe_radius,
            )
            last = self._last_pos.get(address)
            if last is not None and math.hypot(px - last[0], py - last[1]) < _STUCK_MM:
                self._stuck[address] = self._stuck.get(address, 0) + 1
            else:
                self._stuck[address] = 0
            self._last_pos[address] = (px, py)
            hop = math.hypot(wp[0] - px, wp[1] - py)
            if hop < 15:
                continue
            # A waypoint within the firmware threshold is "already reached"
            # and moves nothing - scale the threshold down for short hops.
            hop_threshold = 100 if hop >= 250 else max(20, int(hop * 0.5))
            await self._swarm._backend.send_waypoints(
                address, bot.application, [wp], hop_threshold
            )
