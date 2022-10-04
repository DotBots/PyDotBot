"""Test module for controller base class."""

from unittest.mock import patch

import pytest

from bot_controller.controller import (
    ControllerBase,
    ControllerException,
    controller_factory,
    register_controller,
)
from bot_controller.hdlc import hdlc_encode
from bot_controller.protocol import command_header


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

    controller = ControllerTest("/dev/null", "115200", 123, 456)
    capture = capsys.readouterr()
    controller.init()
    assert "initialize controller" in capture.out
    capture = capsys.readouterr()
    controller.start()
    assert "initialize controller" in capture.out
    controller.send_command(b"test")
    assert serial_write.call_count == 1
    payload_expected = hdlc_encode(
        command_header(controller.dotbot_address, controller.gw_address) + b"test"
    )
    assert serial_write.call_args_list[0].args[0] == payload_expected


@patch("bot_controller.serial_interface.serial.Serial.open")
def test_controller_factory(_):
    with pytest.raises(ControllerException) as exc:
        controller_factory("test", "/dev/null", 115200, 124, 456)
    assert str(exc.value) == "Invalid controller"

    register_controller("test", ControllerTest)
    controller = controller_factory("test", "/dev/null", 115200, 123, 456)
    assert controller.__class__.__name__ == "ControllerTest"
    assert controller.dotbot_address == 123
    assert controller.gw_address == 456
