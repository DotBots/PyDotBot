"""Delivery of controller notifications to connected websocket clients."""

import asyncio
from typing import Callable, Optional

from fastapi import WebSocket, WebSocketDisconnect

from dotbot.logger import LOGGER

# Messages held for a client before it counts as not keeping up.
QUEUE_SIZE = 1000
# Longest a single send may take before the client counts as stuck.
SEND_TIMEOUT = 1.0
# Where `TransportScope` leaves a websocket's transport in its ASGI scope.
TRANSPORT_KEY = "dotbot.transport"


class TransportScope:
    """ASGI middleware putting a websocket's server transport in its scope.

    ASGI has no way to abort a connection, and the server's own close waits
    for everything already buffered to be sent first. Must be the outermost
    user middleware: only there is `send` still the server's bound method.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            protocol = getattr(send, "__self__", None)
            scope[TRANSPORT_KEY] = getattr(protocol, "transport", None)
        await self.app(scope, receive, send)


def _transport(websocket: WebSocket):
    return (getattr(websocket, "scope", None) or {}).get(TRANSPORT_KEY)


def abort_transport(websocket: WebSocket) -> bool:
    """Drop the connection now, discarding unsent data; False if unknown."""
    transport = _transport(websocket)
    if transport is None:
        return False
    transport.abort()
    return True


class WsClient:
    """One websocket client: a bounded outbound queue drained by its own task.

    `send` never waits. A client that overflows its queue, or whose send
    times out or fails, is dropped and its websocket closed; no message is
    ever skipped. Must be used from the event loop thread.
    """

    def __init__(
        self,
        websocket: WebSocket,
        on_drop: Callable[[WebSocket], None],
        queue_size: Optional[int] = None,
        send_timeout: Optional[float] = None,
    ):
        self.websocket = websocket
        self._on_drop = on_drop
        self._send_timeout = send_timeout or SEND_TIMEOUT
        self._queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=queue_size or QUEUE_SIZE
        )
        self._closed = False
        self.logger = LOGGER.bind(context=__name__)
        self._task = asyncio.create_task(self._run())

    def send(self, message: str):
        if self._closed:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self.drop("queue full")

    def close(self):
        """Stop delivering, without closing the websocket itself."""
        self._closed = True
        self._task.cancel()

    def _gone(self, code: int):
        """The client closed its end: forget it, there is nothing to close."""
        if self._closed:
            return
        self.logger.debug("Websocket client closed", code=code)
        self.close()
        self._on_drop(self.websocket)

    def drop(self, reason: str):
        """Stop delivering and close the websocket, so the client reconnects."""
        if self._closed:
            return
        self.logger.warning("Dropping websocket client", reason=reason)
        self.close()
        self._on_drop(self.websocket)
        asyncio.create_task(self._close_websocket())

    async def _close_websocket(self):
        # The close frame queues behind whatever is still unsent, so a client
        # that stopped reading never sees it: the connection is aborted instead,
        # which is what makes the browser reconnect.
        try:
            await asyncio.wait_for(self.websocket.close(), self._send_timeout)
            transport = _transport(self.websocket)
            closed = transport is None or transport.get_write_buffer_size() == 0
        except Exception:  # pylint:disable=broad-exception-caught
            closed = False
        if not closed and abort_transport(self.websocket):
            self.logger.info("Aborted websocket client connection")

    async def _run(self):
        while True:
            message = await self._queue.get()
            try:
                await asyncio.wait_for(
                    self.websocket.send_text(message), self._send_timeout
                )
            except asyncio.TimeoutError:
                self.drop("send timed out")
                return
            except asyncio.CancelledError:
                raise
            except WebSocketDisconnect as exc:
                self._gone(exc.code)
                return
            except Exception as exc:  # pylint:disable=broad-exception-caught
                self.drop(f"send failed: {exc}")
                return
