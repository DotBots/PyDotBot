import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets import exceptions as websockets_exceptions

from dotbot.examples.qrkey_demo import QrKeyClient, QrKeyClientSettings
from dotbot.logger import setup_logging


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

    qrkey_controller_mock = MagicMock()
    qrkey_controller_mock.start.side_effect = qrkey_controller_start_mock
    monkeypatch.setattr(
        "dotbot.examples.qrkey_demo.client.QrkeyController",
        lambda *args, **kwargs: qrkey_controller_mock,
    )
    websocket_mock = WebsocketMock()

    async def recv_side_effect():
        await asyncio.sleep(0.1)  # simulate some delay in receiving messages
        return json.dumps({"type": "delta", "seq": 7, "robots": {}})

    websocket_mock.recv.side_effect = recv_side_effect
    monkeypatch.setattr(
        "dotbot.examples.qrkey_demo.client.connect",
        lambda *args, **kwargs: websocket_mock,
    )
    rest_client = MagicMock()
    monkeypatch.setattr("dotbot.examples.qrkey_demo.client.RestClient", rest_client)

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


@pytest.mark.asyncio
async def test_the_relay_forwards_stream_frames_and_acks_them(client, monkeypatch):
    """Each stream frame reaches MQTT /notify verbatim and is acked."""
    import dotbot.examples.qrkey_demo.client as module

    websocket = module.connect()
    client.qrkey = MagicMock()
    task = asyncio.create_task(client.start_ws_client())
    await asyncio.sleep(0.25)
    task.cancel()
    client.qrkey.publish.assert_any_call(
        "/notify", {"type": "delta", "seq": 7, "robots": {}}
    )
    websocket.send.assert_any_await(json.dumps({"ack": 7}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "closed",
    [
        websockets_exceptions.ConnectionClosedOK(None, None),
        websockets_exceptions.ConnectionClosedError(None, None),
        ConnectionRefusedError("refused"),
    ],
    ids=["ok", "error", "refused"],
)
async def test_the_relay_reconnects_and_resumes_where_it_left(monkeypatch, closed):
    """A closed or refused stream is reconnected with `since` and `run` of
    the last whole frame relayed."""
    import dotbot.examples.qrkey_demo.client as module

    monkeypatch.setattr(module, "RECONNECT_MIN_S", 0.001)
    frames = [
        [
            {"type": "hello", "run": "r1", "seq": 0},
            {"type": "snapshot", "seq": 5, "part": 1, "parts": 2, "robots": []},
            {"type": "snapshot", "seq": 5, "part": 2, "parts": 2, "robots": []},
            {"type": "delta", "seq": 9, "robots": {}},
            closed,
        ],
        [{"type": "hello", "run": "r1", "seq": 9}, asyncio.CancelledError()],
    ]
    urls = []

    def connect(url, **_kwargs):
        urls.append(url)
        websocket = WebsocketMock()
        script = iter(frames[len(urls) - 1])

        async def recv():
            item = next(script)
            if isinstance(item, BaseException):
                raise item
            return json.dumps(item)

        websocket.recv.side_effect = recv
        return websocket

    monkeypatch.setattr(module, "connect", connect)
    client = QrKeyClient(QrKeyClientSettings(), MagicMock())
    client.qrkey = MagicMock()
    with pytest.raises(asyncio.CancelledError):
        await client.start_ws_client()
    assert len(urls) == 2
    assert "since" not in urls[0]
    assert urls[1].endswith("&since=9&run=r1")
