import asyncio
import contextlib
import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from dotbot.area import Area
from dotbot.controller import Controller, ControllerSettings
from dotbot.models import (
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotLH2Waypoint,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
    DotBotWheelVelocityCommandModel,
    WSMoveRaw,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.poses import device_pose, robot_pose
from dotbot.protocol import (
    DIRECTION_NONE,
    WAYPOINT_NO_HEADING,
    ApplicationType,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadCommandWheelVelocity,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLH2Waypoints,
)
from dotbot.robots import ROBOT_DEFAULT
from dotbot.server import api
from dotbot.site import Site
from dotbot.stream import robot_object
from dotbot.tests.camera_fixtures import (
    DEV_CORNER,
    delivering,
    wait_for_detection,
)

client = AsyncClient(transport=ASGITransport(app=api), base_url="http://testserver")


@pytest.fixture(autouse=True)
def controller():
    api.controller = MagicMock()
    api.controller.header = MagicMock()
    api.controller.header.destination = MagicMock()
    api.controller.dotbots = MagicMock()
    api.controller.send_payload = MagicMock()
    api.controller.settings = MagicMock()
    api.controller.settings.gw_address = "0000"
    api.controller.settings.network_id = "0000"
    api.controller.settings.site = None
    # The robot state bookkeeping is the real one, over `dotbots`
    api.controller.seq = 0
    api.controller.run_id = "0123456789ab"
    api.controller.records = {}
    api.controller.changed = {}
    api.controller.max_evicted = 0
    for name in (
        "_record",
        "_append_trail",
        "_changed",
        "update_dotbot",
        "seed_trail",
        "clear_trail",
        "matching",
    ):
        setattr(api.controller, name, getattr(Controller, name).__get__(api.controller))


def _serve(dotbots):
    """Serve `dotbots`, each carrying its `trail` as its trail."""
    api.controller.dotbots = {
        address: dotbot.model_copy(update={"trail": []})
        for address, dotbot in dotbots.items()
    }
    for address, dotbot in dotbots.items():
        api.controller.seed_trail(address, dotbot.trail)


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
async def test_set_dotbots_wheel_velocity(dotbots, code, found):
    api.controller.dotbots = dotbots
    address = "4242"
    command = DotBotWheelVelocityCommandModel(left_mm_s=-150, right_mm_s=200)
    payload = PayloadCommandWheelVelocity(left_mm_s=-150, right_mm_s=200)
    response = await client.put(
        f"/controller/dotbots/{address}/0/wheel_velocity",
        json=command.model_dump(),
    )
    assert response.status_code == code
    if found is True:
        api.controller.send_payload.assert_called_with(int(address, 16), payload)
    else:
        api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"left_mm_s": 701, "right_mm_s": 0}, id="left_above"),
        pytest.param({"left_mm_s": -701, "right_mm_s": 0}, id="left_below"),
        pytest.param({"left_mm_s": 0, "right_mm_s": 701}, id="right_above"),
        pytest.param({"left_mm_s": 0, "right_mm_s": -701}, id="right_below"),
        pytest.param({"left_mm_s": 1.5, "right_mm_s": 0}, id="non_integer"),
        pytest.param({"left_mm_s": 0}, id="missing_field"),
    ],
)
async def test_set_dotbots_wheel_velocity_rejects_invalid(body):
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242",
            application=ApplicationType.DotBot,
            swarm="0000",
            last_seen=123.4,
        ),
    }
    response = await client.put(
        "/controller/dotbots/4242/0/wheel_velocity",
        json=body,
    )
    assert response.status_code == 422
    api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("speed", [700, -700])
async def test_set_dotbots_wheel_velocity_accepts_the_bounds(speed):
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242",
            application=ApplicationType.DotBot,
            swarm="0000",
            last_seen=123.4,
        ),
    }
    response = await client.put(
        "/controller/dotbots/4242/0/wheel_velocity",
        json={"left_mm_s": speed, "right_mm_s": -speed},
    )
    assert response.status_code == 200
    api.controller.send_payload.assert_called_with(
        0x4242, PayloadCommandWheelVelocity(left_mm_s=speed, right_mm_s=-speed)
    )


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
            {"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
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
                    lh2_position=DotBotLH2Position(x=100, y=500),
                ),
            },
            True,
            ApplicationType.DotBot,
            {"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
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
            {"threshold": 100, "waypoints": [{"x": 500, "y": 100}]},
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
            threshold=100,
            count=1,
            waypoints=[PayloadLH2Location(pos_x=500, pos_y=100)],
        )
        expected_threshold = 100
        if has_position is True:
            expected_waypoints = [
                DotBotLH2Position(x=100, y=500),
                DotBotLH2Waypoint(x=500, y=100),
            ]
        else:
            expected_waypoints = [DotBotLH2Waypoint(x=500, y=100)]

    response = await client.put(
        f"/controller/dotbots/{address}/{application.value}/waypoints",
        json=message,
    )
    assert response.status_code == code

    if found and application == ApplicationType.DotBot:
        api.controller.send_waypoints.assert_called_with(address, payload)
        api.controller.send_payload.assert_not_called()
        assert api.controller.dotbots[address].waypoints == expected_waypoints
        assert api.controller.dotbots[address].waypoints_threshold == expected_threshold
    elif found:
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
    _serve(dotbots)
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
    _serve(dotbots)
    response = await client.get(f"/controller/dotbots/{address}")
    assert response.status_code == code
    if found is True:
        assert response.json() == result


@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected", [("", []), ("?trail=2", [3, 4])])
async def test_get_dotbot_returns_the_newest_trail_points(query, expected):
    _serve(
        {
            "12345": DotBotModel(
                address="12345",
                last_seen=123.4,
                trail=[DotBotLH2Position(x=i, y=i) for i in range(5)],
            )
        }
    )
    response = await client.get(f"/controller/dotbots/12345{query}")
    assert response.status_code == 200
    assert [p["x"] for p in response.json()["trail"]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/controller/dotbots", "/controller/dotbots?trail=5&body=1"]
)
async def test_the_whole_fleet_names_its_seq_and_run(path):
    _serve({"12345": DotBotModel(address="12345", last_seen=123.4)})
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["X-Controller-Seq"] == str(api.controller.seq)
    assert response.headers["X-Controller-Run"] == "0123456789ab"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/controller/dotbots/12345",
        "/controller/dotbots?address=12345",
        "/controller/dotbots?limit=1",
        "/controller/dotbots?min_battery=1",
    ],
)
async def test_part_of_the_fleet_names_no_seq_to_resume_from(path):
    _serve({"12345": DotBotModel(address="12345", last_seen=123.4)})
    response = await client.get(path)
    assert response.status_code == 200
    assert "X-Controller-Seq" not in response.headers
    assert "X-Controller-Run" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("trail", ["-1", "1001"])
async def test_a_trail_out_of_range_is_refused(trail):
    _serve({"12345": DotBotModel(address="12345", last_seen=123.4)})
    for path in ("/controller/dotbots", "/controller/dotbots/12345"):
        response = await client.get(f"{path}?trail={trail}")
        assert response.status_code == 422


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
                    trail=[
                        DotBotLH2Position(x=0.0, y=0.5),
                        DotBotLH2Position(x=0.5, y=0.5),
                    ],
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.DotBot,
                    swarm="0000",
                    last_seen=123.4,
                    trail=[
                        DotBotLH2Position(x=0.5, y=0.5),
                        DotBotLH2Position(x=0.5, y=0.0),
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
                    trail=[
                        DotBotGPSPosition(latitude=45.7597, longitude=4.8422),
                        DotBotGPSPosition(latitude=48.8567, longitude=2.3508),
                    ],
                ),
                "12345": DotBotModel(
                    address="12345",
                    application=ApplicationType.SailBot,
                    swarm="0000",
                    last_seen=123.4,
                    trail=[
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
async def test_clear_dotbot_trail(dotbots, address, code, found):
    _serve(dotbots)
    response = await client.delete(f"/controller/dotbots/{address}/positions")
    assert response.status_code == code
    if found is True:
        assert (
            robot_object(api.controller, address, 10, api.controller.seq)["trail"] == []
        )


@pytest.mark.asyncio
async def test_ws_stream_client():
    api.controller.stream.hello.return_value = '{"type": "hello"}'
    with TestClient(api).websocket_connect(
        "/controller/ws/stream?hz=4&trail=7&since=12&run=abc"
    ) as websocket:
        assert websocket.receive_json() == {"type": "hello"}
        websocket.send_text('{"ack": 3}')
        await asyncio.sleep(0.1)
        api.controller.stream.add.assert_called_once()
        options = api.controller.stream.client.call_args.args[1]
        assert (options.hz, options.trail, options.since, options.run) == (
            4,
            7,
            12,
            "abc",
        )
        websocket.close()
        await asyncio.sleep(0.1)
    socket = api.controller.stream.client.call_args.args[0]
    api.controller.stream.receive.assert_called_once_with(socket, '{"ack": 3}')
    api.controller.stream.remove.assert_called_once_with(socket)


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


class _MockByteStream(httpx.AsyncByteStream):
    """Streamable body for MockTransport responses (a plain `content=` body
    counts as already consumed, which the streaming proxy rejects)."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_swarmit_proxy_forwards(monkeypatch):

    async def mock_send(request: httpx.Request):
        assert request.url == httpx.URL("http://swarmit-host:9001/status")
        return httpx.Response(
            status_code=200,
            stream=_MockByteStream([b'{"response": {}}']),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(mock_send)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)
    api.controller.settings.swarmit_url = "http://swarmit-host:9001"

    client = TestClient(api)
    response = client.get("/swarmit/status")

    assert response.status_code == 200
    assert response.content == b'{"response": {}}'
    assert response.headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_swarmit_proxy_forwards_post_body(monkeypatch):

    async def mock_send(request: httpx.Request):
        assert request.url == httpx.URL("http://swarmit-host:9001/start")
        assert request.method == "POST"
        assert request.content == b'{"devices": []}'
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(
            status_code=200, stream=_MockByteStream([b'{"result": "ok"}'])
        )

    transport = httpx.MockTransport(mock_send)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)
    api.controller.settings.swarmit_url = "http://swarmit-host:9001"

    client = TestClient(api)
    response = client.post(
        "/swarmit/start",
        content=b'{"devices": []}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.content == b'{"result": "ok"}'


@pytest.mark.asyncio
async def test_swarmit_proxy_unreachable(monkeypatch):

    async def mock_send_failed(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    transport = httpx.MockTransport(mock_send_failed)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)
    api.controller.settings.swarmit_url = "http://swarmit-host:9001"

    client = TestClient(api)
    response = client.get("/swarmit/status")

    assert response.status_code == 502
    assert b"swarmit server unreachable" in response.content


def test_swarmit_proxy_without_a_server_is_404_and_reaches_nothing(monkeypatch):
    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", MagicMock())
    api.controller.settings.swarmit_url = None
    response = TestClient(api).get("/swarmit/status")
    assert response.status_code == 404
    server_module.httpx.AsyncClient.assert_not_called()


@pytest.mark.asyncio
async def test_mrta_proxy_forwards(monkeypatch):

    async def mock_send(request: httpx.Request):
        assert request.url == httpx.URL("http://mrta-host:9002/status")
        return httpx.Response(
            status_code=200,
            stream=_MockByteStream([b'{"state": "off", "bots": null, "detail": null}']),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(mock_send)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)
    api.controller.settings.mrta_url = "http://mrta-host:9002"

    client = TestClient(api)
    response = client.get("/mrta/status")

    assert response.status_code == 200
    assert response.content == b'{"state": "off", "bots": null, "detail": null}'


@pytest.mark.asyncio
async def test_mrta_proxy_unreachable(monkeypatch):

    async def mock_send_failed(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    transport = httpx.MockTransport(mock_send_failed)
    RealAsyncClient = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=transport, **kwargs)

    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", mock_async_client)
    api.controller.settings.mrta_url = "http://mrta-host:9002"

    client = TestClient(api)
    response = client.get("/mrta/status")

    assert response.status_code == 502
    assert b"MRTA mode server unreachable" in response.content


def test_mrta_proxy_without_a_server_is_404_and_reaches_nothing(monkeypatch):
    """`mrta_url` is unset by default: the proxy answers 404 without ever
    touching the network, which is also the signal the console uses to hide
    the MRTA control entirely rather than show it as unavailable."""
    import dotbot.server as server_module

    monkeypatch.setattr(server_module.httpx, "AsyncClient", MagicMock())
    api.controller.settings.mrta_url = None
    response = TestClient(api).get("/mrta/status")
    assert response.status_code == 404
    server_module.httpx.AsyncClient.assert_not_called()


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
                    waypoints=[DotBotLH2Position(x=500, y=100)],
                ),
            ),
            PayloadLH2Waypoints(
                threshold=10,
                count=1,
                waypoints=[PayloadLH2Location(pos_x=500, pos_y=100)],
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

    if should_call and isinstance(expected_payload, PayloadLH2Waypoints):
        # sent under a batch id, and resent until the robot confirms it
        api.controller.send_waypoints.assert_called_with(
            ws_message.address, expected_payload
        )
    elif should_call:
        api.controller.send_payload.assert_called()
        if expected_payload is not None:
            api.controller.send_payload.assert_called_with(
                int(ws_message.address, 16),
                expected_payload,
            )
    else:
        api.controller.send_payload.assert_not_called()


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


@pytest.mark.asyncio
async def test_connection_reports_an_mqtt_endpoint():
    api.controller.settings = ControllerSettings(
        adapter="cloud",
        mqtt_host="argus.example.org",
        mqtt_port=8883,
        mqtt_use_tls=True,
        network_id="A000",
        gw_address="0000000000000000",
    )

    result = await client.get("/controller/connection")

    assert result.status_code == 200
    assert result.json() == {
        "adapter": "cloud",
        "connection": "mqtts://argus.example.org:8883",
        "swarm_id": "A000",
        "gw_address": "0000000000000000",
    }


@pytest.mark.asyncio
async def test_connection_never_leaks_the_mqtt_credentials():
    """The route is reachable by any browser that can reach the controller."""
    api.controller.settings = ControllerSettings(
        adapter="cloud",
        mqtt_host="broker.example.org",
        mqtt_username="operator",
        mqtt_password="hunter2",
    )

    body = (await client.get("/controller/connection")).text

    assert "operator" not in body
    assert "hunter2" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter,expected",
    [
        ("dotbot-simulator", "simulator"),
        ("sailbot-simulator", "simulator"),
        ("edge", "/dev/ttyACM0"),
        ("serial", "/dev/ttyACM0"),
    ],
)
async def test_connection_reports_the_non_mqtt_adapters(adapter, expected):
    api.controller.settings = ControllerSettings(adapter=adapter, port="/dev/ttyACM0")

    result = await client.get("/controller/connection")

    assert result.json()["connection"] == expected


def test_the_controller_opens_the_console_when_it_is_built(tmp_path, monkeypatch):
    """No UI path when the console is not built; /console when it is."""
    import dotbot.server as server

    console = tmp_path / "console"
    monkeypatch.setattr(server, "CONSOLE_DIR", str(console))
    assert server.default_ui_path() is None

    console.mkdir()
    assert server.default_ui_path() == "/console"


@pytest.mark.asyncio
async def test_the_root_redirects_to_a_built_console(tmp_path):
    from fastapi import FastAPI

    from dotbot.server import mount_console

    (tmp_path / "index.html").write_text("<html></html>")
    app = FastAPI()
    assert mount_console(app, str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        result = await http.get("/", follow_redirects=False)
        console = await http.get("/console/")
    assert result.status_code == 307
    assert result.headers["location"] == "/console/"
    assert console.status_code == 200


@pytest.mark.asyncio
async def test_without_a_console_build_the_root_is_not_found(tmp_path):
    from fastapi import FastAPI

    from dotbot.server import mount_console

    app = FastAPI()
    assert not mount_console(app, str(tmp_path / "missing"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        result = await http.get("/", follow_redirects=False)
    assert result.status_code == 404


def test_the_api_binds_loopback_unless_asked_otherwise():
    """The REST/WS API is unauthenticated, so it is not on the LAN by default."""
    from dotbot.controller import ControllerSettings

    default = ControllerSettings(gw_address="78", network_id="0")
    assert default.controller_http_host == "127.0.0.1"

    wide = ControllerSettings(
        gw_address="78", network_id="0", controller_http_host="0.0.0.0"
    )
    assert wide.controller_http_host == "0.0.0.0"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "put"])
async def test_the_area_routes_are_gone(method):
    """Areas are a client-side layer, so the controller holds no set of them."""
    response = await getattr(client, method)(
        "/controller/area", **({} if method == "get" else {"json": {"area": []}})
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_device_poses():
    """The console sizes a robot placed from swarmit's STATUS from these."""
    origin = DotBotLH2Position(x=0, y=0)
    api.controller.device_poses.return_value = {
        "DotBotV3": device_pose("DotBotV3", origin)
    }
    response = await client.get("/controller/device_poses")
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["DotBotV3"]
    assert body["DotBotV3"]["heading_source"] == "none"
    assert body["DotBotV3"]["photodiode"] == {"x": 0, "y": 0}


@pytest.mark.asyncio
async def test_get_robot_models():
    """A client draws a pose's body from its model's shape, axle at the origin."""
    response = await client.get("/controller/robot_models")
    assert response.status_code == 200
    shape = response.json()["dotbot-v3"]
    assert shape["axle"] == {"x": 0.0, "y": 0.0}
    assert shape["photodiode"] == pytest.approx({"x": 0.0, "y": 53.5})
    assert shape["heading_deg"] == 0.0
    assert len(shape["outline"]) == 14


@pytest.mark.asyncio
async def test_get_controller_site():
    """The console draws the whole site, so it needs the extent, the areas in
    their declared order with their roles, and which one is the field."""
    api.controller.site = Site(
        name="c405-arena",
        anchor="the arena's top-left corner, against the door wall of C405",
        extent_mm=(2000, 4000),
        areas={
            "staging": Area(0, 2000, 2000, 2000, "staging", "staging"),
            "field": Area(0, 0, 2000, 2000, "field", "field"),
            "dev-corner": Area(1000, 0, 1000, 1000, "dev-corner", "corner"),
            "field+staging": Area(0, 0, 2000, 4000, "field+staging"),
        },
    )
    response = await client.get("/controller/site")
    assert response.status_code == 200
    assert response.json() == {
        "name": "c405-arena",
        "anchor": "the arena's top-left corner, against the door wall of C405",
        "extent_mm": [2000, 4000],
        "areas": [
            {
                "x": 0,
                "y": 2000,
                "w": 2000,
                "h": 2000,
                "name": "staging",
                "role": "staging",
            },
            {"x": 0, "y": 0, "w": 2000, "h": 2000, "name": "field", "role": "field"},
            {
                "x": 1000,
                "y": 0,
                "w": 1000,
                "h": 1000,
                "name": "dev-corner",
                "role": "corner",
            },
            {
                "x": 0,
                "y": 0,
                "w": 2000,
                "h": 4000,
                "name": "field+staging",
                "role": None,
            },
        ],
        "field": "field",
    }


def test_the_site_payload_reads_back_as_the_same_site():
    from dotbot.models import DotBotSiteModel

    site = Site(
        name="hall",
        anchor="north-west corner",
        extent_mm=(5000, 4000),
        areas={
            "pen": Area(0, 0, 10, 10, "pen", "corner"),
            "main": Area(5, 5, 10, 10, "main", "field"),
        },
    )
    model = DotBotSiteModel(**DotBotSiteModel.from_site(site).model_dump())
    assert model.field == "main"
    assert model.to_site() == site
    assert list(model.to_site().areas) == ["pen", "main"]


@pytest.mark.asyncio
async def test_get_controller_site_with_only_an_extent_names_its_literal_field():
    api.controller.site = Site(name="hall", extent_mm=(5000, 4000))
    response = await client.get("/controller/site")
    assert response.json()["field"] == "0,0,5000,4000"


@pytest.mark.asyncio
async def test_get_controller_site_with_nothing_measured():
    """A fresh install reports its neutral site rather than inventing a floor."""
    api.controller.site = Site()
    response = await client.get("/controller/site")
    assert response.status_code == 200
    assert response.json() == {
        "name": "default",
        "anchor": "",
        "extent_mm": None,
        "areas": [],
        "field": None,
    }


# --- The camera layer -------------------------------------------------------

# A registration the bench wrote: a GoPro over four sheets taped into
# dev-corner, kept verbatim. The synthetic fixture cannot stand in for it -
# it carries an integer source rather than a path, a camera mounted at
# right angles to the frame, and a millimetre residual off a real lens.
REAL_CAMERA_FILE = """
schema_version = 1
kind = "camera"
created = "2026-09-15T11:58:26Z"
id = "22248be43bde6d93"

[site]
name = "c405-arena"
anchor = "the corner where the arena's top wall meets the door wall of C405"

[camera]
area = "dev-corner"
source = 0
width = 1920
height = 1080
fps = 30.0
lens = "linear"
intrinsics = ""
reads = 25

[[marker]]
id = 0
dictionary = "DICT_4X4_50"
side_mm = 150.0
centre_mm = [1105.0, 148.5]
corners_mm = [[1030.0, 73.5], [1180.0, 73.5], [1180.0, 223.5], [1030.0, 223.5]]
corners_px = [[1242.114697265625, 231.2410723876953], [1256.7383544921875, 293.572138671875], [1178.2674755859375, 296.226279296875], [1166.2070458984374, 233.71604919433594]]

[[marker]]
id = 1
dictionary = "DICT_4X4_50"
side_mm = 150.0
centre_mm = [1895.0, 148.5]
corners_mm = [[1820.0, 73.5], [1970.0, 73.5], [1970.0, 223.5], [1820.0, 223.5]]
corners_px = [[1341.7293994140625, 640.3177685546875], [1365.4220361328125, 738.3996533203125], [1265.2443017578125, 744.503134765625], [1245.754013671875, 645.6232080078125]]

[[marker]]
id = 2
dictionary = "DICT_4X4_50"
side_mm = 150.0
centre_mm = [1105.0, 851.5]
corners_mm = [[1030.0, 776.5], [1180.0, 776.5], [1180.0, 926.5], [1030.0, 926.5]]
corners_px = [[861.4837182617188, 242.1832373046875], [863.3884350585937, 309.0532653808594], [777.52103515625, 311.58351806640627], [778.7485498046875, 243.72177368164063]]

[[marker]]
id = 3
dictionary = "DICT_4X4_50"
side_mm = 150.0
centre_mm = [1895.0, 851.5]
corners_mm = [[1820.0, 776.5], [1970.0, 776.5], [1970.0, 926.5], [1820.0, 926.5]]
corners_px = [[875.7261181640625, 665.2610791015625], [879.4344018554688, 767.0706884765625], [773.3879418945312, 774.3927294921875], [774.234970703125, 671.5585180664062]]

[homography]
matrix = [[0.026072884758520428, 3.1429353231686856, 355.3471468990013], [-2.023927532764786, 0.5321569056318636, 2473.0438679636], [-4.8016552004033726e-05, 0.0005987887309469123, 1.0]]
residual_mm = 3.125575236970499
span_mm = [[1030.0, 73.5], [1970.0, 73.5], [1970.0, 926.5], [1030.0, 926.5]]
"""


@pytest.fixture
def real_camera(tmp_path):
    """The bench's own registration, read back through the file loader."""
    from dotbot.camera.registration import read_camera_calibration_file

    path = tmp_path / "camera-2026-09-15T11-58-26Z-22248be4.toml"
    path.write_text(REAL_CAMERA_FILE, encoding="utf-8")
    return read_camera_calibration_file(path)


@contextlib.contextmanager
def registered(calibration, open_source=None, area=DEV_CORNER):
    """One camera service on the controller, started and torn down.

    Registered whether or not it started, so what the routes serve is the
    service's own `live`, not the fixture's choice of what to hand them.
    """
    from dotbot.camera.service import CameraService

    service = CameraService(calibration, area, open_source=open_source)
    started = service.start()
    api.controller.cameras = [service]
    try:
        yield service, started
    finally:
        service.stop()


def stream_parts(body):
    """The (head, payload) pairs of a `multipart/x-mixed-replace` body."""
    parts = []
    for chunk in body.split(b"--frame\r\n")[1:]:
        head, _, rest = chunk.partition(b"\r\n\r\n")
        assert b"Content-Type: image/jpeg" in head
        payload = rest[: -len(b"\r\n")]
        assert f"Content-Length: {len(payload)}".encode() in head
        parts.append((head, payload))
    return parts


@pytest.mark.asyncio
async def test_get_controller_cameras(synthetic_camera):
    """One descriptor per registered camera, keyed by the area it covers."""
    with registered(synthetic_camera) as (service, started):
        assert started
        response = await client.get("/controller/cameras")

    import numpy as np

    assert response.status_code == 200
    (described,) = response.json()
    # The synthetic frame looks down on a floor wider than the area, so the
    # camera's coverage swallows dev-corner whole.
    assert np.array(described.pop("coverage_mm")) == pytest.approx(
        np.array(
            [
                [540.1, -40.1],
                [2556.3, -40.0],
                [2583.7, 1109.2],
                [540.1, 1064.4],
            ]
        ),
        abs=0.1,
    )
    assert described == {
        "area": "dev-corner",
        "source": str(synthetic_camera.source),
        "mm_per_px": 2.0,
        "width": 500,
        "height": 500,
        "span_mm": [
            [1030.0, 73.5],
            [1970.0, 73.5],
            [1970.0, 926.5],
            [1030.0, 926.5],
        ],
        "residual_mm": synthetic_camera.residual_mm,
        "id": synthetic_camera.id,
        "lens": "linear",
        "detect": True,
    }


@pytest.mark.asyncio
async def test_the_camera_stream_carries_the_area_warped_into_its_raster(
    synthetic_camera,
):
    """The registration, end to end: the sheets land where the layout puts them.

    Decoding the four markers back out of the warped raster is what
    separates a stream that carries an image from one that carries the
    right image: a transposed or unscaled warp still returns a JPEG.
    """
    import cv2
    import numpy as np

    from dotbot.camera.capture import build_detector, detect_markers
    from dotbot.camera.raster import MM_PER_PX
    from dotbot.camera.sheets import marker_layout

    with registered(synthetic_camera):
        response = await client.get("/controller/cameras/dev-corner/stream")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "multipart/x-mixed-replace; boundary=frame"
    )
    parts = stream_parts(response.content)
    assert parts
    # Stamped when the frame was read off the device, so a reader can age it.
    stamp = float(parts[0][0].split(b"X-Timestamp: ")[1].split(b"\r\n")[0])
    assert time.time() - 60.0 < stamp <= time.time()

    raster = cv2.imdecode(np.frombuffer(parts[0][1], np.uint8), cv2.IMREAD_COLOR)
    assert raster.shape == (500, 500, 3)

    found = detect_markers(raster, build_detector())
    assert sorted(found) == [0, 1, 2, 3]
    for marker in marker_layout(DEV_CORNER):
        expected = np.array(
            [
                ((x - DEV_CORNER.x) / MM_PER_PX, (y - DEV_CORNER.y) / MM_PER_PX)
                for x, y in marker.corners_mm
            ]
        )
        assert found[marker.id] == pytest.approx(expected, abs=1.0)

    grey = cv2.cvtColor(raster, cv2.COLOR_BGR2GRAY)
    assert grey[250, 250] > 192  # the bare floor between the sheets


@pytest.mark.asyncio
async def test_one_camera_warp_serves_every_client(synthetic_camera):
    """Two viewers, one warp: the held frame is what both are sent."""
    with registered(synthetic_camera) as (service, _):
        first = await client.get("/controller/cameras/dev-corner/stream")
        warps = service.held()[1]
        second = await client.get("/controller/cameras/dev-corner/stream")

        assert service.held()[1] == warps
    assert stream_parts(first.content)[0][1] == stream_parts(second.content)[0][1]


@pytest.mark.asyncio
async def test_a_camera_that_does_not_open_is_a_missing_layer(real_camera):
    """Ordinary, not an error state: the controller serves everything else."""
    with registered(real_camera, open_source=delivering(opens=False)) as (
        service,
        started,
    ):
        assert not started
        assert not service.live

        listed = await client.get("/controller/cameras")
        stream = await client.get("/controller/cameras/dev-corner/stream")

    assert listed.json() == []
    assert stream.status_code == 404


@pytest.mark.asyncio
async def test_a_camera_delivering_another_mode_is_not_served(real_camera):
    """The homography describes the pixel grid it was solved on, and no other.

    A source back on a different mode still delivers a plausible picture,
    so serving it would put every position it implies out by the scale
    ratio. A missing layer makes someone look; a wrong one does not.
    """
    import numpy as np

    other_mode = np.full((720, 1280), 180, np.uint8)
    with registered(real_camera, open_source=delivering(other_mode)) as (
        service,
        started,
    ):
        assert not started
        assert service.live is False

        listed = await client.get("/controller/cameras")
        stream = await client.get("/controller/cameras/dev-corner/stream")

    assert listed.json() == []
    assert stream.status_code == 404


@pytest.mark.asyncio
async def test_a_camera_at_another_frame_rate_is_not_served(real_camera):
    """Same pixel grid, another rate: still not the camera that was solved."""
    import numpy as np

    lit = np.full((1080, 1920), 180, np.uint8)
    with registered(real_camera, open_source=delivering(lit, fps=60.0)) as (_, started):
        assert not started
        listed = await client.get("/controller/cameras")

    assert listed.json() == []


@pytest.mark.asyncio
async def test_the_camera_stream_404s_for_an_area_no_camera_covers(synthetic_camera):
    with registered(synthetic_camera):
        response = await client.get("/controller/cameras/annex/stream")

    assert response.status_code == 404
    assert "annex" in response.json()["detail"]


@pytest.mark.asyncio
async def test_the_latest_detection_is_served_over_rest(synthetic_camera):
    """The same record the WebSocket carries, for a script that polls."""
    with registered(synthetic_camera) as (service, started):
        assert started
        assert wait_for_detection(service) is not None
        response = await client.get("/controller/cameras/dev-corner/detection")
        missing = await client.get("/controller/cameras/annex/detection")

    assert response.status_code == 200
    body = response.json()
    assert body["area"] == "dev-corner"
    assert body["status"] == "none"
    assert body["robots"] == []
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_a_camera_registered_on_the_bench_describes_itself(real_camera):
    """The bench's own file: an integer source, and a real residual."""
    import numpy as np

    lit = np.full((1080, 1920), 180, np.uint8)
    with registered(real_camera, open_source=delivering(lit)) as (_, started):
        assert started
        response = await client.get("/controller/cameras")

    descriptor = response.json()[0]
    assert descriptor["source"] == 0
    assert descriptor["id"] == "22248be43bde6d93"
    assert descriptor["residual_mm"] == pytest.approx(3.1256, abs=1e-4)
    assert descriptor["width"] == 500 and descriptor["height"] == 500
    assert descriptor["span_mm"][0] == [1030.0, 73.5]


def test_the_camera_coverage_is_the_frame_rectangle_on_the_floor(real_camera):
    """The floor the camera can see, in the frame's own millimetres.

    The homography and the frame's size both hold for the whole
    registration, so this is one polygon per camera rather than an alpha
    channel on every frame. Checked by mapping it back through the inverse
    homography, which must land on the frame's four pixel corners.
    """
    import numpy as np

    from dotbot.camera.raster import coverage_mm

    coverage = coverage_mm(real_camera.matrix, real_camera.width, real_camera.height)
    inverse = np.linalg.inv(np.array(real_camera.matrix))
    mapped = np.array([inverse @ [x, y, 1.0] for x, y in coverage])
    assert (mapped[:, :2] / mapped[:, 2:]) == pytest.approx(
        np.array([[0.0, 0.0], [1919.0, 0.0], [1919.0, 1079.0], [0.0, 1079.0]]),
        abs=1e-6,
    )


def test_a_frame_crossing_the_horizon_describes_no_coverage_polygon():
    """Its image is not a polygon there, and no mask beats a wrong one."""
    from dotbot.camera.raster import coverage_mm

    crossing = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.01, -5.0]]
    assert coverage_mm(crossing, 1920, 1080) == []
    assert coverage_mm([], 1920, 1080) == []


@pytest.mark.asyncio
async def test_the_warp_has_no_source_outside_the_coverage_polygon(
    synthetic_camera,
):
    """What the polygon claims is what the warp does, on the same frame.

    The same registration on a frame cropped to its left 900 columns sees
    only part of dev-corner. Inside the polygon the raster carries floor;
    outside it the warp had nothing to read and left its border fill, which
    is what the console cuts away.
    """
    import dataclasses

    import cv2
    import numpy as np

    from dotbot.camera.raster import MM_PER_PX
    from dotbot.camera.service import CameraService

    columns = 900
    frame = cv2.imread(str(synthetic_camera.source))[:, :columns]
    cropped = dataclasses.replace(synthetic_camera, width=columns)
    service = CameraService(cropped, DEV_CORNER, open_source=delivering(frame, fps=0.0))
    assert service.start()
    try:
        jpeg, _ = service.held()
    finally:
        service.stop()

    raster = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    grey = cv2.cvtColor(raster, cv2.COLOR_BGR2GRAY)

    edge = max(x for x, _ in service.coverage_mm)
    assert DEV_CORNER.x < edge < DEV_CORNER.x + DEV_CORNER.w
    inside = int((edge - 40 - DEV_CORNER.x) / MM_PER_PX)
    outside = int((edge + 40 - DEV_CORNER.x) / MM_PER_PX)
    assert grey[250, inside] > 192  # the bare floor between the sheets
    assert grey[250, outside] == 0  # no source, so the warp's border fill


# --- The detection on the status WebSocket ----------------------------------


class CannedDetector:
    """A detector reporting the same pose on every frame."""

    def __init__(self, status="found"):
        self.status = status

    def detect(self, bgr, priors=(), stamp=None):
        from dotbot.camera.detection import Detection, Pose, RobotFix

        if self.status == "none":
            return Detection("none", 0, (), 1.0)
        pose = Pose(
            centre_px=(250.0, 250.0),
            heading_atan2_deg=52.5,
            green_flare=0.82,
            tmpl_margin=0.91,
            refined=True,
        )
        return Detection(
            self.status,
            1,
            (RobotFix(self.status, pose, "0000000000000001", stamp or 0.0),),
            12.5,
        )


@contextlib.contextmanager
def detecting(calibration, status="found"):
    """One camera on a real controller, detecting whatever `status` says."""
    import cv2

    from dotbot.camera.service import CameraService
    from dotbot.controller import Controller, ControllerSettings

    frame = cv2.imread(str(calibration.source))
    service = CameraService(
        calibration,
        DEV_CORNER,
        open_source=delivering(*([frame] * 20), fps=0.0),
        detector=CannedDetector(status),
    )
    controller = Controller.__new__(Controller)
    controller.settings = ControllerSettings()
    controller.cameras = [service]
    controller._camera_pushed = {}
    controller.seq = 0
    controller.events = {}
    assert service.start()
    assert wait_for_detection(service) is not None
    try:
        yield controller
    finally:
        service.stop()


@pytest.mark.asyncio
async def test_a_detection_reaches_the_console_once_per_warp(synthetic_camera):
    """One event per new warp, and none for a warp already pushed."""
    with detecting(synthetic_camera) as controller:
        await controller._push_camera_detections()
        seq, name, message = controller.events["camera_detection/dev-corner"]
        assert (seq, name) == (controller.seq, "camera_detection")
        assert message["area"] == "dev-corner"
        assert message["camera_id"] == synthetic_camera.id
        assert message["status"] == "found"
        assert message["candidates"] == 1
        assert message["elapsed_ms"] == 12.5
        assert message["sequence"] >= 1
        assert message["timestamp"] > 0
        assert message["rate_hz"] > 0

        (robot,) = message["robots"]
        assert robot["address"] == "0000000000000001"
        assert robot["status"] == "found"
        assert robot["timestamp"] == message["timestamp"]
        pose = robot["pose"]
        assert pose["heading_atan2_deg"] == 52.5
        assert pose["heading_deg"] == -37.5
        assert len(pose["outline_mm"]) == 14
        # The raster's (250, 250) is the middle of a 1000 mm area at 2 mm/px.
        assert pose["centre_mm"] == [1500.0, 500.0]

        await controller._push_camera_detections()
        assert controller.seq == seq


@pytest.mark.asyncio
async def test_a_detection_of_nothing_carries_no_pose(synthetic_camera):
    with detecting(synthetic_camera, status="none") as controller:
        await controller._push_camera_detections()
        _, _, message = controller.events["camera_detection/dev-corner"]
        assert message["status"] == "none"
        assert message["robots"] == []


@pytest.mark.asyncio
async def test_the_last_detection_is_kept_for_a_console_that_connects_late(
    synthetic_camera,
):
    """A camera that has stopped delivering pushes no further frame, so a
    console arriving afterwards would otherwise draw an empty floor."""
    with detecting(synthetic_camera) as controller:
        await controller._push_camera_detections()
        assert controller._camera_pushed["dev-corner"] >= 1
        assert "camera_detection/dev-corner" in controller.events


@pytest.mark.asyncio
async def test_set_dotbots_waypoints_poses():
    """Headings, the intermediate radius and the heading tolerance reach the
    wire: a heading in [0, 360) goes out as centidegrees in [-18000, 18000),
    a point without one as no heading."""
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242", application=ApplicationType.DotBot, last_seen=123.4
        )
    }
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints",
        json={
            "threshold": 5,
            "intermediate_threshold": 30,
            "heading_tolerance": 4,
            "waypoints": [
                {"x": 500, "y": 100},
                {"x": 600, "y": 100, "heading_deg": 270},
                {"x": 700, "y": 100, "heading_deg": -45.5},
                {"x": 800, "y": 100, "heading_deg": 180},
            ],
        },
    )
    assert response.status_code == 200
    address, payload = api.controller.send_waypoints.call_args.args
    assert address == "4242"
    assert (payload.threshold, payload.pass_mm, payload.heading_tol_deg) == (5, 30, 4)
    assert [h.heading_cdeg for h in payload.headings] == [
        WAYPOINT_NO_HEADING,
        -9000,
        -4550,
        -18000,
    ]
    stored = api.controller.dotbots["4242"].waypoints
    assert [w.heading_deg for w in stored] == [None, 270.0, 314.5, 180.0]


@pytest.mark.asyncio
async def test_set_dotbots_waypoints_empty_clears_the_batch():
    """The console clears a robot's waypoints with an empty batch: it goes
    out with no points, and the record keeps only where the robot stood."""
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242",
            application=ApplicationType.DotBot,
            last_seen=123.4,
            lh2_position=DotBotLH2Position(x=100, y=500),
            waypoints=[
                DotBotLH2Position(x=100, y=500),
                DotBotLH2Waypoint(x=900, y=900),
            ],
        )
    }
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints", json={"threshold": 10, "waypoints": []}
    )
    assert response.status_code == 200
    address, payload = api.controller.send_waypoints.call_args.args
    assert (address, payload.count, payload.waypoints) == ("4242", 0, [])
    assert api.controller.dotbots["4242"].waypoints == [DotBotLH2Position(x=100, y=500)]


@pytest.mark.asyncio
async def test_set_dotbots_waypoints_poses_echo_their_heading():
    """The console draws an active pose and repeats a mission from what the
    controller echoes, so a heading survives into the notification and the
    robot's record, after the robot's own start point."""
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242",
            application=ApplicationType.DotBot,
            last_seen=123.4,
            lh2_position=DotBotLH2Position(x=100, y=100),
        )
    }
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints",
        json={
            "threshold": 60,
            "waypoints": [
                {"x": 500, "y": 100},
                {"x": 600, "y": 100, "heading_deg": 270},
            ],
        },
    )
    assert response.status_code == 200
    record = api.controller.records["4242"]
    assert record.revs["waypoints"] == api.controller.seq
    echoed = api.controller.dotbots["4242"].model_dump(mode="json", exclude_none=True)[
        "waypoints"
    ]
    assert echoed == [
        {"x": 100, "y": 100},
        {"x": 500, "y": 100},
        {"x": 600, "y": 100, "heading_deg": 270.0},
    ]
    stored = api.controller.dotbots["4242"].model_dump(mode="json")["waypoints"]
    assert stored[2]["heading_deg"] == 270.0
    assert stored[1].get("heading_deg") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "speed,code,called",
    [
        pytest.param(400, 200, True, id="valid"),
        pytest.param(0, 200, True, id="default"),
        pytest.param(701, 422, False, id="too_fast"),
        pytest.param(-1, 422, False, id="negative"),
    ],
)
async def test_set_dotbots_max_speed(speed, code, called):
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242", application=ApplicationType.DotBot, last_seen=123.4
        )
    }
    response = await client.put(
        "/controller/dotbots/4242/0/max_speed", json={"max_speed_mm_s": speed}
    )
    assert response.status_code == code
    if called:
        api.controller.send_max_speed.assert_called_with("4242", speed)
    else:
        api.controller.send_max_speed.assert_not_called()


@pytest.mark.asyncio
async def test_set_dotbots_max_speed_unknown_dotbot():
    api.controller.dotbots = {}
    response = await client.put(
        "/controller/dotbots/4242/0/max_speed", json={"max_speed_mm_s": 300}
    )
    assert response.status_code == 404
    api.controller.send_max_speed.assert_not_called()


@pytest.mark.asyncio
async def test_waypoints_start_from_the_axle():
    """The echoed waypoint list starts at the robot's centre: its own axle
    estimate, else the body pose's axle, else the photodiode fix."""
    photodiode = DotBotLH2Position(x=1000, y=1000)
    robot = DotBotModel(
        address="4242",
        application=ApplicationType.DotBot,
        last_seen=123.4,
        lh2_position=photodiode,
        pose=robot_pose(ROBOT_DEFAULT, photodiode, 90),
    )
    api.controller.dotbots = {"4242": robot}
    body = {"threshold": 10, "waypoints": [{"x": 500, "y": 100}]}
    await client.put("/controller/dotbots/4242/0/waypoints", json=body)
    axle = DotBotLH2Position(x=robot.pose.x, y=robot.pose.y)
    assert robot.waypoints[0] == axle != photodiode

    robot.axle_position = DotBotLH2Position(x=1001, y=949)
    await client.put("/controller/dotbots/4242/0/waypoints", json=body)
    assert robot.waypoints[0] == DotBotLH2Position(x=1001, y=949)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"threshold": -1, "waypoints": []}, id="negative_threshold"),
        pytest.param({"threshold": 65536, "waypoints": []}, id="threshold_over_u16"),
        pytest.param(
            {"threshold": 10, "waypoints": [{"x": 1, "y": 1}] * 17}, id="17_points"
        ),
        pytest.param(
            {"threshold": 10, "waypoints": [{"x": 1, "y": 1, "heading_deg": "NaN"}]},
            id="nan_heading",
        ),
        pytest.param(
            {"threshold": 10, "intermediate_threshold": -1, "waypoints": []},
            id="negative_pass_radius",
        ),
        pytest.param(
            {"threshold": 10, "heading_tolerance": 256, "waypoints": []},
            id="tolerance_over_u8",
        ),
    ],
)
async def test_set_dotbots_waypoints_rejects_what_the_wire_cannot_carry(body):
    api.controller.dotbots = {
        "4242": DotBotModel(
            address="4242", application=ApplicationType.DotBot, last_seen=123.4
        )
    }
    response = await client.put("/controller/dotbots/4242/0/waypoints", json=body)
    assert response.status_code == 422
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_waypoints_start_from_the_fix_without_a_heading():
    """A pose without a heading places its axle arbitrarily, so the echo
    starts at the photodiode fix instead."""
    photodiode = DotBotLH2Position(x=1000, y=1000)
    robot = DotBotModel(
        address="4242",
        application=ApplicationType.DotBot,
        last_seen=123.4,
        lh2_position=photodiode,
        pose=robot_pose(ROBOT_DEFAULT, photodiode, DIRECTION_NONE),
    )
    assert robot.pose.heading_source == "none"
    api.controller.dotbots = {"4242": robot}
    body = {"threshold": 10, "waypoints": [{"x": 500, "y": 100}]}
    await client.put("/controller/dotbots/4242/0/waypoints", json=body)
    assert robot.waypoints[0] == photodiode


def _two_dotbots():
    return {
        address: DotBotModel(
            address=address,
            application=ApplicationType.DotBot,
            last_seen=123.4,
            lh2_position=DotBotLH2Position(x=100, y=100),
        )
        for address in ("4242", "4343")
    }


@pytest.mark.asyncio
async def test_set_waypoint_batches_sends_each_robot_its_own():
    """One request, one batch per robot, under the same settings: each goes
    out as the single-robot route would send it."""
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={
            "threshold": 40,
            "intermediate_threshold": 20,
            "dotbots": {
                "4242": [{"x": 500, "y": 100}],
                "4343": [{"x": 600, "y": 200, "heading_deg": 90}, {"x": 700, "y": 200}],
            },
        },
    )
    assert response.status_code == 200
    assert response.json() == {"applied": ["4242", "4343"], "unknown": [], "failed": []}
    sent = {
        address: payload
        for address, payload in (
            c.args for c in api.controller.send_waypoints.call_args_list
        )
    }
    assert [(w.pos_x, w.pos_y) for w in sent["4242"].waypoints] == [(500, 100)]
    assert [(w.pos_x, w.pos_y) for w in sent["4343"].waypoints] == [
        (600, 200),
        (700, 200),
    ]
    assert {p.threshold for p in sent.values()} == {40}
    assert {p.pass_mm for p in sent.values()} == {20}
    assert api.controller.dotbots["4343"].waypoints[1].heading_deg == 90.0
    assert {
        address
        for address, record in api.controller.records.items()
        if "waypoints" in record.revs
    } == {"4242", "4343"}


@pytest.mark.asyncio
async def test_set_waypoint_batches_takes_more_robots_than_a_batch_takes_points():
    """The 16-point cap is per robot: 20 robots with one point each is fine."""
    api.controller.dotbots = {
        f"{i:04x}": DotBotModel(
            address=f"{i:04x}", application=ApplicationType.DotBot, last_seen=1.0
        )
        for i in range(20)
    }
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={
            "threshold": 40,
            "dotbots": {a: [{"x": 1, "y": 2}] for a in api.controller.dotbots},
        },
    )
    assert response.status_code == 200
    assert api.controller.send_waypoints.call_count == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"threshold": 40, "dotbots": {"4242": [{"x": 1, "y": 2}] * 17}},
            id="17_points",
        ),
        pytest.param(
            {"threshold": -1, "dotbots": {"4242": []}}, id="negative_threshold"
        ),
        pytest.param(
            {"threshold": 40, "heading_tolerance": 300, "dotbots": {}},
            id="heading_tolerance",
        ),
        pytest.param(
            {
                "threshold": 40,
                "dotbots": {"4242": [{"x": 1, "y": 2, "heading_deg": "nan"}]},
            },
            id="nan_heading",
        ),
        pytest.param({"threshold": 40}, id="no_dotbots"),
    ],
)
async def test_set_waypoint_batches_validates_as_the_single_route(body):
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put("/controller/dotbots/waypoints", json=body)
    assert response.status_code == 422
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_set_waypoint_batches_applies_the_known_and_lists_the_unknown():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={
            "threshold": 40,
            "dotbots": {"4242": [{"x": 1, "y": 2}], "9999": [], "8888": []},
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "applied": ["4242"],
        "unknown": ["9999", "8888"],
        "failed": [],
    }
    assert [c.args[0] for c in api.controller.send_waypoints.call_args_list] == ["4242"]


@pytest.mark.asyncio
async def test_set_waypoint_batches_strict_refuses_an_unknown_robot_before_sending():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints?strict=true",
        json={"threshold": 40, "dotbots": {"4242": [{"x": 1, "y": 2}], "9999": []}},
    )
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_set_waypoint_batches_strict_with_every_robot_known():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints?strict=true",
        json={"threshold": 40, "dotbots": {"4242": [{"x": 1, "y": 2}]}},
    )
    assert response.status_code == 200
    assert response.json() == {"applied": ["4242"], "unknown": [], "failed": []}


@pytest.mark.asyncio
async def test_set_waypoint_batches_with_no_robot_known_is_404():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={"threshold": 40, "dotbots": {"9999": [{"x": 1, "y": 2}]}},
    )
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_set_waypoint_batches_with_no_robot_named_is_empty():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints", json={"threshold": 40, "dotbots": {}}
    )
    assert response.status_code == 200
    assert response.json() == {"applied": [], "unknown": [], "failed": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "?strict=true"])
async def test_set_waypoint_batches_validation_refuses_everything(query):
    """A malformed batch for one robot, even an unknown one, sends nothing."""
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        f"/controller/dotbots/waypoints{query}",
        json={
            "threshold": 40,
            "dotbots": {"4242": [{"x": 1, "y": 2}], "9999": [{"x": 1, "y": 2}] * 17},
        },
    )
    assert response.status_code == 422
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "?strict=true"])
async def test_set_waypoint_batches_of_the_wrong_kind_send_nothing(query):
    """A GPS batch for a DotBot refuses the whole request, including the
    robots listed before it."""
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    api.controller.send_payload = MagicMock()
    response = await client.put(
        f"/controller/dotbots/waypoints{query}",
        json={
            "threshold": 40,
            "dotbots": {
                "4242": [{"x": 1, "y": 2}],
                "4343": [{"latitude": 48.8, "longitude": 2.3}],
            },
        },
    )
    assert response.status_code == 422
    assert "4343" in response.json()["detail"]
    api.controller.send_waypoints.assert_not_called()
    api.controller.send_payload.assert_not_called()
    assert api.controller.dotbots["4242"].waypoints == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "application,point",
    [
        (ApplicationType.DotBot.value, {"latitude": 48.8, "longitude": 2.3}),
        (ApplicationType.SailBot.value, {"x": 1, "y": 2}),
    ],
)
async def test_set_dotbot_waypoints_of_the_wrong_kind_is_422(application, point):
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    api.controller.send_payload = MagicMock()
    response = await client.put(
        f"/controller/dotbots/4242/{application}/waypoints",
        json={"threshold": 40, "waypoints": [point]},
    )
    assert response.status_code == 422
    api.controller.send_waypoints.assert_not_called()
    api.controller.send_payload.assert_not_called()


@pytest.mark.asyncio
async def test_clear_waypoints_of_named_robots():
    api.controller.dotbots = _two_dotbots()
    api.controller.dotbots["4242"].waypoints = [
        DotBotLH2Position(x=100, y=100),
        DotBotLH2Waypoint(x=900, y=900),
    ]
    api.controller.send_waypoints = MagicMock()
    response = await client.delete(
        "/controller/dotbots/waypoints?address=4242&address=4242"
    )
    assert response.status_code == 200
    assert response.json() == {"applied": ["4242"], "unknown": [], "failed": []}
    address, payload = api.controller.send_waypoints.call_args.args
    assert (address, payload.count) == ("4242", 0)
    assert api.controller.send_waypoints.call_count == 1
    assert api.controller.dotbots["4242"].waypoints == [DotBotLH2Position(x=100, y=100)]


@pytest.mark.asyncio
async def test_clear_waypoints_of_every_robot():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.delete("/controller/dotbots/waypoints")
    assert response.status_code == 200
    assert sorted(response.json()["applied"]) == ["4242", "4343"]
    assert sorted(c.args[0] for c in api.controller.send_waypoints.call_args_list) == [
        "4242",
        "4343",
    ]


@pytest.mark.asyncio
async def test_clear_waypoints_stops_the_known_and_lists_the_unknown():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.delete(
        "/controller/dotbots/waypoints?address=4242&address=9999"
    )
    assert response.status_code == 200
    assert response.json() == {"applied": ["4242"], "unknown": ["9999"], "failed": []}
    assert [c.args[0] for c in api.controller.send_waypoints.call_args_list] == ["4242"]


@pytest.mark.asyncio
async def test_clear_waypoints_strict_refuses_an_unknown_robot_before_sending():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.delete(
        "/controller/dotbots/waypoints?address=4242&address=9999&strict=true"
    )
    assert response.status_code == 404
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_clear_waypoints_with_no_robot_known_is_404():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.delete("/controller/dotbots/waypoints?address=9999")
    assert response.status_code == 404
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_clear_waypoints_of_every_robot_with_none_known():
    api.controller.dotbots = {}
    api.controller.send_waypoints = MagicMock()
    response = await client.delete("/controller/dotbots/waypoints")
    assert response.status_code == 200
    assert response.json() == {"applied": [], "unknown": [], "failed": []}


# --- Waypoints the wire or the site cannot take ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "point",
    [
        pytest.param({"x": -100, "y": 500}, id="negative_x"),
        pytest.param({"x": 100, "y": -1}, id="negative_y"),
        pytest.param({"x": 2**32, "y": 500}, id="over_u32"),
        pytest.param({"x": "NaN", "y": 500}, id="nan"),
        pytest.param({"x": "inf", "y": 500}, id="inf"),
    ],
)
async def test_a_waypoint_the_wire_cannot_carry_is_422(point):
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints",
        json={"threshold": 40, "waypoints": [point]},
    )
    assert response.status_code == 422
    assert "cannot be sent" in response.json()["detail"]
    api.controller.send_waypoints.assert_not_called()
    assert api.controller.dotbots["4242"].waypoints == []


@pytest.mark.asyncio
@pytest.mark.parametrize("point", [{"x": 3001, "y": 500}, {"x": -1, "y": 500}])
async def test_a_waypoint_outside_the_site_is_422(point):
    api.controller.settings.site = Site(name="c405", extent_mm=(3000, 2000))
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints",
        json={"threshold": 40, "waypoints": [{"x": 3000, "y": 2000}, point]},
    )
    assert response.status_code == 422
    assert "outside site 'c405', 0 to 3000 x 0 to 2000 mm" in response.json()["detail"]
    api.controller.send_waypoints.assert_not_called()


@pytest.mark.asyncio
async def test_a_bulk_request_with_one_waypoint_outside_the_site_sends_nothing():
    api.controller.settings.site = Site(name="c405", extent_mm=(3000, 2000))
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={
            "threshold": 40,
            "dotbots": {"4242": [{"x": 1, "y": 2}], "4343": [{"x": -5, "y": 2}]},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"].startswith("4343: waypoint (-5, 2) mm")
    api.controller.send_waypoints.assert_not_called()
    assert api.controller.dotbots["4242"].waypoints == []


def test_ws_waypoint_outside_the_site_is_an_invalid_message():
    api.controller.settings.site = Site(name="c405", extent_mm=(3000, 2000))
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock()
    with TestClient(api).websocket_connect("/controller/ws/dotbots") as ws:
        ws.send_json(
            {
                "cmd": "waypoints",
                "address": "4242",
                "application": 0,
                "data": {"threshold": 40, "waypoints": [{"x": -100, "y": 500}]},
            }
        )
        response = ws.receive_json()
    assert response["error"] == "invalid_message"
    assert "outside site 'c405'" in response["details"]
    api.controller.send_waypoints.assert_not_called()


# --- Waypoints the controller could not send ----------------------------------


@pytest.mark.asyncio
async def test_waypoints_not_sent_are_a_500_and_leave_the_robot_as_it_was():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock(return_value=False)
    response = await client.put(
        "/controller/dotbots/4242/0/waypoints",
        json={"threshold": 40, "waypoints": [{"x": 1, "y": 2}]},
    )
    assert response.status_code == 500
    assert response.json()["detail"].startswith("4242: waypoints not sent")
    assert api.controller.dotbots["4242"].waypoints == []


@pytest.mark.asyncio
async def test_a_bulk_request_lists_the_robots_it_could_not_send_to():
    api.controller.dotbots = _two_dotbots()
    api.controller.send_waypoints = MagicMock(
        side_effect=lambda address, _payload: address != "4343"
    )
    response = await client.put(
        "/controller/dotbots/waypoints",
        json={
            "threshold": 40,
            "dotbots": {"4242": [{"x": 1, "y": 2}], "4343": [{"x": 3, "y": 4}]},
        },
    )
    assert response.status_code == 200
    assert response.json() == {"applied": ["4242"], "unknown": [], "failed": ["4343"]}
    assert api.controller.dotbots["4343"].waypoints == []
