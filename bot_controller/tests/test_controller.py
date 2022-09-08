"""Test module for controller base class."""

from unittest.mock import patch

from bot_controller.controller import ControllerBase


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
    assert serial_write.call_count == 2
    assert serial_write.call_args_list[0].args[0] == b"\x04"
    assert serial_write.call_args_list[1].args[0] == b"test"
