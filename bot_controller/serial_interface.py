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
        self.connected = True
        super().__init__()
        self.daemon = True
        self.start()

    def run(self):
        """Listen continuously at each byte received on serial."""
        try:
            while self.connected:
                byte = self.serial.read(1)
                if byte is None:
                    raise SerialInterfaceException("Serial port disconnected")
                self.callback(byte)
        except SerialInterfaceException as exc:
            self.connected = False
            print(f"{exc}")
        except serial.serialutil.PortNotOpenError as exc:
            self.connected = False
            print(f"{exc}")

    def write(self, bytes_):
        """Write bytes on serial."""
        self.serial.write(bytes_)
        self.serial.flush()
