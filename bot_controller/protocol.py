"""Module for the Dotbot protocol API."""

from enum import Enum

PROTOCOL_VERSION = 0


class Command(Enum):
    """Types of DotBot command types."""

    MOVE_RAW = 0
    RGB_LED = 1
