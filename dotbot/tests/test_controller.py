"""Test module for controller base class."""

import time

from dataclasses import dataclass
from typing import List
from unittest.mock import patch

import pytest
import serial

from dotbot.controller import (
    gps_distance,
    lh2_distance,
    ControllerBase,
    ControllerException,
    ControllerSettings,
    controller_factory,
    register_controller,
)
from dotbot.hdlc import hdlc_encode
from dotbot.models import DotBotModel, DotBotLH2Position, DotBotGPSPosition
from dotbot.protocol import (
    ProtocolField,
    ProtocolPayload,
    ProtocolData,
    ProtocolHeader,
    PROTOCOL_VERSION,
    PayloadType,
    ApplicationType,
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


class ControllerTest(ControllerBase):
    """A Dotbot test controller."""

    def init(self):
        """Initialize the test controller."""
        print("initialize controller")

    async def start(self):
        """Starts the test controller."""
        print("start controller")


@pytest.mark.asyncio
@patch("dotbot.serial_interface.serial.Serial.write")
@patch("dotbot.serial_interface.serial.Serial.open")
@patch("dotbot.serial_interface.serial.Serial.flush")
async def test_controller(_, __, serial_write, capsys):
    """Check controller subclass instanciation and write to serial."""
    settings = ControllerSettings("/dev/null", "115200", "0", "456", "78")
    controller = ControllerTest(settings)
    controller.dotbots.update(
        {
            "0000000000000000": DotBotModel(
                address="0000000000000000", last_seen=time.time()
            )
        }
    )
    controller.serial = serial.Serial(settings.port, settings.baudrate)
    controller.init()
    capture = capsys.readouterr()
    assert "initialize controller" in capture.out
    await controller.start()
    capture = capsys.readouterr()
    assert "start controller" in capture.out
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
    controller = ControllerTest(settings)
    dotbot = DotBotModel(address="0000000000000000", last_seen=time.time())
    controller.dotbots.update({dotbot.address: dotbot})
    controller.serial = serial.Serial(settings.port, settings.baudrate)
    controller.init()
    await controller.start()
    payload = ProtocolPayload(
        ProtocolHeader(123, 0, 0, 0, 0),
        PayloadType.CMD_MOVE_RAW,
        ProtocolDataTest(),
    )
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(payload)
    assert serial_write.call_count == 0


@patch("dotbot.serial_interface.serial.Serial.open")
def test_controller_factory(_):
    settings = ControllerSettings("/dev/null", "115200", "123", "456", "78")
    with pytest.raises(ControllerException) as exc:
        controller_factory("test", settings)
    assert str(exc.value) == "Invalid controller"

    register_controller("test", ControllerTest)
    controller = controller_factory("test", settings)
    assert controller.__class__.__name__ == "ControllerTest"
    assert controller.header == ProtocolHeader(
        destination=int(settings.dotbot_address, 16),
        source=int(settings.gw_address, 16),
        swarm_id=int(settings.swarm_id, 16),
        application=ApplicationType.DotBot,
        version=PROTOCOL_VERSION,
    )


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
