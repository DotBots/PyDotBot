"""Test module for controller base class."""

import time
from dataclasses import dataclass
from typing import List
from unittest.mock import patch

import pytest
import serial

from dotbot.controller import Controller, ControllerSettings, gps_distance, lh2_distance
from dotbot.hdlc import hdlc_encode
from dotbot.models import DotBotGPSPosition, DotBotLH2Position, DotBotModel
from dotbot.protocol import (
    PayloadType,
    ProtocolData,
    ProtocolField,
    ProtocolHeader,
    ProtocolPayload,
)


@dataclass
class ProtocolDataTest(ProtocolData):
    test: int = 0x1234

    @property
    def fields(self) -> List[ProtocolField]:
        """Returns the list of fields in this data."""
        return [
            ProtocolField(ProtocolDataTest.test, "test", 2),
        ]

    @staticmethod
    def from_bytes(bytes_: bytes) -> ProtocolData:
        """Returns a ProtocolData instance from a bytearray."""
        return ProtocolDataTest(bytes_[0:2])


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
    payload = ProtocolPayload(
        ProtocolHeader(0, 0, 0, 0, 0),
        PayloadType.CMD_MOVE_RAW,
        ProtocolDataTest(),
    )
    # smoke test for the from_bytes static method of ProtocolDataTest
    assert len(ProtocolDataTest.from_bytes(bytearray([1, 2])).fields) == 1
    controller.send_payload(payload)
    assert serial_write.call_count == 1
    payload_expected = hdlc_encode(payload.to_bytes())
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
    payload = ProtocolPayload(
        ProtocolHeader(123, 0, 0, 0, 0),
        PayloadType.CMD_MOVE_RAW,
        ProtocolDataTest(),
    )
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(payload)
    assert serial_write.call_count == 0


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
