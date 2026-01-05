"""Test module for controller base class."""

import asyncio
import time
from unittest.mock import patch

import pytest
from dotbot_utils.hdlc import hdlc_encode
from dotbot_utils.protocol import Frame, Header, Packet
from dotbot_utils.serial_interface import SerialInterface

from dotbot.adapter import SerialAdapter
from dotbot.controller import Controller, ControllerSettings, gps_distance, lh2_distance
from dotbot.models import DotBotGPSPosition, DotBotLH2Position, DotBotModel
from dotbot.protocol import ControlModeType, PayloadControlMode


@pytest.mark.asyncio
@patch("dotbot_utils.serial_interface.serial.Serial.write")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot_utils.serial_interface.serial.Serial.flush")
async def test_controller(_, __, serial_write, capsys):
    """Check controller subclass instanciation and write to serial."""
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        dotbot_address="456",
        gw_address="78",
    )
    controller = Controller(settings)
    controller.dotbots.update(
        {
            "0000000000000000": DotBotModel(
                address="0000000000000000", last_seen=time.time()
            )
        }
    )
    controller.adapter = SerialAdapter(settings.port, settings.baudrate)
    controller.adapter.serial = SerialInterface(
        settings.port, settings.baudrate, lambda: None
    )
    frame = Frame(
        header=Header(
            destination=0,
            source=0,
        ),
        packet=Packet().from_payload(PayloadControlMode(mode=ControlModeType.AUTO)),
    )
    controller.send_payload(0, PayloadControlMode(mode=ControlModeType.AUTO))
    assert serial_write.call_count == 1
    payload_expected = hdlc_encode(frame.to_bytes())
    assert serial_write.call_args_list[0].args[0] == payload_expected


@pytest.mark.asyncio
@patch("dotbot_utils.serial_interface.serial.Serial.write")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot_utils.serial_interface.serial.Serial.flush")
async def test_controller_dont_send(_, __, serial_write):
    """Check controller subclass instanciation and write to serial."""
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        dotbot_address="456",
        gw_address="78",
    )
    controller = Controller(settings)
    dotbot = DotBotModel(address="0000000000000000", last_seen=time.time())
    controller.dotbots.update({dotbot.address: dotbot})
    controller.adapter = SerialAdapter(settings.port, settings.baudrate)
    controller.adapter.serial = SerialInterface(
        settings.port, settings.baudrate, lambda: None
    )
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(1, PayloadControlMode(mode=ControlModeType.AUTO))
    assert serial_write.call_count == 0


def test_controller_saibot_simulator():
    """Check controller called for sailbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="sailbot-simulator",
            network_id="0",
            dotbot_address="456",
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


@patch("dotbot.controller.QrkeyController.start")
def test_controller_dotbot_simulator(_):
    """Check controller called for dotbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="dotbot-simulator",
            network_id="0",
            dotbot_address="456",
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
