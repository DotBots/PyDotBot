"""Dotbot controller serial interface."""

import serial
from bot_controller.hdlc import hdlc_encode


def write(serial_port: str, serial_baudrate: int, message: bytes):
    """Write bytes on a serial port."""

    with serial.Serial(serial_port, serial_baudrate, timeout=1) as ser:
        ser.write(hdlc_encode(message))
