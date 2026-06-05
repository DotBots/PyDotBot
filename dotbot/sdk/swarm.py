# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The `Swarm` - the SDK's entry point and live fleet.

`Swarm.connect(conn)` discriminates on the connection string (SDK plan section
10). v1 implements the `http(s)://` connection (a running `dotbot run
controller`); the direct links (`mqtts://`, serial) and `simulator` come later
behind this same surface. The Swarm holds the live `Bot` objects, keeps them
fresh from the controller's `ws/status` stream, and exposes iteration, the
`all` / `select(...)` fleet handles, and the `link` budget.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import AsyncIterator, Callable, Iterator
from urllib.parse import urlparse

from dotbot.logger import LOGGER
from dotbot.models import DotBotModel, DotBotStatus
from dotbot.sdk._backend import HttpBackend
from dotbot.sdk.bot import Bot
from dotbot.sdk.events import (
    BatteryUpdate,
    BotJoined,
    BotLeft,
    Event,
    ModeChanged,
    PositionUpdate,
)
from dotbot.sdk.fleet import Fleet
from dotbot.sdk.link import LinkProfile
from dotbot.sdk.position import Position


def _backend_for(conn: str):
    """Pick a backend from the connection string. v1: http(s) only."""
    if conn.startswith(("http://", "https://")):
        parsed = urlparse(conn)
        https = parsed.scheme == "https"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if https else 8000)
        return HttpBackend(host, port, https)
    raise ValueError(
        f"unsupported connection {conn!r} - v1 supports http(s):// "
        "(a running `dotbot run controller`); mqtts://, serial and simulator come later"
    )


class Swarm:
    """The live swarm. Use `async with Swarm.connect(url) as swarm:`."""

    def __init__(self, backend):
        self._backend = backend
        self._bots: dict[str, Bot] = {}
        self._tasks: set[asyncio.Task] = set()
        self._handlers: dict[type, list[Callable]] = {}
        self._event_queues: set[asyncio.Queue] = set()
        self._positions_clamped = False
        self._tick_warned = False

    @classmethod
    def connect(cls, conn: str) -> Swarm:
        """Return a Swarm for `conn`. Enter it as an async context manager to
        actually open the connection."""
        return cls(_backend_for(conn))

    async def __aenter__(self) -> Swarm:
        await self._open()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def _open(self) -> None:
        for model in await self._backend.fetch_fleet():
            self._bots[model.address] = Bot(self, model)
        await self._backend.connect(self._on_update, self._on_reload)

    # ---- state plumbing -------------------------------------------------

    def _on_update(self, data: dict) -> None:
        try:
            model = DotBotModel(**data)
        except Exception:  # noqa: BLE001 - ignore malformed pushes
            return
        bot = self._bots.get(model.address)
        if bot is None:
            bot = Bot(self, model)
            self._bots[model.address] = bot
            self._emit(BotJoined(bot.address, time.monotonic()))
            return
        before = (bot.position, bot.battery, bot.mode, bot._status)
        bot._apply(model)
        self._emit_changes(bot, *before)

    def _emit_changes(self, bot, old_pos, old_battery, old_mode, old_status) -> None:
        ts = time.monotonic()
        if bot.position is not None and bot.position != old_pos:
            self._emit(PositionUpdate(bot.address, ts, bot.position))
        if (
            bot.battery is not None
            and old_battery is not None
            and abs(bot.battery - old_battery) >= 0.05
        ):
            self._emit(BatteryUpdate(bot.address, ts, bot.battery))
        if bot.mode != old_mode:
            self._emit(ModeChanged(bot.address, ts, bot.mode))
        if old_status == DotBotStatus.ACTIVE and bot._status != DotBotStatus.ACTIVE:
            self._emit(BotLeft(bot.address, ts))

    def _on_reload(self) -> None:
        self._schedule(self._refetch())

    async def _refetch(self) -> None:
        # A reload (e.g. a NEW_DOTBOT notification) is the real path by which a
        # bot joins after connect; the per-bot UPDATE stream never carries the
        # first sight of it. Emit BotJoined here so `swarm.on(BotJoined, ...)`
        # actually fires for a mid-run join, not only for the initial fleet.
        for model in await self._backend.fetch_fleet():
            bot = self._bots.get(model.address)
            if bot is None:
                bot = Bot(self, model)
                self._bots[model.address] = bot
                self._emit(BotJoined(bot.address, time.monotonic()))
            else:
                bot._apply(model)

    def _schedule(self, coro) -> asyncio.Task:
        """Run a fire-and-forget command coroutine, keeping a reference so it is
        not garbage-collected mid-flight."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ---- collection protocol -------------------------------------------

    def __iter__(self) -> Iterator[Bot]:
        return iter(list(self._bots.values()))

    def __len__(self) -> int:
        return len(self._bots)

    def __getitem__(self, address: str) -> Bot:
        return self._bots[address]

    @property
    def bots(self) -> list[Bot]:
        return list(self._bots.values())

    # ---- fleet + link ---------------------------------------------------

    @property
    def all(self) -> Fleet:
        return Fleet(self._bots.values())

    def select(self, predicate: Callable[[Bot], bool]) -> Fleet:
        return Fleet(bot for bot in self._bots.values() if predicate(bot))

    @property
    def link(self) -> LinkProfile | None:
        # TODO: read GET /controller/link once the endpoint exists; until then
        # report a minimal Mari profile (host position rate, no gateway budget).
        return LinkProfile(kind=self._backend.kind, position_rate_hz=2.0, gateways=())

    # ---- events + telemetry --------------------------------------------

    def on(self, event_type: type[Event], callback: Callable[[Event], object]) -> None:
        """Register `callback(event)` for an Event class (e.g.
        `swarm.on(PositionUpdate, cb)`). The callback may be sync or async
        (async is scheduled). Register on `Event` to receive every event."""
        self._handlers.setdefault(event_type, []).append(callback)

    def _emit(self, event: Event) -> None:
        for event_type in (type(event), Event):
            for callback in self._handlers.get(event_type, ()):
                result = callback(event)
                if asyncio.iscoroutine(result):
                    self._schedule(result)
        for queue in self._event_queues:
            queue.put_nowait(event)

    async def events(self) -> AsyncIterator[Event]:
        """Async-iterate discrete events: `async for event in swarm.events():`."""
        queue: asyncio.Queue = asyncio.Queue()
        self._event_queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._event_queues.discard(queue)

    async def positions(
        self, *, rate_hz: float | None = None
    ) -> AsyncIterator[dict[str, Position]]:
        """Yield `{address: Position}` snapshots at a declared rate. `rate_hz`
        None clamps to the link's host position rate; a higher request is
        clamped with a one-time notice - you cannot sample faster than the link
        reports."""
        max_rate = self.link.position_rate_hz if self.link else None
        if rate_hz is None:
            rate_hz = max_rate or 2.0
        elif max_rate and rate_hz > max_rate:
            if not self._positions_clamped:
                self._positions_clamped = True
                LOGGER.warning(
                    "positions rate clamped to link budget",
                    requested_hz=rate_hz,
                    link_hz=max_rate,
                )
            rate_hz = max_rate
        period = 1.0 / rate_hz
        while True:
            yield {
                address: bot.position
                for address, bot in self._bots.items()
                if bot.position is not None
            }
            await asyncio.sleep(period)

    async def tick(self, rate_hz: float = 10) -> AsyncIterator[None]:
        """Yield once per control cycle at `rate_hz`, paced (drift-corrected) for
        budget-aware control loops. For swarm-wide per-bot commands, keep
        `rate_hz` at or below the link bottleneck's per-bot command rate; a
        higher rate is flagged once - you can issue commands faster than the link
        drains them, but they queue."""
        bottleneck = self.link.bottleneck if self.link else None
        if (
            bottleneck is not None
            and rate_hz > bottleneck.per_bot_command_rate_hz
            and not self._tick_warned
        ):
            self._tick_warned = True
            LOGGER.warning(
                "tick rate exceeds per-bot command budget",
                requested_hz=rate_hz,
                budget_hz=bottleneck.per_bot_command_rate_hz,
            )
        period = 1.0 / rate_hz
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            yield
            next_tick += period
            delay = next_tick - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = loop.time()  # body overran the period; resync

    async def close(self) -> None:
        # Flush pending fire-and-forget commands (e.g. a final stop()) before
        # tearing down, so they are not lost on shutdown - cancelling them would
        # strand a bot mid-move. Bounded so a stuck async callback can't hang us.
        pending = [t for t in self._tasks if not t.done()]
        if pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True), timeout=2.0
                )
            except asyncio.TimeoutError:
                for task in pending:
                    task.cancel()
        await self._backend.close()

    # ---- launcher -------------------------------------------------------

    @classmethod
    def run(cls, fn: Callable, *, conn: str | None = None) -> None:
        """Parse argv (--swarm-url, or --host/--port), connect, run `fn(swarm)`,
        and tear down on Ctrl-C. The zero-ceremony entry point for scripts."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--swarm-url", default=conn or "http://localhost:8000")
        parser.add_argument("--host", default=None)
        parser.add_argument("--port", type=int, default=8000)
        args, _ = parser.parse_known_args()
        url = f"http://{args.host}:{args.port}" if args.host else args.swarm_url

        async def _main() -> None:
            async with cls.connect(url) as swarm:
                await fn(swarm)

        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            pass
