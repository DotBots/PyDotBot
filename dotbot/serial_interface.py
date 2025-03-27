# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot controller serial interface."""

import sys
import threading
import time
from typing import Callable

import serial
from serial.tools import list_ports

from dotbot.logger import LOGGER

PAYLOAD_CHUNK_SIZE = 64
PAYLOAD_CHUNK_DELAY = 0.002  # 2 ms


def get_default_port():
    """Return default serial port."""
    ports = [port for port in list_ports.comports()]
    if sys.platform != "win32":
        ports = [port for port in ports if "J-Link" == port.product]
    if not ports:
        return "/dev/ttyACM0"
    # return first JLink port available
    return ports[0].device


class SerialInterfaceException(Exception):
    """Exception raised when serial port is disconnected."""


class SerialInterface(threading.Thread):
    """Bidirectional serial interface."""

    def __init__(self, port: str, baudrate: int, callback: Callable):
        self.lock = threading.Lock()
        self.callback = callback
        self.serial = serial.Serial(port, baudrate)
        super().__init__(daemon=True)
        self._logger = LOGGER.bind(context=__name__)
        self.start()
        self._logger.info("Serial port thread started")

    def run(self):
        """Listen continuously at each byte received on serial."""
        self.serial.flush()
        try:
            while 1:
                try:
                    byte = self.serial.read(1)
                except (TypeError, serial.serialutil.SerialException):
                    byte = None
                if byte is None:
                    self._logger.info("Serial port disconnected")
                    break
                self.callback(byte)
        except serial.serialutil.PortNotOpenError as exc:
            self._logger.error(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc
        except serial.serialutil.SerialException as exc:
            self._logger.error(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc

    def stop(self):
        self.serial.close()
        self.join()

    def write(self, bytes_):
        """Write bytes on serial."""
        # Send 64 bytes at a time
        pos = 0
        while (pos % PAYLOAD_CHUNK_SIZE) == 0 and pos < len(bytes_):
            self.serial.write(bytes_[pos : pos + PAYLOAD_CHUNK_SIZE])
            self.serial.flush()
            pos += PAYLOAD_CHUNK_SIZE
            time.sleep(PAYLOAD_CHUNK_DELAY)
        # self.serial.flush()
