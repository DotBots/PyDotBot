"""Module for the Dotbot protocol API."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from binascii import hexlify
from typing import List

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
            f"{Command.MOVE_RAW} ({Command.MOVE_RAW.value}):\n"
            "+---------+---------+---------+---------+\n"
            "|  left x |  left y | right x | right y |\n"
            f"| {self.left_x:7} | {self.left_y:7} | {self.right_x:7} | {self.right_y:7} |\n"
            "+---------+---------+---------+---------+\n"
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
            f"{Command.RGB_LED} ({Command.RGB_LED.value}):\n"
            "+-------+-------+-------+\n"
            "|   red | green |  blue |\n"
            f"| {self.red:5} | {self.green:5} | {self.blue:5} |\n"
            "+-------+-------+-------+\n"
        )


@dataclass
class ProtocolLh2RawLocation(ProtocolPayload):
    """Dataclass that holds LH2 raw location."""

    bits: int
    polynomial_index: int
    offset: int

    def to_bytearray(self) -> bytes:
        """Converts the raw location to a bytearray."""
        buffer = bytearray()
        buffer += int(self.bits).to_bytes(8, "big")
        buffer += int(self.polynomial_index).to_bytes(1, "big")
        buffer += int(self.offset).to_bytes(1, "big", signed=True)
        return buffer

    def __repr__(self):
        bits = hexlify(int(self.bits).to_bytes(8, "big")).decode()
        poly = hexlify(int(self.polynomial_index).to_bytes(1, "big")).decode()
        offset = hexlify(int(self.offset).to_bytes(1, "big", signed=True)).decode()
        return (
            "+--------------------+--------+--------+\n"
            "|        bits        |   poly | offset |\n"
            f"| 0x{bits} |   0x{poly} |   0x{offset} |"
        )


@dataclass
class ProtocolLh2RawData(ProtocolPayload):
    """Dataclass that holds LH2 raw data."""

    header: ProtocolPayloadHeader
    locations: List[ProtocolLh2RawLocation]

    def to_bytearray(self) -> bytes:
        """Converts the raw data to a bytearray."""

        buffer = self.header.to_bytearray()
        buffer += int(Command.LH2_RAW_DATA.value).to_bytes(1, "big")
        for location in self.locations:
            buffer += location.to_bytearray()
        return buffer

    def __repr__(self):
        backslash = "\n"
        return (
            f"{self.header}\n"
            f"{Command.LH2_RAW_DATA} ({Command.LH2_RAW_DATA.value}):\n"
            f"{backslash.join([str(location) for location in self.locations])}\n"
            "+--------------------+--------+--------+\n"
        )


class ProtocolParser:
    """Protocol payload parser."""

    def __init__(self, payload: bytes):
        self.payload = payload

    @property
    def protocol(self) -> ProtocolPayload:
        """Return the parsed protocol payload."""
        header = ProtocolPayloadHeader(
            int.from_bytes(self.payload[0:8], "big"),  # destination
            int.from_bytes(self.payload[8:16], "big"),  # source
            int.from_bytes(self.payload[16:18], "big"),  # swarm_id
            int.from_bytes(self.payload[18:19], "big"),  # version
        )
        payload_type = Command(int.from_bytes(self.payload[19:20], "big"))
        if payload_type == Command.MOVE_RAW:
            return ProtocolCommandMoveRaw(header, *self.payload[20:25])
        if payload_type == Command.RGB_LED:
            return ProtocolCommandRgbLed(header, *self.payload[20:24])
        if payload_type == Command.LH2_RAW_DATA:
            return ProtocolLh2RawData(
                header,
                [
                    ProtocolLh2RawLocation(
                        int.from_bytes(self.payload[20:28], "big"),
                        int.from_bytes(self.payload[28:29], "big"),
                        int.from_bytes(self.payload[29:30], "big", signed=True),
                    ),
                    ProtocolLh2RawLocation(
                        int.from_bytes(self.payload[30:38], "big"),
                        int.from_bytes(self.payload[38:39], "big"),
                        int.from_bytes(self.payload[39:40], "big", signed=True),
                    ),
                    ProtocolLh2RawLocation(
                        int.from_bytes(self.payload[40:48], "big"),
                        int.from_bytes(self.payload[48:49], "big"),
                        int.from_bytes(self.payload[49:50], "big", signed=True),
                    ),
                    ProtocolLh2RawLocation(
                        int.from_bytes(self.payload[50:58], "big"),
                        int.from_bytes(self.payload[58:59], "big"),
                        int.from_bytes(self.payload[59:60], "big", signed=True),
                    ),
                ],
            )
        raise ProtocolPayloadParserException(f"Unsupported payload type {payload_type}")

    def __repr__(self):
        return f"{self.protocol}"
