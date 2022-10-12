"""Test module for controller base class."""

from dataclasses import dataclass
from typing import List
from unittest.mock import patch

import pytest

from bot_controller.controller import (
    ControllerBase,
    ControllerException,
    controller_factory,
    register_controller,
)
from bot_controller.hdlc import hdlc_encode
from bot_controller.protocol import (
    ProtocolField,
    ProtocolPayload,
    ProtocolData,
    ProtocolHeader,
    PROTOCOL_VERSION,
    PayloadType,
)


@dataclass
class ProtocolDataTest(ProtocolData):
    test: int = 0x1234

    @property
    def fields(self) -> List[ProtocolField]:
        """Returns the list of fields in this data."""
        return [
            ProtocolField(self.test, "test", 2),
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

    def start(self):
        """Starts the test controller."""
        print("start controller")


@patch("bot_controller.serial_interface.serial.Serial.write")
@patch("bot_controller.serial_interface.serial.Serial.open")
@patch("bot_controller.serial_interface.serial.Serial.flush")
def test_controller(_, __, serial_write, capsys):
    """Check controller subclass instanciation and write to serial."""

    controller = ControllerTest("/dev/null", "115200", 123, 456, 78)
    capture = capsys.readouterr()
    controller.init()
    assert "initialize controller" in capture.out
    capture = capsys.readouterr()
    controller.start()
    assert "initialize controller" in capture.out
    payload = ProtocolPayload(
        ProtocolHeader.from_bytes(bytearray()),
        PayloadType.CMD_MOVE_RAW,
        ProtocolDataTest(),
    )
    # smoke test for the from_bytes static method of ProtocolDataTest
    assert len(ProtocolDataTest.from_bytes(bytearray([1, 2])).fields) == 1
    controller.send_payload(payload)
    assert serial_write.call_count == 1
    payload_expected = hdlc_encode(payload.to_bytes())
    assert serial_write.call_args_list[0].args[0] == payload_expected


@patch("bot_controller.serial_interface.serial.Serial.open")
def test_controller_factory(_):
    with pytest.raises(ControllerException) as exc:
        controller_factory("test", "/dev/null", 115200, 124, 456, 78)
    assert str(exc.value) == "Invalid controller"

    register_controller("test", ControllerTest)
    controller = controller_factory("test", "/dev/null", 115200, 123, 456, 78)
    assert controller.__class__.__name__ == "ControllerTest"
    assert controller.header == ProtocolHeader(123, 456, 78, PROTOCOL_VERSION)
