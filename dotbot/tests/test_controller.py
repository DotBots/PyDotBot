"""Test module for controller base class."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from dotbot_utils.hdlc import hdlc_encode
from dotbot_utils.protocol import Frame, Header, Packet
from dotbot_utils.serial_interface import SerialInterface

from dotbot.adapter import SerialAdapter
from dotbot.controller import Controller, ControllerSettings, gps_distance, lh2_distance
from dotbot.models import (
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotQueryModel,
    DotBotStatus,
)
from dotbot.protocol import ApplicationType, ControlModeType, PayloadControlMode


@pytest.fixture
def controller(monkeypatch):
    """Create a controller instance with mocked serial interface."""
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.flush", MagicMock()
    )
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        gw_address="78",
    )
    _controller = Controller(settings)
    _controller.dotbots.update(
        {
            "0000000000000000": DotBotModel(
                address="0000000000000000",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.ACTIVE,
                battery=2.0,
                lh2_position=DotBotLH2Position(x=1000, y=1000),
                position_history=[
                    DotBotLH2Position(x=900, y=900),
                    DotBotLH2Position(x=800, y=800),
                ],
            ),
            "0000000000000001": DotBotModel(
                address="0000000000000001",
                last_seen=time.time(),
                application=ApplicationType.SailBot,
                status=DotBotStatus.ACTIVE,
                battery=3.0,
            ),
            "0000000000000002": DotBotModel(
                address="0000000000000002",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.INACTIVE,
                battery=1.0,
                lh2_position=DotBotLH2Position(x=500, y=500),
                position_history=[
                    DotBotLH2Position(x=400, y=400),
                    DotBotLH2Position(x=300, y=300),
                ],
            ),
            "0000000000000003": DotBotModel(
                address="0000000000000003",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.LOST,
                battery=1.0,
                lh2_position=DotBotLH2Position(x=1000, y=1500),
                position_history=[],
            ),
        }
    )
    _controller.adapter = SerialAdapter(settings.port, settings.baudrate)
    _controller.adapter.serial = SerialInterface(
        settings.port, settings.baudrate, lambda: None
    )

    yield _controller


@pytest.mark.asyncio
async def test_controller(controller):
    """Check controller subclass instanciation and write to serial."""
    frame = Frame(
        header=Header(
            destination=0,
            source=0,
        ),
        packet=Packet().from_payload(PayloadControlMode(mode=ControlModeType.AUTO)),
    )
    controller.send_payload(0, PayloadControlMode(mode=ControlModeType.AUTO))

    serial_write_mock = controller.adapter.serial.serial.write
    assert serial_write_mock.call_count == 1
    payload_expected = hdlc_encode(frame.to_bytes())
    assert serial_write_mock.call_args_list[0].args[0] == payload_expected


@pytest.mark.asyncio
async def test_controller_dont_send(controller):
    """Check controller subclass instanciation and write to serial."""
    serial_write_mock = controller.adapter.serial.serial.write
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(42, PayloadControlMode(mode=ControlModeType.AUTO))
    assert serial_write_mock.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,length",
    [
        pytest.param(
            DotBotQueryModel(address="0000000000000001"),
            1,
            id="by address",
        ),
        pytest.param(
            DotBotQueryModel(application=ApplicationType.SailBot),
            1,
            id="by application",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.ACTIVE),
            2,
            id="by status active",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.INACTIVE),
            1,
            id="by status inactive",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.LOST),
            1,
            id="by status lost",
        ),
        pytest.param(
            DotBotQueryModel(min_battery=2.5),
            1,
            id="by min battery",
        ),
        pytest.param(
            DotBotQueryModel(max_battery=1.5),
            2,
            id="by max battery",
        ),
        pytest.param(
            DotBotQueryModel(max_position_x=600),
            1,
            id="by max position x",
        ),
        pytest.param(
            DotBotQueryModel(min_position_x=800),
            2,
            id="by min position x",
        ),
        pytest.param(
            DotBotQueryModel(max_position_y=600),
            1,
            id="by max position y",
        ),
        pytest.param(
            DotBotQueryModel(min_position_y=1000),
            2,
            id="by min position y",
        ),
        pytest.param(
            DotBotQueryModel(max_positions=1),
            3,
            id="by max positions",
        ),
        pytest.param(
            DotBotQueryModel(limit=2),
            2,
            id="by limit",
        ),
    ],
)
async def test_controller_get_dotbots_query(query, length, controller):
    """Check controller get_dotbots query."""
    dotbots = controller.get_dotbots(query=query)
    assert len(dotbots) == length


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_controller_sailbot_simulator():
    """Check controller called for sailbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="sailbot-simulator",
            network_id="0",
            gw_address="78",
            controller_http_port=8000,
        )
        controller = Controller(settings)
        try:
            await asyncio.wait_for(controller.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_simulator())


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@patch("dotbot.controller.QrkeyController.start")
def test_controller_dotbot_simulator(_):
    """Check controller called for dotbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="dotbot-simulator",
            network_id="0",
            gw_address="78",
            controller_http_port=8001,
        )
        controller = Controller(settings)
        try:
            await asyncio.wait_for(controller.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_simulator())


@pytest.mark.parametrize(
    "last,new,result",
    [
        (DotBotLH2Position(x=0, y=0, z=0), DotBotLH2Position(x=0, y=0, z=0), 0.0),
        (DotBotLH2Position(x=1, y=0, z=0), DotBotLH2Position(x=0, y=0, z=0), 1.0),
        (DotBotLH2Position(x=0, y=1, z=0), DotBotLH2Position(x=0, y=0, z=0), 1.0),
    ],
)
def test_lh2_distance(last, new, result):
    assert lh2_distance(last, new) == result


@pytest.mark.parametrize(
    "last,new,result",
    [
        (
            DotBotGPSPosition(latitude=45.7597, longitude=4.8422),  # Lyon
            DotBotGPSPosition(latitude=48.8567, longitude=2.3508),  # Paris
            392216.71780,
        ),
        (
            DotBotGPSPosition(latitude=51.509865, longitude=-0.118092),  # London
            DotBotGPSPosition(latitude=48.8567, longitude=2.3508),  # Paris
            343374.07842,
        ),
    ],
)
def test_gps_distance(last, new, result):
    assert gps_distance(last, new) == pytest.approx(result)
