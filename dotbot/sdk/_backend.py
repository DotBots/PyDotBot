# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The HTTP connection backend for `Swarm.connect("http://...")`.

Talks to a running `dotbot run controller` two ways: the REST API (initial
fleet fetch + the write path, reusing `dotbot.rest.RestClient`) and the
`ws/status` websocket (live state push). It is a thin composition layer - it
holds no swarm state itself; it just forwards controller notifications to a
callback and exposes typed send methods.
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable

import websockets

from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient

# dotbot.models.DotBotNotificationCommand values carried on ws/status.
_NOTIF_RELOAD = 1
_NOTIF_UPDATE = 2
_NOTIF_NEW_DOTBOT = 4


class HttpBackend:
    """Connects to a controller over REST + the `ws/status` websocket."""

    kind = "http"

    def __init__(self, host: str, port: int, https: bool = False):
        self.host = host
        self.port = port
        self.https = https
        self._rest = RestClient(host, port, https)
        self._ws_task: asyncio.Task | None = None
        self._on_update: Callable[[dict], None] | None = None
        self._on_reload: Callable[[], None] | None = None
        self._closed = False

    @property
    def _ws_url(self) -> str:
        scheme = "wss" if self.https else "ws"
        return f"{scheme}://{self.host}:{self.port}/controller/ws/status"

    async def connect(
        self,
        on_update: Callable[[dict], None],
        on_reload: Callable[[], None],
    ) -> None:
        """Start the `ws/status` reader. `on_update(model_dict)` fires for each
        per-bot UPDATE (carrying a full DotBotModel); `on_reload()` fires when
        the fleet membership may have changed and a re-fetch is warranted."""
        self._on_update = on_update
        self._on_reload = on_reload
        self._ws_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    async for raw in ws:
                        self._dispatch(raw)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - reconnect on any drop
                if self._closed:
                    return
                await asyncio.sleep(0.5)

    def _dispatch(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        cmd = msg.get("cmd")
        if cmd == _NOTIF_UPDATE and isinstance(msg.get("data"), dict):
            if self._on_update is not None:
                self._on_update(msg["data"])
        elif cmd in (_NOTIF_RELOAD, _NOTIF_NEW_DOTBOT):
            if self._on_reload is not None:
                self._on_reload()

    async def fetch_fleet(self) -> list[DotBotModel]:
        return await self._rest.fetch_dotbots()

    async def send_rgb_led(
        self,
        address: str,
        application: ApplicationType,
        red: int,
        green: int,
        blue: int,
    ) -> None:
        await self._rest.send_rgb_led_command(
            address,
            DotBotRgbLedCommandModel(red=red, green=green, blue=blue),
            application,
        )

    async def send_move_raw(
        self,
        address: str,
        application: ApplicationType,
        left: tuple[int, int],
        right: tuple[int, int],
    ) -> None:
        await self._rest.send_move_raw_command(
            address,
            application,
            DotBotMoveRawCommandModel(
                left_x=left[0], left_y=left[1], right_x=right[0], right_y=right[1]
            ),
        )

    async def send_waypoints(
        self,
        address: str,
        application: ApplicationType,
        points: list[tuple[float, float]],
        threshold: int,
    ) -> None:
        await self._rest.send_waypoint_command(
            address,
            application,
            DotBotWaypoints(
                threshold=threshold,
                waypoints=[DotBotLH2Position(x=x, y=y) for x, y in points],
            ),
        )

    async def close(self) -> None:
        self._closed = True
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self._rest.close()
