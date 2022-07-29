from bot_controller.keyboard import KeyboardController
from bot_controller.joystick import JoystickController
from bot_controller.server import ServerController


class ControllerException(Exception):
    ...


def controller_factory(type_):
    if type_ == "keyboard":
        return KeyboardController
    elif type_ == "joystick":
        return JoystickController
    elif type_ == "server":
        return ServerController
    else:
        raise ControllerException("Invalid controller")
