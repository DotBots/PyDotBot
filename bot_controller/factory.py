from bot_controller.keyboard import KeyboardController
from bot_controller.joystick import JoystickController
from bot_controller.server import ServerController


class ControllerException(Exception):
    ...


def controller_factory(type_, port, baudrate):
    if type_ == "keyboard":
        return KeyboardController(port, baudrate)
    elif type_ == "joystick":
        return JoystickController(port, baudrate)
    elif type_ == "server":
        return ServerController(port, baudrate)
    else:
        raise ControllerException("Invalid controller")
