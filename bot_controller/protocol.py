from enum import Enum

PROTOCOL_VERSION = 0


class Command(Enum):
    MOVE_RAW = 0
    RGB_LED = 1
