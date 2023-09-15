import asyncio
import logging

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from httpx import AsyncClient
from fastapi.testclient import TestClient

from dotbot.models import (
    DotBotModel,
    DotBotAddressModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotCalibrationStateModel,
    DotBotControlModeModel,
    DotBotGPSPosition,
    DotBotLH2Position,
)
from dotbot.protocol import (
    ApplicationType,
    ProtocolHeader,
    ProtocolPayload,
    PayloadType,
    PROTOCOL_VERSION,
    CommandMoveRaw,
    CommandRgbLed,
    ControlMode,
    LH2Location,
    LH2Waypoints,
    GPSPosition,
    GPSWaypoints,
)
from dotbot.server import app, web


client = AsyncClient(app=app, base_url="http://testserver")


@pytest.fixture(autouse=True)
def controller():
    app.controller = MagicMock()
    app.controller.websockets = []
    app.controller.header = MagicMock()
    app.controller.header.destination = MagicMock()
    app.controller.dotbots = MagicMock()
    app.controller.get_dotbots = MagicMock()
    app.controller.lh2_manager = MagicMock()
    app.controller.lh2_manager.state_model = DotBotCalibrationStateModel(state="test")
    app.controller.notify_clients = AsyncMock()
    app.controller.send_payload = MagicMock()
    app.controller.settings = MagicMock()
    app.controller.settings.gw_address = "0000"
    app.controller.settings.swarm_id = "0000"


@pytest.mark.asyncio
async def test_openapi_exists():
    response = await client.get("/api")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_dotbot_address():
    result_address = "0000000000004242"
    result = DotBotAddressModel(address=result_address)
    app.controller.header.destination = int(result_address, 16)
    response = await client.get("/controller/dotbot_address")
    assert response.status_code == 200
    assert response.json() == result.model_dump()


@pytest.mark.asyncio
async def test_set_dotbot_address():
    new_address = "0000000000004242"
    response = await client.put(
        "/controller/dotbot_address",
        json=DotBotAddressModel(address=new_address).model_dump(),
    )
    assert response.status_code == 200
    assert app.controller.header.destination == int(new_address, 16)


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
    app.controller.dotbots = dotbots
    address = "4242"
    command = DotBotMoveRawCommandModel(left_x=42, left_y=0, right_x=42, right_y=0)
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(app.controller.settings.gw_address, 16),
        swarm_id=int(app.controller.settings.swarm_id, 16),
        application=ApplicationType.DotBot,
        version=PROTOCOL_VERSION,
    )
    expected_payload = ProtocolPayload(
        header,
        PayloadType.CMD_MOVE_RAW,
        CommandMoveRaw(42, 0, 42, 0),
    )
    response = await client.put(
        f"/controller/dotbots/{address}/0/move_raw",
        json=command.model_dump(),
    )
    assert response.status_code == code
    if found is True:
        app.controller.send_payload.assert_called_with(expected_payload)
    else:
        app.controller.send_payload.assert_not_called()


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
    app.controller.dotbots = dotbots
    address = "4242"
    command = DotBotRgbLedCommandModel(red=42, green=0, blue=42)
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(app.controller.settings.gw_address, 16),
        swarm_id=int(app.controller.settings.swarm_id, 16),
        application=ApplicationType.DotBot,
        version=PROTOCOL_VERSION,
    )
    expected_payload = ProtocolPayload(
        header,
        PayloadType.CMD_RGB_LED,
        CommandRgbLed(42, 0, 42),
    )
    response = await client.put(
        f"/controller/dotbots/{address}/0/rgb_led",
        json=command.model_dump(),
    )
    assert response.status_code == code

    if found:
        app.controller.send_payload.assert_called_with(expected_payload)
    else:
        app.controller.send_payload.assert_not_called()


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
async def test_set_dotbots_mode(dotbots, code, found):
    app.controller.dotbots = dotbots
    address = "4242"
    message = DotBotControlModeModel(mode=1)
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(app.controller.settings.gw_address, 16),
        swarm_id=int(app.controller.settings.swarm_id, 16),
        application=ApplicationType.DotBot,
        version=PROTOCOL_VERSION,
    )
    expected_payload = ProtocolPayload(
        header,
        PayloadType.CONTROL_MODE,
        ControlMode(1),
    )
    response = await client.put(
        f"/controller/dotbots/{address}/0/mode",
        json=message.model_dump(),
    )
    assert response.status_code == code

    if found:
        app.controller.send_payload.assert_called_with(expected_payload)
    else:
        app.controller.send_payload.assert_not_called()


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
    app.controller.dotbots = dotbots
    address = "4242"
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(app.controller.settings.gw_address, 16),
        swarm_id=int(app.controller.settings.swarm_id, 16),
        application=application,
        version=PROTOCOL_VERSION,
    )
    if application == ApplicationType.SailBot:
        expected_payload = ProtocolPayload(
            header,
            PayloadType.GPS_WAYPOINTS,
            GPSWaypoints(
                threshold=10, waypoints=[GPSPosition(latitude=500000, longitude=100000)]
            ),
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
        expected_payload = ProtocolPayload(
            header,
            PayloadType.LH2_WAYPOINTS,
            LH2Waypoints(threshold=10, waypoints=[LH2Location(500000, 100000, 0)]),
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
        app.controller.send_payload.assert_called_with(expected_payload)
        assert app.controller.dotbots[address].waypoints == expected_waypoints
        assert app.controller.dotbots[address].waypoints_threshold == expected_threshold
    else:
        app.controller.send_payload.assert_not_called()


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
    app.controller.get_dotbots.return_value = list(
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
    app.controller.dotbots = dotbots
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
    app.controller.dotbots = dotbots
    response = await client.delete(f"/controller/dotbots/{address}/positions")
    assert response.status_code == code
    if found is True:
        assert app.controller.dotbots[address].position_history == []


@pytest.mark.asyncio
async def test_lh2_calibration():
    response = await client.get("/controller/lh2/calibration")
    assert response.json() == DotBotCalibrationStateModel(state="test").model_dump()
    assert response.status_code == 200

    with patch(
        "dotbot.server.app.controller.lh2_manager.add_calibration_point"
    ) as point:
        response = await client.post(
            "/controller/lh2/calibration/2",
        )
        assert response.status_code == 200
        point.assert_called_with(2)

    with patch(
        "dotbot.server.app.controller.lh2_manager.compute_calibration"
    ) as calibration:
        response = await client.put(
            "/controller/lh2/calibration",
        )
        assert response.status_code == 200
        calibration.assert_called_once()


@pytest.mark.asyncio
async def test_ws_client():
    with TestClient(app).websocket_connect("/controller/ws/status") as websocket:
        await asyncio.sleep(0.1)
        assert len(app.controller.websockets) == 1
        websocket.close()
        await asyncio.sleep(0.1)
        assert len(app.controller.websockets) == 0


@pytest.mark.asyncio
@patch("uvicorn.Server.serve")
async def test_web(serve, caplog):
    caplog.set_level(logging.DEBUG, logger="pydotbot")
    with pytest.raises(SystemExit):
        await web(None)
    serve.side_effect = asyncio.exceptions.CancelledError()
    await web(None)
    assert "Web server cancelled" in caplog.text
