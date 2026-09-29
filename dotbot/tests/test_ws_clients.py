import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from dotbot.controller import Controller, ControllerSettings
from dotbot.models import ApplicationType, DotBotModel, DotBotStatus
from dotbot.server import api
from dotbot.stream import STALL_S, StreamOptions
from dotbot.ws_clients import (
    TRANSPORT_KEY,
    TransportScope,
    close_websocket,
    write_buffer_size,
)


class StuckWebSocket:
    """A client that never reads: every send blocks forever."""

    def __init__(self):
        self.close = AsyncMock()

    async def send_text(self, message):
        await asyncio.Event().wait()


class BackloggedWebSocket(StuckWebSocket):
    """A client that stopped reading: its close frame never gets through."""

    def __init__(self, write_buffer=0, closing=True):
        async def close():
            await asyncio.Event().wait()

        self.close = AsyncMock(side_effect=close)
        self.transport = MagicMock()
        self.transport.get_write_buffer_size.return_value = write_buffer
        self.transport.is_closing.return_value = closing
        self.scope = {TRANSPORT_KEY: self.transport}


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.flush", MagicMock()
    )
    _controller = Controller(
        ControllerSettings(
            port="/dev/null", baudrate=115200, network_id="0", gw_address="78"
        )
    )
    _controller.send_waypoints = MagicMock()
    _controller.dotbots["4242"] = DotBotModel(
        address="4242",
        application=ApplicationType.DotBot,
        status=DotBotStatus.ACTIVE,
        last_seen=time.time(),
    )
    previous = getattr(api, "controller", None)
    api.controller = _controller
    yield _controller
    for websocket in list(_controller.stream.clients):
        _controller.stream.remove(websocket)
    api.controller = previous


@pytest.mark.asyncio
async def test_a_put_returns_while_a_stream_client_never_reads(controller):
    """A stuck console never delays a REST command."""
    stuck = StuckWebSocket()
    stream_client = controller.stream.client(stuck, StreamOptions())
    controller.stream.add(stream_client)
    client = AsyncClient(transport=ASGITransport(app=api), base_url="http://test")
    while stream_client.sending_since is None:
        await asyncio.sleep(0.01)
    for _ in range(3):
        # A PUT held behind the stuck send would wait for the STALL_S drop
        response = await asyncio.wait_for(
            client.put(
                "/controller/dotbots/4242/0/waypoints",
                json={"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
            ),
            timeout=STALL_S / 5,
        )
        assert response.status_code == 200
        assert stream_client.sending_since is not None


def test_the_write_buffer_is_read_from_the_transport():
    assert write_buffer_size(BackloggedWebSocket(write_buffer=4096)) == 4096
    assert write_buffer_size(StuckWebSocket()) == 0


@pytest.mark.asyncio
async def test_a_close_that_stalls_is_aborted():
    websocket = BackloggedWebSocket(closing=False)
    await close_websocket(websocket, timeout=0.05)
    websocket.transport.abort.assert_called_once()


@pytest.mark.asyncio
async def test_a_close_behind_a_backlog_is_aborted():
    websocket = BackloggedWebSocket(write_buffer=65536)
    websocket.close = AsyncMock()
    await close_websocket(websocket, timeout=0.05)
    websocket.close.assert_awaited()
    websocket.transport.abort.assert_called_once()


@pytest.mark.asyncio
async def test_a_close_the_client_never_answers_is_aborted():
    websocket = BackloggedWebSocket(closing=False)
    websocket.close = AsyncMock()
    await close_websocket(websocket, timeout=0.1)
    websocket.transport.abort.assert_called_once()


@pytest.mark.asyncio
async def test_a_clean_close_is_not_aborted():
    websocket = BackloggedWebSocket()
    websocket.close = AsyncMock()
    await close_websocket(websocket, timeout=0.05)
    websocket.close.assert_awaited_once()
    websocket.transport.abort.assert_not_called()


@pytest.mark.asyncio
async def test_the_transport_is_found_from_the_server_send():
    class Protocol:
        transport = object()

        async def send(self, message):
            pass

    seen = {}

    async def app(scope, receive, send):
        seen.update(scope)

    protocol = Protocol()
    await TransportScope(app)({"type": "websocket"}, None, protocol.send)
    assert seen[TRANSPORT_KEY] is protocol.transport


def test_transport_scope_is_the_outermost_middleware():
    assert api.user_middleware[0].cls is TransportScope


@pytest.mark.asyncio
async def test_uvicorn_hands_transport_scope_the_real_transport():
    """Against a real uvicorn server, a websocket's scope carries the
    connection's transport, so a server release that stops exposing it
    fails here rather than leaving write_buffer_size() silently at 0."""
    import socket

    import uvicorn
    from fastapi import FastAPI, WebSocket
    from websockets.asyncio.client import connect

    app = FastAPI()
    app.add_middleware(TransportScope)
    seen = {}

    @app.websocket("/ws")
    async def endpoint(websocket: WebSocket):
        await websocket.accept()
        seen["transport"] = websocket.scope.get(TRANSPORT_KEY)
        seen["buffered"] = write_buffer_size(websocket)
        await websocket.send_text("ok")
        await websocket.close()

    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
    except OSError as exc:
        sock.close()
        pytest.skip(f"cannot bind a loopback port: {exc}")
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", timeout_graceful_shutdown=0)
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        async with connect(f"ws://127.0.0.1:{port}/ws") as websocket:
            assert await websocket.recv() == "ok"
    finally:
        server.should_exit = True
        await task
        sock.close()
    assert isinstance(seen["transport"], asyncio.Transport)
    assert seen["buffered"] == 0
