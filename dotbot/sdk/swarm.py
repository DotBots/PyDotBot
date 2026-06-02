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
from typing import Callable, Iterator
from urllib.parse import urlparse

from dotbot.models import DotBotModel
from dotbot.sdk._backend import HttpBackend
from dotbot.sdk.bot import Bot
from dotbot.sdk.fleet import Fleet
from dotbot.sdk.link import LinkProfile


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
            self._bots[model.address] = Bot(self, model)
        else:
            bot._apply(model)

    def _on_reload(self) -> None:
        self._schedule(self._refetch())

    async def _refetch(self) -> None:
        for model in await self._backend.fetch_fleet():
            bot = self._bots.get(model.address)
            if bot is None:
                self._bots[model.address] = Bot(self, model)
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

    async def close(self) -> None:
        for task in list(self._tasks):
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
