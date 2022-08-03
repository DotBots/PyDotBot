from abc import ABC, abstractmethod

from bot_controller import bc_serial


class ControllerBase(ABC):

    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.init()

    @abstractmethod
    def init(self):
        ...

    @abstractmethod
    def start(self):
        ...

    def write(self, payload):
        bc_serial.write(self.port, self.baudrate, payload)
