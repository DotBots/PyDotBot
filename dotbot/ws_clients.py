"""Transport-level helpers for the controller's websocket clients."""

import asyncio

from fastapi import WebSocket

from dotbot.logger import LOGGER

# Longest a close may take before the connection is aborted instead.
CLOSE_TIMEOUT = 1.0
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


def write_buffer_size(websocket: WebSocket) -> int:
    """Bytes sent to `websocket` and not yet written to its socket; 0 if unknown."""
    transport = _transport(websocket)
    if transport is None:
        return 0
    try:
        return transport.get_write_buffer_size()
    except Exception:  # pylint:disable=broad-exception-caught
        return 0


def abort_transport(websocket: WebSocket) -> bool:
    """Drop the connection now, discarding unsent data; False if unknown."""
    transport = _transport(websocket)
    if transport is None:
        return False
    transport.abort()
    return True


async def close_websocket(websocket: WebSocket, timeout: float = CLOSE_TIMEOUT):
    """Close a client's websocket, aborting the connection unless the client
    answers the close within `timeout` with nothing left unsent.

    The close frame queues behind whatever is still unsent, and the server
    keeps the connection until the client answers it, so a client that
    stopped reading would hold both forever; aborting frees them.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        await asyncio.wait_for(websocket.close(), timeout)
    except Exception:  # pylint:disable=broad-exception-caught
        pass
    transport = _transport(websocket)
    if transport is None:
        return
    while not transport.is_closing() and loop.time() < deadline:
        await asyncio.sleep(0.05)
    if transport.is_closing() and write_buffer_size(websocket) == 0:
        return
    transport.abort()
    LOGGER.bind(context=__name__).info("Aborted websocket client connection")
