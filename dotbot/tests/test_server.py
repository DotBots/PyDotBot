import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from dotbot.models import (
    DotBotCalibrationStateModel,
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
)
from dotbot.protocol import (
    ApplicationType,
    Frame,
    Header,
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
    api.controller.lh2_manager = MagicMock()
    api.controller.lh2_manager.state_model = DotBotCalibrationStateModel(state="test")
    api.controller.notify_clients = AsyncMock()
    api.controller.send_payload = MagicMock()
    api.controller.settings = MagicMock()
    api.controller.settings.gw_address = "0000"
    api.controller.settings.swarm_id = "0000"


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
    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
    payload = PayloadCommandMoveRaw(**command.model_dump())
    expected_frame = Frame(header=header, payload=payload)
    response = await client.put(
        f"/controller/dotbots/{address}/0/move_raw",
        json=command.model_dump(),
    )
    assert response.status_code == code
    if found is True:
        api.controller.send_payload.assert_called_with(expected_frame)
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
    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
    payload = PayloadCommandRgbLed(**command.model_dump())
    expected_frame = Frame(header=header, payload=payload)
    response = await client.put(
        f"/controller/dotbots/{address}/0/rgb_led",
        json=command.model_dump(),
    )
    assert response.status_code == code

    if found:
        api.controller.send_payload.assert_called_with(expected_frame)
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
    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
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

    expected_frame = Frame(header=header, payload=payload)
    response = await client.put(
        f"/controller/dotbots/{address}/{application.value}/waypoints",
        json=message,
    )
    assert response.status_code == code

    if found:
        api.controller.send_payload.assert_called_with(expected_frame)
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
async def test_lh2_calibration():
    response = await client.get("/controller/lh2/calibration")
    assert response.json() == DotBotCalibrationStateModel(state="test").model_dump()
    assert response.status_code == 200

    with patch(
        "dotbot.server.api.controller.lh2_manager.add_calibration_point"
    ) as point:
        response = await client.post(
            "/controller/lh2/calibration/2",
        )
        assert response.status_code == 200
        point.assert_called_with(2)

    with patch(
        "dotbot.server.api.controller.lh2_manager.compute_calibration"
    ) as calibration:
        response = await client.put(
            "/controller/lh2/calibration",
        )
        assert response.status_code == 200
        calibration.assert_called_once()


@pytest.mark.asyncio
async def test_ws_client():
    with TestClient(api).websocket_connect("/controller/ws/status") as websocket:
        await asyncio.sleep(0.1)
        assert len(api.controller.websockets) == 1
        websocket.close()
        await asyncio.sleep(0.1)
        assert len(api.controller.websockets) == 0


# @pytest.mark.asyncio
# @patch("uvicorn.Server.serve")
# async def test_web(serve, caplog):
#     caplog.set_level(logging.DEBUG, logger="pydotbot")
#     with pytest.raises(SystemExit):
#         await web(None)
#     serve.side_effect = asyncio.exceptions.CancelledError()
#     await web(None)
#     assert "Web server cancelled" in caplog.text
