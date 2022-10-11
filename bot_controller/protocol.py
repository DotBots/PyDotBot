"""Module for the Dotbot protocol API."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from binascii import hexlify

PROTOCOL_VERSION = 1


class Command(Enum):
    """Types of DotBot command types."""

    MOVE_RAW = 0
    RGB_LED = 1
    LH2_RAW_DATA = 2
    LH2_LOCATION = 3


class ProtocolPayloadParserException(Exception):
    """Exception raised on invalid or unsupported payload."""


class ProtocolPayload(ABC):  # pylint: disable=too-few-public-methods
    """Base class for payload classes."""

    @abstractmethod
    def to_bytearray(self) -> bytes:
        """Converts a payload to a bytearray."""


@dataclass
class ProtocolPayloadHeader(ProtocolPayload):
    """Dataclass that holds header fields."""

    destination: int
    source: int
    swarm_id: int
    version: int

    def to_bytearray(self) -> bytes:
        """Converts the header to a bytearray."""

        buffer = bytearray()
        buffer += int(self.destination).to_bytes(8, "big")
        buffer += int(self.source).to_bytes(8, "big")
        buffer += int(self.swarm_id).to_bytes(2, "big")
        buffer += int(self.version).to_bytes(1, "big")
        return buffer

    def __repr__(self):
        dst = hexlify(int(self.destination).to_bytes(8, "big")).decode()
        src = hexlify(int(self.source).to_bytes(8, "big")).decode()
        swarm_id = hexlify(int(self.swarm_id).to_bytes(2, "big")).decode()
        version = hexlify(int(self.version).to_bytes(1, "big")).decode()
        return (
            f"Header: ({len(self.to_bytearray())} bytes)\n"
            "+--------------------+--------------------+----------+---------+\n"
            "|        destination |             source | swarm id | version |\n"
            f"| 0x{dst} | 0x{src} |   0x{swarm_id} |    0x{version} |\n"
            "+--------------------+--------------------+----------+---------+\n"
        )


@dataclass
class ProtocolCommandMoveRaw(ProtocolPayload):
    """Dataclass that holds a complete move raw command fields."""

    header: ProtocolPayloadHeader
    left_x: int
    left_y: int
    right_x: int
    right_y: int

    def to_bytearray(self) -> bytes:
        """Converts the move raw command to a bytearray."""

        buffer = self.header.to_bytearray()
        buffer += int(Command.MOVE_RAW.value).to_bytes(1, "big")
        buffer += int(self.left_x).to_bytes(1, "big", signed=True)
        buffer += int(self.left_y).to_bytes(1, "big", signed=True)
        buffer += int(self.right_x).to_bytes(1, "big", signed=True)
        buffer += int(self.right_y).to_bytes(1, "big", signed=True)
        return buffer

    def __repr__(self):
        return (
            f"{self.header}\n"
            "Move Raw command:\n"
            "+---------+---------+---------+---------+---------+\n"
            "|    type |  left x |  left y | right x | right y |\n"
            f"| {Command.MOVE_RAW.value:7} | {self.left_x:7} | {self.left_y:7} | {self.right_x:7} | {self.right_y:7} |\n"
            "+---------+---------+---------+---------+---------+\n"
        )


@dataclass
class ProtocolCommandRgbLed(ProtocolPayload):
    """Dataclass that holds a complete rgb led command fields."""

    header: ProtocolPayloadHeader
    red: int
    green: int
    blue: int

    def to_bytearray(self) -> bytes:
        """Converts the rgb led command to a bytearray."""

        buffer = self.header.to_bytearray()
        buffer += int(Command.RGB_LED.value).to_bytes(1, "big")
        buffer += int(self.red).to_bytes(1, "big")
        buffer += int(self.green).to_bytes(1, "big")
        buffer += int(self.blue).to_bytes(1, "big")
        return buffer

    def __repr__(self):
        return (
            f"{self.header}\n"
            "RGB LED command:\n"
            "+-------+-------+-------+-------+\n"
            "|  type |   red | green |  blue |\n"
            f"| {Command.RGB_LED.value:5} | {self.red:5} | {self.green:5} | {self.blue:5} |\n"
            "+-------+-------+-------+-------+\n"
        )


def parse_payload(bytes_: bytes) -> ProtocolPayload:
    """Parses a payload."""
    header = ProtocolPayloadHeader(
        int.from_bytes(bytes_[0:8], "big"),  # destination
        int.from_bytes(bytes_[8:16], "big"),  # source
        int.from_bytes(bytes_[16:18], "big"),  # swarm_id
        int.from_bytes(bytes_[18:19], "big"),  # version
    )
    payload_type = Command(int.from_bytes(bytes_[19:20], "big"))
    if payload_type == Command.MOVE_RAW:
        return ProtocolCommandMoveRaw(header, *bytes_[20:25])
    if payload_type == Command.RGB_LED:
        return ProtocolCommandRgbLed(header, *bytes_[20:24])
    raise ProtocolPayloadParserException(f"Unsupported payload type {payload_type}")
