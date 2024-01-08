"""Dotbot controller serial interface."""

import sys
import threading
import time
from typing import Callable

import serial
from serial.tools import list_ports

from dotbot.logger import LOGGER
from dotbot.fauxbot import FauxBot

PAYLOAD_CHUNK_SIZE = 64
PAYLOAD_CHUNK_DELAY = 0.002  # 2 ms


def get_default_port():
    """Return default serial port."""
    ports = [port for port in list_ports.comports()]
    if sys.platform != "win32":
        ports = [port for port in ports if "J-Link" == port.product]
    if not ports:
        return "/dev/ttyACM0"
    # return last JLink port
    return ports[-1].device


class SerialInterfaceException(Exception):
    """Exception raised when serial port is disconnected."""

class SerialInterface(threading.Thread):
    """Bidirectional serial interface."""

    def __init__(self, port: str, baudrate: int, callback: Callable):
        self.callback = callback
        self.serial = serial.Serial(port, baudrate)
        super().__init__(daemon=True)
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("Serial port thread started")

    def run(self):
        """Listen continuously at each byte received on serial."""
        try:
            while 1:
                byte = self.serial.read(1)
                if byte is None:
                    msg = "Serial port disconnected"
                    self._logger.warning(msg)
                    raise SerialInterfaceException(msg)
                self.callback(byte)
        except serial.serialutil.PortNotOpenError as exc:
            self._logger.error(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc
        except serial.serialutil.SerialException as exc:
            self._logger.error(f"{exc}")
            raise SerialInterfaceException(f"{exc}") from exc

    def write(self, bytes_):
        """Write bytes on serial."""
        # Send 64 bytes at a time
        pos = 0
        while (pos % PAYLOAD_CHUNK_SIZE) == 0 and pos < len(bytes_):
            self.serial.write(bytes_[pos : pos + PAYLOAD_CHUNK_SIZE])
            self.serial.flush()
            pos += PAYLOAD_CHUNK_SIZE
            time.sleep(PAYLOAD_CHUNK_DELAY)

class FauxBotSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots"""
    
    def __init__(self, callback:Callable):
        
        # create a robot
        self.dotbot1 = FauxBot("1234567890123456")
        
        # create a second robot??
        self.dotbot2 = FauxBot("4987654321098765")
        
        #for fauxbotObject in FauxBot:
        #    print(fauxbotObject)
        
        self.callback = callback
        super().__init__(daemon=True)
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("FauxBot Simulation Started")
    
        
    def run(self):
    
        advertising_interval = []
        dotBotIterIndex = 0
        for fauxbotObject in FauxBot:
            #print(fauxbotObject.address)
            advertising_interval.append(0)
            
            """Listen continuously at each byte received on the fake serial interface."""
            for byte in fauxbotObject.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
                time.sleep(0.001)
                
        
        advertising_interval1 = 0
        advertising_interval2 = 0
        """Listen continuously at each byte received on the fake serial interface."""
        #for byte in self.dotbot1.advertise():
        #    self.callback(byte.to_bytes(length=1, byteorder="little"))
        #    time.sleep(0.001)
        
        #for byte in self.dotbot2.advertise():
        #    self.callback(byte.to_bytes(length=1, byteorder="little"))
        #    time.sleep(0.001)
        
        while 1:
            for byte in self.dotbot1.update():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
                time.sleep(0.001)
            
            advertising_interval1 += 1
            if (advertising_interval1 == 4):
                for byte in self.dotbot1.advertise():
                    self.callback(byte.to_bytes(length=1, byteorder="little"))
                    time.sleep(0.001)
                advertising_interval1 = 0
            #time.sleep(0.01)
            
            for byte in self.dotbot2.update():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
                time.sleep(0.001)
            
            advertising_interval2 += 1
            if (advertising_interval2 == 4):
                for byte in self.dotbot2.advertise():
                    self.callback(byte.to_bytes(length=1, byteorder="little"))
                    time.sleep(0.001)
                advertising_interval = 0
            time.sleep(0.01)
    
    def write(self, bytes_):
        """Write bytes on the fake serial. It is an identical interface to the real gateway."""
        self.dotbot1.parse_serial_input(bytes_)
        self.dotbot2.parse_serial_input(bytes_)
        
        
