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


class ControllerTest(ControllerBase):
    """A Dotbot test controller."""

    def init(self):
        """Initialize the test controller."""
        print("initialize controller")

    def start(self):
        """Starts the test controller."""
        print("start controller")


@patch("bot_controller.bc_serial.serial.Serial.write")
@patch("bot_controller.bc_serial.serial.Serial.open")
def test_controller(_, serial_write, capsys):
    """Check controller subclass instanciation and write to serial."""

    controller = ControllerTest("/dev/null", "115200")
    capture = capsys.readouterr()
    controller.init()
    assert "initialize controller" in capture.out
    capture = capsys.readouterr()
    controller.start()
    assert "initialize controller" in capture.out
    controller.write(b"test")
    assert serial_write.call_count == 1
    assert serial_write.call_args_list[0].args[0] == hdlc_encode(b"test")


def test_controller_factory():
    with pytest.raises(ControllerException) as exc:
        controller_factory("test", "/dev/null", 115200)
    assert str(exc.value) == "Invalid controller"

    register_controller("test", ControllerTest)
    controller = controller_factory("test", "/dev/null", 115200)
    assert controller.__class__.__name__ == "ControllerTest"
    assert controller.port == "/dev/null"
    assert controller.baudrate == 115200
