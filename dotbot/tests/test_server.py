import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from dotbot.models import (
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
    WSMoveRaw,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.protocol import (
    ApplicationType,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLH2Waypoints,
)
from dotbot.server import api

client = AsyncClient(transport=ASGITransport(app=api), base_url="http://testserver")


@pytest.fixture(autouse=True)
def controller():
    api.controller = MagicMock()
    api.controller.websockets = []
    api.controller.header = MagicMock()
    api.controller.header.destination = MagicMock()
    api.controller.dotbots = MagicMock()
    api.controller.get_dotbots = MagicMock()
    api.controller.notify_clients = AsyncMock()
    api.controller.send_payload = MagicMock()
    api.controller.settings = MagicMock()
    api.controller.settings.gw_address = "0000"
    api.controller.settings.network_id = "0000"


@pytest.mark.asyncio
async def test_openapi_exists():
    response = await client.get("/api")
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,code,found",
    [
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
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
                    application=ApplicationType.DotBot,
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
async def test_set_dotbots_move_raw(dotbots, code, found):
    api.controller.dotbots = dotbots
    address = "4242"
    command = DotBotMoveRawCommandModel(left_x=42, left_y=0, right_x=42, right_y=0)
    payload = PayloadCommandMoveRaw(**command.model_dump())
    response = await client.put(
        f"/controller/dotbots/{address}/0/move_raw",
        json=command.model_dump(),
    )
    assert response.status_code == code
    if found is True:
        api.controller.send_payload.assert_called_with(int(address, 16), payload)
    else:
        api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,code,found",
    [
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
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
                    application=ApplicationType.DotBot,
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
async def test_set_dotbots_rgb_led(dotbots, code, found):
    api.controller.dotbots = dotbots
    address = "4242"
    command = DotBotRgbLedCommandModel(red=42, green=0, blue=42)
    payload = PayloadCommandRgbLed(**command.model_dump())
    response = await client.put(
        f"/controller/dotbots/{address}/0/rgb_led",
        json=command.model_dump(),
    )
    assert response.status_code == code

    if found:
        api.controller.send_payload.assert_called_with(int(address, 16), payload)
    else:
        api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,has_position,application,message,code,found",
    [
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            False,
            ApplicationType.DotBot,
            {"threshold": 10, "waypoints": [{"x": 0.5, "y": 0.1, "z": 0}]},
            200,
            True,
            id="dotbot_found",
        ),
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                    lh2_position=DotBotLH2Position(x=0.1, y=0.5, z=0),
                ),
            },
            True,
            ApplicationType.DotBot,
            {"threshold": 10, "waypoints": [{"x": 0.5, "y": 0.1, "z": 0}]},
            200,
            True,
            id="dotbot_with_position_found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            False,
            ApplicationType.DotBot,
            {"threshold": 10, "waypoints": [{"x": 0.5, "y": 0.1, "z": 0}]},
            404,
            False,
            id="dotbot_not_found",
        ),
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            False,
            ApplicationType.SailBot,
            {"threshold": 10, "waypoints": [{"latitude": 0.5, "longitude": 0.1}]},
            200,
            True,
            id="sailbot_found",
        ),
        pytest.param(
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                    gps_position=DotBotGPSPosition(latitude=0.1, longitude=0.5),
                ),
            },
            True,
            ApplicationType.SailBot,
            {"threshold": 10, "waypoints": [{"latitude": 0.5, "longitude": 0.1}]},
            200,
            True,
            id="sailbot_with_position_found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            False,
            ApplicationType.SailBot,
            {"threshold": 10, "waypoints": [{"latitude": 0.5, "longitude": 0.1}]},
            404,
            False,
            id="sailbot_not_found",
        ),
    ],
)
async def test_set_dotbots_waypoints(
    dotbots, has_position, application, message, code, found
):
    api.controller.dotbots = dotbots
    address = "4242"
    if application == ApplicationType.SailBot:
        payload = PayloadGPSWaypoints(
            threshold=10,
            count=1,
            waypoints=[PayloadGPSPosition(latitude=500000, longitude=100000)],
        )
        expected_threshold = 10
        if has_position is True:
            expected_waypoints = [
                DotBotGPSPosition(latitude=0.1, longitude=0.5),
                DotBotGPSPosition(latitude=0.5, longitude=0.1),
            ]
        else:
            expected_waypoints = [DotBotGPSPosition(latitude=0.5, longitude=0.1)]
    else:  # DotBot application
        payload = PayloadLH2Waypoints(
            threshold=10,
            count=1,
            waypoints=[PayloadLH2Location(pos_x=500000, pos_y=100000, pos_z=0)],
        )
        expected_threshold = 10
        if has_position is True:
            expected_waypoints = [
                DotBotLH2Position(x=0.1, y=0.5, z=0),
                DotBotLH2Position(x=0.5, y=0.1, z=0),
            ]
        else:
            expected_waypoints = [DotBotLH2Position(x=0.5, y=0.1, z=0)]

    response = await client.put(
        f"/controller/dotbots/{address}/{application.value}/waypoints",
        json=message,
    )
    assert response.status_code == code

    if found:
        api.controller.send_payload.assert_called_with(int(address, 16), payload)
        assert api.controller.dotbots[address].waypoints == expected_waypoints
        assert api.controller.dotbots[address].waypoints_threshold == expected_threshold
    else:
        api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,result",
    [
        pytest.param({}, [], id="empty"),
        pytest.param(
            {
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            [
                DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ).model_dump(exclude_none=True),
            ],
            id="one",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            [
                DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ).model_dump(exclude_none=True),
                DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ).model_dump(exclude_none=True),
            ],
            id="sorted",
        ),
    ],
)
async def test_get_dotbots(dotbots, result):
    api.controller.get_dotbots.return_value = list(
        sorted(dotbots.values(), key=lambda dotbot: dotbot.address)
    )
    response = await client.get("/controller/dotbots")
    assert response.status_code == 200
    assert response.json() == result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,address,code,found,result",
    [
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            "12345",
            200,
            True,
            DotBotModel(
                address="12345",
                application=ApplicationType.DotBot,
                swarm="0000",
                last_seen=123.4,
            ).model_dump(exclude_none=True),
            id="found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
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
async def test_get_dotbot(dotbots, address, code, found, result):
    api.controller.dotbots = dotbots
    response = await client.get(f"/controller/dotbots/{address}")
    assert response.status_code == code
    if found is True:
        assert response.json() == result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dotbots,address,code,found",
    [
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                    position_history=[
                        DotBotLH2Position(x=0.0, y=0.5, z=0.0),
                        DotBotLH2Position(x=0.5, y=0.5, z=0.0),
                    ],
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                    position_history=[
                        DotBotLH2Position(x=0.5, y=0.5, z=0.0),
                        DotBotLH2Position(x=0.5, y=0.0, z=0.0),
                    ],
                ),
            },
            "12345",
            200,
            True,
            id="dotbot_found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            "34567",
            404,
            False,
            id="dotbot_not_found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                    position_history=[
                        DotBotGPSPosition(latitude=45.7597, longitude=4.8422),
                        DotBotGPSPosition(latitude=48.8567, longitude=2.3508),
                    ],
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                    position_history=[
                        DotBotGPSPosition(latitude=51.509865, longitude=-0.118092),
                        DotBotGPSPosition(latitude=48.8567, longitude=2.3508),
                    ],
                ),
            },
            "34567",
            404,
            False,
            id="sailbot_found",
        ),
        pytest.param(
            {
                "56789": DotBotModel(
                    address="56789",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                ),
            },
            "34567",
            404,
            False,
            id="sailbot_not_found",
        ),
    ],
)
async def test_clear_dotbot_position_history(dotbots, address, code, found):
    api.controller.dotbots = dotbots
    response = await client.delete(f"/controller/dotbots/{address}/positions")
    assert response.status_code == code
    if found is True:
        assert api.controller.dotbots[address].position_history == []


@pytest.mark.asyncio
async def test_ws_client():
    with TestClient(api).websocket_connect("/controller/ws/status") as websocket:
        await asyncio.sleep(0.1)
        assert len(api.controller.websockets) == 1
        websocket.close()
        await asyncio.sleep(0.1)
        assert len(api.controller.websockets) == 0


@pytest.mark.asyncio
async def test_reverse_proxy_middleware_redirects_to_upstream(monkeypatch):

    async def mock_send(request: httpx.Request):
        assert request.url == httpx.URL("http://localhost:8080/pin/test")

        return httpx.Response(
            status_code=200,
            content=b"proxied-content",
            headers={"X-Upstream": "mock"},
        )

    transport = httpx.MockTransport(mock_send)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)

    client = TestClient(api)
    response = client.get("/pin/test")

    assert response.status_code == 200
    assert response.content == b"proxied-content"
    assert response.headers["X-Upstream"] == "mock"


@pytest.mark.asyncio
async def test_reverse_proxy_middleware_connect_error(monkeypatch):

    async def mock_send_failed(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    transport = httpx.MockTransport(mock_send_failed)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)

    client = TestClient(api)
    response = client.get("/pin/fail")

    assert response.status_code == 502
    assert b"Proxy connection failed" in response.content


# @pytest.mark.asyncio
# @patch("uvicorn.Server.serve")
# async def test_web(serve, caplog):
#     caplog.set_level(logging.DEBUG, logger="pydotbot")
#     with pytest.raises(SystemExit):
#         await web(None)
#     serve.side_effect = asyncio.exceptions.CancelledError()
#     await web(None)
#     assert "Web server cancelled" in caplog.text


@pytest.mark.parametrize(
    "dotbots,ws_message,expected_payload,should_call",
    [
        pytest.param(
            # ---- RGB LED (valid) ----
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                )
            },
            WSRgbLed(
                cmd="rgb_led",
                address="4242",
                application=ApplicationType.DotBot,
                data=DotBotRgbLedCommandModel(
                    red=255,
                    green=0,
                    blue=128,
                ),
            ),
            PayloadCommandRgbLed(red=255, green=0, blue=128),
            True,
            id="rgb_led_valid",
        ),
        pytest.param(
            # ---- WAYPOINTS (valid) ----
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                )
            },
            WSWaypoints(
                cmd="waypoints",
                address="4242",
                application=ApplicationType.DotBot,
                data=DotBotWaypoints(
                    threshold=10,
                    waypoints=[DotBotLH2Position(x=0.5, y=0.1, z=0)],
                ),
            ),
            PayloadLH2Waypoints(
                threshold=10,
                count=1,
                waypoints=[PayloadLH2Location(pos_x=500000, pos_y=100000, pos_z=0)],
            ),
            True,
            id="waypoints_valid",
        ),
        pytest.param(
            # ---- MOVE_RAW (valid) ----
            {
                "4242": DotBotModel(
                    address="4242",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                )
            },
            WSMoveRaw(
                cmd="move_raw",
                address="4242",
                application=ApplicationType.DotBot,
                data=DotBotMoveRawCommandModel(
                    left_x=0,
                    left_y=100,
                    right_x=0,
                    right_y=100,
                ),
            ),
            PayloadCommandMoveRaw(
                left_x=0,
                left_y=100,
                right_x=0,
                right_y=100,
            ),
            True,
            id="move_raw_valid",
        ),
        pytest.param(
            # ---- UNKNOWN ADDRESS (ignored) ----
            {},
            WSRgbLed(
                cmd="rgb_led",
                address="4242",
                application=ApplicationType.DotBot,
                data=DotBotRgbLedCommandModel(
                    red=255,
                    green=0,
                    blue=128,
                ),
            ),
            None,
            False,
            id="address_not_found",
        ),
    ],
)
def test_ws_dotbots_commands(
    dotbots,
    ws_message,
    expected_payload,
    should_call,
):
    api.controller.dotbots = dotbots

    with TestClient(api).websocket_connect("/controller/ws/dotbots") as ws:
        ws.send_json(ws_message.model_dump())

    if should_call:
        api.controller.send_payload.assert_called()
        if expected_payload is not None:
            api.controller.send_payload.assert_called_with(
                int(ws_message.address, 16),
                expected_payload,
            )
    else:
        api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
def test_ws_invalid_message_validation_error():
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242",
            application=ApplicationType.DotBot,
            swarm="0000",
            last_seen=123.4,
        )
    }

    invalid_message = {
        # cmd doesn't match with data
        "cmd": "waypoints",
        "address": "4242",
        "data": {
            "red": 255,
            "green": 0,
            "blue": 0,
        },
    }

    with TestClient(api).websocket_connect("/controller/ws/dotbots") as ws:
        ws.send_json(invalid_message)

        response = ws.receive_json()

    assert response["error"] == "invalid_message"
    assert "details" in response
    assert isinstance(response["details"], list)

    api.controller.send_payload.assert_not_called()
