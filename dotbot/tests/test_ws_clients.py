import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from dotbot.controller import Controller, ControllerSettings
from dotbot.models import ApplicationType, DotBotModel, DotBotStatus
from dotbot.server import api
from dotbot.stream import StreamOptions
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
    controller.stream.add(controller.stream.client(stuck, StreamOptions()))
    client = AsyncClient(transport=ASGITransport(app=api), base_url="http://test")
    await asyncio.sleep(0.1)
    for _ in range(3):
        start = time.monotonic()
        response = await client.put(
            "/controller/dotbots/4242/0/waypoints",
            json={"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
        )
        assert response.status_code == 200
        assert time.monotonic() - start < 0.1


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
