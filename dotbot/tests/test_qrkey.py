import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets import exceptions as websockets_exceptions

from dotbot.logger import setup_logging
from dotbot.qrkey import QrKeyClient, QrKeyClientSettings


class WebsocketMock:
    def __init__(self):
        self.send = AsyncMock()
        self.recv = AsyncMock()
        self.close = AsyncMock()

    async def __aenter__(self, *args, **kwargs):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@pytest.fixture
def client(monkeypatch):
    """Create a client instance with mocked websocket and qrkey clients."""

    async def qrkey_controller_start_mock(*args, **kwargs):
        await asyncio.sleep(0.5)  # simulate some async work
        raise websockets_exceptions.ConnectionClosedError(1000, None)

    qrkey_controller_mock = AsyncMock()
    qrkey_controller_mock.start.side_effect = qrkey_controller_start_mock
    monkeypatch.setattr(
        "dotbot.qrkey.QrkeyController", lambda *args, **kwargs: qrkey_controller_mock
    )
    websocket_mock = WebsocketMock()

    async def recv_side_effect():
        await asyncio.sleep(0.1)  # simulate some delay in receiving messages
        return json.dumps({"cmd": 2, "data": {"address": "test_bot"}})

    websocket_mock.recv.side_effect = recv_side_effect
    monkeypatch.setattr("dotbot.qrkey.connect", lambda *args, **kwargs: websocket_mock)
    rest_client = MagicMock()
    monkeypatch.setattr("dotbot.qrkey.RestClient", rest_client)

    settings = QrKeyClientSettings(
        http_port=8001,
        http_host="localhost",
        webbrowser=False,
        verbose=False,
    )

    _client = QrKeyClient(settings, rest_client)

    yield _client


@pytest.mark.asyncio
async def test_qrkey_client_basic(client):
    """Test that the QrKeyClient can be instantiated and run without errors."""
    setup_logging(None, "debug", ["console"])
    await client.run()
