"""Module for the Dotbot protocol API."""

from enum import Enum

PROTOCOL_VERSION = 1
SWARM_ID = 0x0000


class Command(Enum):
    """Types of DotBot command types."""

    MOVE_RAW = 0
    RGB_LED = 1


def command_header(dst, src):
    """Returns the command header.

    >>> command_header(0x1111111111111111, 0x1212121212121212)
    bytearray(b'\\x11\\x11\\x11\\x11\\x11\\x11\\x11\\x11\\x12\\x12\\x12\\x12\\x12\\x12\\x12\\x12\\x00\\x00\\x01')
    """
    header = bytearray()
    header += int(dst).to_bytes(8, "little")  # destination address
    header += int(src).to_bytes(8, "little")  # source address
    header += SWARM_ID.to_bytes(2, "little")  # swarm id
    header += PROTOCOL_VERSION.to_bytes(1, "little")  # firmware version
    return header


def move_raw_command(left_x, left_y, right_x, right_y):
    """Computes and returns a move raw command payload in bytes from positions.

    >>> move_raw_command(0, 0, 0, 0)
    bytearray(b'\\x00\\x00\\x00\\x00\\x00')
    >>> move_raw_command(10, 10, 10, 10)
    bytearray(b'\\x00\\n\\n\\n\\n')
    >>> move_raw_command(0, 0, 0, 0)
    bytearray(b'\\x00\\x00\\x00\\x00\\x00')
    >>> move_raw_command(-10, -10, -10, -10)
    bytearray(b'\\x00\\xf6\\xf6\\xf6\\xf6')
    """
    payload = bytearray()  # init payload
    payload += int(Command.MOVE_RAW.value).to_bytes(1, "little")  # command type
    payload += int(left_x).to_bytes(1, "little", signed=True)
    payload += int(left_y).to_bytes(1, "little", signed=True)
    payload += int(right_x).to_bytes(1, "little", signed=True)
    payload += int(right_y).to_bytes(1, "little", signed=True)
    return payload


def rgb_led_command(red, green, blue):
    """Computes and returns a rgb led command payload in bytes from an RGB color.

    >>> rgb_led_command(0, 0, 0)
    bytearray(b'\\x01\\x00\\x00\\x00')
    >>> rgb_led_command(10, 10, 10)
    bytearray(b'\\x01\\n\\n\\n')
    >>> rgb_led_command(255, 255, 255)
    bytearray(b'\\x01\\xff\\xff\\xff')
    """
    payload = bytearray()
    payload += int(Command.RGB_LED.value).to_bytes(1, "little")
    payload += int(red).to_bytes(1, "little")
    payload += int(green).to_bytes(1, "little")
    payload += int(blue).to_bytes(1, "little")
    return payload
