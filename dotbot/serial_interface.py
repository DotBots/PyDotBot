"""Dotbot controller serial interface."""

import threading

from typing import Callable

import serial


class SerialInterfaceException(Exception):
    """Exception raised when serial port is disconnected."""


class SerialInterface(threading.Thread):
    """Bidirectional serial interface."""

    def __init__(self, port: str, baudrate: int, callback: Callable):
        self.callback = callback
        self.serial = serial.Serial(port, baudrate)
        super().__init__(daemon=True)
        self.start()

    def run(self):
        """Listen continuously at each byte received on serial."""
        try:
            while 1:
                byte = self.serial.read(1)
                if byte is None:
                    raise SerialInterfaceException("Serial port disconnected")
                self.callback(byte)
        except serial.serialutil.PortNotOpenError as exc:
            print(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc
        except serial.serialutil.SerialException as exc:
            print(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc

    def write(self, bytes_):
        """Write bytes on serial."""
        self.serial.write(bytes_)
        self.serial.flush()
