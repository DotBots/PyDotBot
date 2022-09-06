"""Module containing API for the controller factory."""

from bot_controller.keyboard import KeyboardController
from bot_controller.joystick import JoystickController
from bot_controller.server import ServerController


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


def controller_factory(type_, port, baudrate):
    """Returns an instance of a concrete Dotbot controller."""
    if type_ == "keyboard":
        return KeyboardController(port, baudrate)
    if type_ == "joystick":
        return JoystickController(port, baudrate)
    if type_ == "server":
        return ServerController(port, baudrate)

    raise ControllerException("Invalid controller")
