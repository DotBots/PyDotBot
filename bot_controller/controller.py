from abc import ABC, abstractmethod, abstractproperty

from bot_controller import bc_serial


class ControllerBase(ABC):

    @abstractmethod
    def start(self):
        ...

    def write(self, payload):
        bc_serial.write(self.port, self.baudrate, payload)
