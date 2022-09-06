"""Interface of the Dotbot controller."""

from abc import ABC, abstractmethod

from bot_controller import bc_serial


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.init()

    @abstractmethod
    def init(self):
        """Abstract method to initialize a controller."""

    @abstractmethod
    def start(self):
        """Abstract method to start a controller."""

    def write(self, payload):
        """Write a payload of bytes to the serial interface."""
        bc_serial.write(self.port, self.baudrate, payload)
