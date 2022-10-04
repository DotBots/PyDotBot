"""Interface of the Dotbot controller."""

from abc import ABC, abstractmethod

from bot_controller import bc_serial
from bot_controller.protocol import command_header

CONTROLLERS = {}


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, port, baudrate, dotbot_address, gw_address):
        self.port = port
        self.baudrate = baudrate
        self.dotbot_address = dotbot_address
        self.gw_address = gw_address
        self.init()

    @abstractmethod
    def init(self):
        """Abstract method to initialize a controller."""

    @abstractmethod
    def start(self):
        """Abstract method to start a controller."""

    def send_command(self, command):
        """Sends a command over serial."""
        payload = command_header(self.dotbot_address, self.gw_address)
        payload += command
        bc_serial.write(self.port, self.baudrate, payload)


def register_controller(type_, cls):
    """Register a new controller."""
    CONTROLLERS.update({type_: cls})


def controller_factory(type_, port, baudrate, dotbot_address, gw_address):
    """Returns an instance of a concrete Dotbot controller."""
    if type_ not in CONTROLLERS:
        raise ControllerException("Invalid controller")
    return CONTROLLERS[type_](port, baudrate, dotbot_address, gw_address)
