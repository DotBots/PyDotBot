"""Test module for controller base class."""

import asyncio
import time
from unittest.mock import patch

import pytest
import serial

from dotbot.controller import Controller, ControllerSettings, gps_distance, lh2_distance
from dotbot.hdlc import hdlc_encode
from dotbot.models import DotBotGPSPosition, DotBotLH2Position, DotBotModel
from dotbot.protocol import ControlModeType, Frame, Header, PayloadControlMode


@pytest.mark.asyncio
@patch("dotbot.serial_interface.serial.Serial.write")
@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.serial_interface.serial.Serial.flush")
async def test_controller(_, __, serial_write, capsys):
    """Check controller subclass instanciation and write to serial."""
    settings = ControllerSettings("/dev/null", "115200", "0", "456", "78")
    controller = Controller(settings)
    controller.dotbots.update(
        {
            "0000000000000000": DotBotModel(
                address="0000000000000000", last_seen=time.time()
            )
        }
    )
    controller.serial = serial.Serial(settings.port, settings.baudrate)
    frame = Frame(
        header=Header(
            destination=0,
            source=0,
        ),
        payload=PayloadControlMode(mode=ControlModeType.AUTO),
    )
    controller.send_payload(frame)
    assert serial_write.call_count == 1
    payload_expected = hdlc_encode(frame.to_bytes())
    assert serial_write.call_args_list[0].args[0] == payload_expected


@pytest.mark.asyncio
@patch("dotbot.serial_interface.serial.Serial.write")
@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.serial_interface.serial.Serial.flush")
async def test_controller_dont_send(_, __, serial_write):
    """Check controller subclass instanciation and write to serial."""
    settings = ControllerSettings("/dev/null", "115200", "0", "456", "78")
    controller = Controller(settings)
    dotbot = DotBotModel(address="0000000000000000", last_seen=time.time())
    controller.dotbots.update({dotbot.address: dotbot})
    controller.serial = serial.Serial(settings.port, settings.baudrate)
    frame = Frame(
        header=Header(
            destination=1,
            source=0,
        ),
        payload=PayloadControlMode(mode=ControlModeType.AUTO),
    )
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(frame)
    assert serial_write.call_count == 0


def test_controller_saibot_simulator():
    """Check controller called for sailbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            "sailbot-simulator", "115200", "0", "456", "78", 8000
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
            "dotbot-simulator", "115200", "0", "456", "78", 8001
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
            392217.25594,
        ),
        (
            DotBotGPSPosition(latitude=51.509865, longitude=-0.118092),  # London
            DotBotGPSPosition(latitude=48.8567, longitude=2.3508),  # Paris
            343374.55271,
        ),
    ],
)
def test_gps_distance(last, new, result):
    assert gps_distance(last, new) == pytest.approx(result)
