"""Module containing API for the controller factory."""

from bot_controller.keyboard import KeyboardController
from bot_controller.joystick import JoystickController
from bot_controller.server import ServerController


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


def controller_factory(type_, port, baudrate):
    """Returns an instance of a concrete Dotbot controller.

    >>> controller_factory("invalid", "/dev/tty", 115200)
    Traceback (most recent call last):
    bot_controller.factory.ControllerException: Invalid controller
    >>> controller_factory("keyboard", "/dev/tty", 115200)  # doctest: +ELLIPSIS
    <bot_controller.keyboard.KeyboardController object at 0x...>
    >>> controller_factory("server", "/dev/tty", 115200)  # doctest: +ELLIPSIS
    <bot_controller.server.ServerController object at 0x...>
    """
    if type_ == "keyboard":
        return KeyboardController(port, baudrate)
    if type_ == "joystick":
        return JoystickController(port, baudrate)
    if type_ == "server":
        return ServerController(port, baudrate)

    raise ControllerException("Invalid controller")
