import asyncio

from unittest.mock import MagicMock, patch

import pytest

from fastapi.testclient import TestClient

from dotbot.models import (
    DotBotModel,
    DotBotAddressModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
)
from dotbot.protocol import (
    ProtocolHeader,
    ProtocolPayload,
    PayloadType,
    PROTOCOL_VERSION,
    CommandMoveRaw,
    CommandRgbLed,
)
from dotbot.server import app, web


client = TestClient(app)


@pytest.fixture(autouse=True)
def controller():
    app.controller = MagicMock()
    app.controller.header = MagicMock()
    app.controller.header.destination = MagicMock()
    app.controller.dotbots = MagicMock()
    app.controller.send_payload = MagicMock()
    app.controller.settings = MagicMock()
    app.controller.settings.gw_address = "0000"
    app.controller.settings.swarm_id = "0000"


def test_openapi_exists():
    response = client.get("/api")
    assert response.status_code == 200


def test_get_dotbot_address():
    result_address = "0000000000004242"
    result = DotBotAddressModel(address=result_address)
    app.controller.header.destination = int(result_address, 16)
    response = client.get("/controller/dotbot_address")
    assert response.status_code == 200
    assert response.json() == result.dict()


def test_set_dotbot_address():
    new_address = "0000000000004242"
    response = client.put(
        "/controller/dotbot_address",
        json=DotBotAddressModel(address=new_address).dict(),
    )
    assert response.status_code == 200
    assert app.controller.header.destination == int(new_address, 16)


@pytest.mark.parametrize(
    "dotbots,code,found",
    [
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            200,
            True,
            id="found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            404,
            False,
            id="not_found",
        ),
    ],
)
def test_set_dotbots_move_raw(dotbots, code, found):
    app.controller.dotbots = dotbots
    address = "4242"
    command = DotBotMoveRawCommandModel(left_x=42, left_y=0, right_x=42, right_y=0)
    header = ProtocolHeader(
        int(address, 16),
        int(app.controller.settings.gw_address, 16),
        int(app.controller.settings.swarm_id, 16),
        PROTOCOL_VERSION,
    )
    expected_payload = ProtocolPayload(
        header,
        PayloadType.CMD_MOVE_RAW,
        CommandMoveRaw(42, 0, 42, 0),
    )
    response = client.put(
        f"/controller/dotbots/{address}/move_raw",
        json=command.dict(),
    )
    assert response.status_code == code
    if found is True:
        app.controller.send_payload.assert_called_with(expected_payload)
    else:
        app.controller.send_payload.assert_not_called()


@pytest.mark.parametrize(
    "dotbots,code,found",
    [
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            200,
            True,
            id="found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            404,
            False,
            id="not_found",
        ),
    ],
)
def test_set_dotbots_rgb_led(dotbots, code, found):
    app.controller.dotbots = dotbots
    address = "4242"
    command = DotBotRgbLedCommandModel(red=42, green=0, blue=42)
    header = ProtocolHeader(
        int(address, 16),
        int(app.controller.settings.gw_address, 16),
        int(app.controller.settings.swarm_id, 16),
        PROTOCOL_VERSION,
    )
    expected_payload = ProtocolPayload(
        header,
        PayloadType.CMD_RGB_LED,
        CommandRgbLed(42, 0, 42),
    )
    response = client.put(
        f"/controller/dotbots/{address}/rgb_led",
        json=command.dict(),
    )
    assert response.status_code == code

    if found:
        app.controller.send_payload.assert_called_with(expected_payload)
    else:
        app.controller.send_payload.assert_not_called()


@pytest.mark.parametrize(
    "dotbots,result",
    [
        pytest.param({}, [], id="empty"),
        pytest.param(
            {
                "12345": DotBotModel(
                    address=12345,
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            [
                DotBotModel(
                    address=12345,
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ).dict(exclude_none=True),
            ],
            id="one",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            [
                DotBotModel(
                    address="12345",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ).dict(exclude_none=True),
                DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ).dict(exclude_none=True),
            ],
            id="sorted",
        ),
    ],
)
def test_get_dotbots(dotbots, result):
    app.controller.dotbots = dotbots
    response = client.get("/controller/dotbots")
    assert response.status_code == 200
    assert response.json() == result


@pytest.mark.parametrize(
    "dotbots,address,code,found,result",
    [
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            "12345",
            200,
            True,
            DotBotModel(
                address="12345",
                application="DotBot",
                swarm="0000",
                last_seen=123.4,
            ).dict(exclude_none=True),
            id="found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application="DotBot",
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            "34567",
            404,
            False,
            None,
            id="not_found",
        ),
    ],
)
def test_get_dotbot(dotbots, address, code, found, result):
    app.controller.dotbots = dotbots
    response = client.get(f"/controller/dotbots/{address}")
    assert response.status_code == code
    if found is True:
        assert response.json() == result


@pytest.mark.asyncio
@patch("uvicorn.Server.serve")
async def test_web(serve, capsys):
    with pytest.raises(SystemExit):
        await web(None)
    serve.side_effect = asyncio.exceptions.CancelledError()
    await web(None)
    out, _ = capsys.readouterr()
    assert "Web server cancelled" in out
