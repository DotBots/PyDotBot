"""Test module for controller factory function."""

from unittest.mock import patch

from bot_controller.factory import controller_factory


@patch("bot_controller.joystick.JoystickController.init")
def test_joystick_controller_factory(init):
    controller = controller_factory("joystick", "/dev/null", 115200)
    assert controller.__class__.__name__ == "JoystickController"
    init.assert_called_once()
    assert controller.port == "/dev/null"
    assert controller.baudrate == 115200
