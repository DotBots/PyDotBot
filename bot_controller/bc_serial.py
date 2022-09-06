"""Dotbot controller serial interface."""

import serial


def write(serial_port: str, serial_baudrate: int, message: bytes):
    """Write bytes on a serial port."""

    with serial.Serial(serial_port, serial_baudrate, timeout=1) as ser:
        ser.write(len(message).to_bytes(1, "little"))
        ser.write(message)
