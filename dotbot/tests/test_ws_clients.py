import asyncio
import json
import random
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from dotbot import ws_clients
from dotbot.controller import Controller, ControllerSettings
from dotbot.models import (
    ApplicationType,
    DotBotModel,
    DotBotNotificationCommand,
    DotBotStatus,
)
from dotbot.server import api
from dotbot.ws_clients import WsClient


class RecordingWebSocket:
    """A client that reads everything, at a small random pace."""

    def __init__(self):
        self.received = []
        self.close = AsyncMock()

    async def send_text(self, message):
        await asyncio.sleep(random.uniform(0, 0.002))
        self.received.append(message)


class StuckWebSocket:
    """A client that never reads: every send blocks forever."""

    def __init__(self):
        self.close = AsyncMock()

    async def send_text(self, message):
        await asyncio.Event().wait()


async def _until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        await asyncio.sleep(0.01)


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.flush", MagicMock()
    )
    monkeypatch.setattr(ws_clients, "SEND_TIMEOUT", 0.2)
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
    for client in list(_controller.websockets.values()):
        client.close()
    api.controller = previous


@pytest.mark.asyncio
async def test_a_put_returns_while_a_client_never_reads(controller):
    """A stuck console neither delays a REST command nor starves the others."""
    stuck, reading = StuckWebSocket(), RecordingWebSocket()
    controller.add_websocket(stuck)
    controller.add_websocket(reading)
    client = AsyncClient(transport=ASGITransport(app=api), base_url="http://test")

    for _ in range(3):
        start = time.monotonic()
        response = await client.put(
            "/controller/dotbots/4242/0/waypoints",
            json={"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
        )
        assert response.status_code == 200
        assert time.monotonic() - start < 0.1

    await _until(lambda: len(reading.received) == 3)
    update = json.loads(reading.received[0])
    assert update["cmd"] == DotBotNotificationCommand.UPDATE.value
    assert update["data"]["address"] == "4242"

    await _until(lambda: stuck not in controller.websockets)
    stuck.close.assert_awaited()
    assert reading in controller.websockets


@pytest.mark.asyncio
async def test_a_client_receives_its_messages_in_order():
    websocket = RecordingWebSocket()
    client = WsClient(websocket, MagicMock())
    for i in range(200):
        client.send(str(i))
    await _until(lambda: len(websocket.received) == 200)
    assert websocket.received == [str(i) for i in range(200)]
    client.close()


@pytest.mark.asyncio
async def test_a_client_that_overflows_its_queue_is_dropped():
    websocket = StuckWebSocket()
    on_drop = MagicMock()
    client = WsClient(websocket, on_drop, queue_size=3, send_timeout=10)
    for i in range(5):
        client.send(str(i))
    on_drop.assert_called_once_with(websocket)
    await _until(lambda: websocket.close.await_count == 1)


@pytest.mark.asyncio
async def test_a_client_whose_socket_fails_is_dropped():
    websocket = MagicMock()
    websocket.send_text = AsyncMock(side_effect=RuntimeError("closed"))
    websocket.close = AsyncMock()
    on_drop = MagicMock()
    client = WsClient(websocket, on_drop)
    client.send("x")
    await _until(lambda: on_drop.called)
    on_drop.assert_called_once_with(websocket)


@pytest.mark.asyncio
async def test_a_removed_client_gets_nothing_more(controller):
    websocket = RecordingWebSocket()
    controller.add_websocket(websocket)
    controller.remove_websocket(websocket)
    await controller._broadcast({"cmd": 0})
    await asyncio.sleep(0.05)
    assert websocket.received == []
    assert controller.websockets == {}
