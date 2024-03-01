"""Module for the Dotbot protocol API."""

import dataclasses
from abc import ABC, abstractmethod
from binascii import hexlify
from dataclasses import dataclass
from enum import Enum, IntEnum
from itertools import chain
from typing import List

PROTOCOL_VERSION = 8


class PayloadType(Enum):
    """Types of DotBot payload types."""

    CMD_MOVE_RAW    = 0
    CMD_RGB_LED     = 1
    LH2_RAW_DATA    = 2
    LH2_LOCATION    = 3
    ADVERTISEMENT   = 4
    GPS_POSITION    = 5
    DOTBOT_DATA     = 6
    CONTROL_MODE    = 7
    LH2_WAYPOINTS   = 8
    GPS_WAYPOINTS   = 9
    SAILBOT_DATA    = 10
    INVALID_PAYLOAD = 11  # Increase each time a new payload type is added


class ApplicationType(IntEnum):
    """Types of DotBot applications."""

    DotBot = 0  # pylint: disable=invalid-name
    SailBot = 1  # pylint: disable=invalid-name


class ControlModeType(IntEnum):
    """Types of DotBot control modes."""

    MANUAL = 0
    AUTO = 1


class ProtocolPayloadParserException(Exception):
    """Exception raised on invalid or unsupported payload."""


@dataclass
class ProtocolField:
    """Data class that describes a payload field."""

    value: int = 0
    name: str = ""
    length: int = 1
    signed: bool = False


@dataclass
class ProtocolData(ABC):
    """Base class for protocol payload data classes."""

    @property
    @abstractmethod
    def fields(self) -> List[ProtocolField]:
        """Returns the list of fields in this data."""

    @staticmethod
    @abstractmethod
    def from_bytes(bytes_):
        """Returns a ProtocolData instance from a bytearray."""


@dataclass
class ProtocolHeader(ProtocolData):
    """Dataclass that holds header fields."""

    destination: int = 0xFFFFFFFFFFFFFFFF
    source: int = 0x0000000000000000
    swarm_id: int = 0x0000
    application: ApplicationType = ApplicationType.DotBot
    version: int = PROTOCOL_VERSION
    msg_id: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.destination, name="dst", length=8),
            ProtocolField(self.source, name="src", length=8),
            ProtocolField(self.swarm_id, name="swarm id", length=2),
            ProtocolField(self.application, name="app."),
            ProtocolField(self.version, name="ver."),
            ProtocolField(self.msg_id, name="msg id", length=4),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return ProtocolHeader(
            int.from_bytes(bytes_[0:8], "little"),  # destination
            int.from_bytes(bytes_[8:16], "little"),  # source
            int.from_bytes(bytes_[16:18], "little"),  # swarm_id
            ApplicationType(int.from_bytes(bytes_[18:19], "little")),  # application
            int.from_bytes(bytes_[19:20], "little"),  # version
            int.from_bytes(bytes_[20:24], "little"),  # msg id
        )


@dataclass
class CommandMoveRaw(ProtocolData):
    """Dataclass that holds move raw command data fields."""

    left_x: int = 0
    left_y: int = 0
    right_x: int = 0
    right_y: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.left_x, name="lx", length=1, signed=True),
            ProtocolField(self.left_y, name="ly", length=1, signed=True),
            ProtocolField(self.right_x, name="rx", length=1, signed=True),
            ProtocolField(self.right_y, name="ry", length=1, signed=True),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return CommandMoveRaw(*bytes_[0:4])


@dataclass
class CommandRgbLed(ProtocolData):
    """Dataclass that holds a complete rgb led command fields."""

    red: int = 0
    green: int = 0
    blue: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.red, name="red"),
            ProtocolField(self.green, name="green"),
            ProtocolField(self.blue, name="blue"),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return CommandRgbLed(*bytes_[0:3])


@dataclass
class Lh2RawLocation(ProtocolData):
    """Dataclass that holds LH2 raw location data."""

    bits: int = 0x0000000000000000
    polynomial_index: int = 0x00
    offset: int = 0x00

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.bits, name="bits", length=8),
            ProtocolField(self.polynomial_index, name="poly", length=1),
            ProtocolField(self.offset, name="off.", length=1, signed=True),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return Lh2RawLocation(
            int.from_bytes(bytes_[0:8], "little"),
            int.from_bytes(bytes_[8:9], "little"),
            int.from_bytes(bytes_[9:10], "little", signed=True),
        )


@dataclass
class Lh2RawData(ProtocolData):
    """Dataclass that holds LH2 raw data."""

    locations: List[Lh2RawLocation] = dataclasses.field(default_factory=lambda: [])

    @property
    def fields(self) -> List[ProtocolField]:
        return list(chain(*[location.fields for location in self.locations]))

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return Lh2RawData(
            [
                Lh2RawLocation.from_bytes(bytes_[0:10]),
                Lh2RawLocation.from_bytes(bytes_[10:20]),
            ]
        )


@dataclass
class LH2Location(ProtocolData):
    """Dataclass that holds LH2 computed location data."""

    pos_x: int = 0
    pos_y: int = 0
    pos_z: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.pos_x, name="x", length=4),
            ProtocolField(self.pos_y, name="y", length=4),
            ProtocolField(self.pos_z, name="z", length=4),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return LH2Location(
            int.from_bytes(bytes_[0:4], "little"),
            int.from_bytes(bytes_[4:8], "little"),
            int.from_bytes(bytes_[8:12], "little"),
        )


@dataclass
class DotBotData(ProtocolData):
    """Dataclass that holds direction and LH2 raw data from DotBot application."""

    direction: int = 0xFFFF
    locations: List[Lh2RawLocation] = dataclasses.field(default_factory=lambda: [])

    @property
    def fields(self) -> List[ProtocolField]:
        _fields = [ProtocolField(self.direction, name="dir.", length=2, signed=True)]
        _fields += list(chain(*[location.fields for location in self.locations]))
        return _fields

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return DotBotData(
            direction=int.from_bytes(bytes_[0:2], "little", signed=True),
            locations=[
                Lh2RawLocation.from_bytes(bytes_[2:12]),
                Lh2RawLocation.from_bytes(bytes_[12:22]),
            ],
        )


@dataclass
class GPSPosition(ProtocolData):
    """Dataclass that holds GPS positions."""

    latitude: int = 0
    longitude: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.latitude, name="latitude", length=4, signed=True),
            ProtocolField(self.longitude, name="longitude", length=4, signed=True),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return GPSPosition(
            latitude=int.from_bytes(bytes_[0:4], "little", signed=True),
            longitude=int.from_bytes(bytes_[4:8], "little", signed=True),
        )


@dataclass
class SailBotData(ProtocolData):
    """Dataclass that holds SailBot data from SailBot application."""

    # Initialized as 0xFFFF because then at controller .py: -500 <= payload.values.direction <= 500
    direction: int = 0xFFFF
    latitude:  int = 0
    longitude: int = 0
    wind_angle: int = 0xFFFF    # uint angles from 0 to 359
    rudder_angle: int = 0
    sail_angle: int = 0
    
    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.direction, name="dir.", length=2, signed=False),
            ProtocolField(self.latitude, name="latitude", length=4, signed=True),
            ProtocolField(self.longitude, name="longitude", length=4, signed=True),
            ProtocolField(self.wind_angle, name="wind_angle", length=2, signed=False),
            ProtocolField(self.rudder_angle, name="rudder_angle", length=1, signed=True),
            ProtocolField(self.sail_angle, name="sail_angle", length=1, signed=True),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return SailBotData(
            direction = int.from_bytes(bytes_[0:2], "little", signed=False),
            latitude = int.from_bytes(bytes_[2:6], "little", signed=True),
            longitude = int.from_bytes(bytes_[6:10], "little", signed=True),
            wind_angle = int.from_bytes(bytes_[10:12], "little", signed=False),
            rudder_angle = int.from_bytes(bytes_[12:13], "little", signed=True),
            sail_angle = int.from_bytes(bytes_[13:14], "little", signed=True),
        )

@dataclass
class Advertisement(ProtocolData):
    """Dataclass that holds an advertisement (emtpy)."""

    @property
    def fields(self) -> List[ProtocolField]:
        return []

    @staticmethod
    def from_bytes(_: bytes) -> ProtocolData:
        return Advertisement()


@dataclass
class ControlMode(ProtocolData):
    """Dataclass that holds a control mode message."""

    mode: ControlModeType = ControlModeType.MANUAL

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.mode, "mode"),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return ControlMode(bytes_[0])


@dataclass
class LH2Waypoints(ProtocolData):
    """Dataclass that holds a list of LH2 waypoints."""

    threshold: int
    waypoints: List[LH2Location] = dataclasses.field(default_factory=lambda: [])

    @property
    def fields(self) -> List[ProtocolField]:
        _fields = [ProtocolField(len(self.waypoints), name="len.")]
        _fields += [ProtocolField(value=self.threshold, name="thr.")]
        _fields += list(chain(*[waypoint.fields for waypoint in self.waypoints]))
        return _fields

    @staticmethod
    def from_bytes(_) -> ProtocolData:
        return LH2Waypoints(threshold=0, waypoints=[])


@dataclass
class GPSWaypoints(ProtocolData):
    """Dataclass that holds a list of GPS waypoints."""

    threshold: int
    waypoints: List[GPSPosition] = dataclasses.field(default_factory=lambda: [])

    @property
    def fields(self) -> List[ProtocolField]:
        _fields = [ProtocolField(len(self.waypoints), name="len.")]
        _fields += [ProtocolField(value=self.threshold, name="thr.")]
        _fields += list(chain(*[waypoint.fields for waypoint in self.waypoints]))
        return _fields

    @staticmethod
    def from_bytes(_) -> ProtocolData:
        return GPSWaypoints(threshold=0, waypoints=[])


@dataclass
class ProtocolPayload:
    """Manage a protocol complete payload (header + type + values)."""

    header: ProtocolHeader
    payload_type: PayloadType
    values: ProtocolData

    def to_bytes(self, endian="little") -> bytes:
        """Converts a payload to a bytearray."""
        buffer = bytearray()
        for field in self.header.fields:
            buffer += int(field.value).to_bytes(
                length=field.length, byteorder=endian, signed=field.signed
            )
        buffer += int(self.payload_type.value).to_bytes(length=1, byteorder=endian)
        for field in self.values.fields:
            buffer += int(field.value).to_bytes(
                length=field.length, byteorder=endian, signed=field.signed
            )
        return buffer

    @staticmethod
    def from_bytes(bytes_: bytes):
        """Parse a bytearray to return a protocol payload instance."""
        try:
            header = ProtocolHeader.from_bytes(bytes_[0:24])
        except ValueError as exc:
            raise ProtocolPayloadParserException(f"Invalid header: {exc}") from exc
        if header.version != PROTOCOL_VERSION:
            raise ProtocolPayloadParserException(
                f"Invalid header: Unsupported payload version '{header.version}' (expected: {PROTOCOL_VERSION})"
            )
        payload_type = PayloadType(int.from_bytes(bytes_[24:25], "little"))
        if payload_type == PayloadType.CMD_MOVE_RAW:
            values = CommandMoveRaw.from_bytes(bytes_[25:30])
        elif payload_type == PayloadType.CMD_RGB_LED:
            values = CommandRgbLed.from_bytes(bytes_[25:29])
        elif payload_type == PayloadType.LH2_RAW_DATA:
            values = Lh2RawData.from_bytes(bytes_[25:45])
        elif payload_type == PayloadType.LH2_LOCATION:
            values = LH2Location.from_bytes(bytes_[25:37])
        elif payload_type == PayloadType.ADVERTISEMENT:
            values = Advertisement.from_bytes(None)
        elif payload_type == PayloadType.GPS_POSITION:
            values = GPSPosition.from_bytes(bytes_[25:33])
        elif payload_type == PayloadType.DOTBOT_DATA:
            values = DotBotData.from_bytes(bytes_[25:47])
        elif payload_type == PayloadType.SAILBOT_DATA:
            values = SailBotData.from_bytes(bytes_[25:39])
        elif payload_type == PayloadType.CONTROL_MODE:
            values = ControlMode.from_bytes(bytes_[25:26])
        elif payload_type == PayloadType.LH2_WAYPOINTS:
            values = LH2Waypoints.from_bytes(None)
        elif payload_type == PayloadType.GPS_WAYPOINTS:
            values = GPSWaypoints.from_bytes(None)
        else:
            raise ProtocolPayloadParserException(
                f"Unsupported payload type '{payload_type.value}'"
            )
        return ProtocolPayload(header, payload_type, values)

    def __repr__(self):
        header_separators = [
            "-" * (4 * field.length + 2) for field in self.header.fields
        ]
        type_separators = ["-" * 6]  # type
        values_separators = [
            "-" * (4 * field.length + 2) for field in self.values.fields
        ]
        header_names = [
            f" {field.name:<{4 * field.length + 1}}" for field in self.header.fields
        ]
        type_name = [" type "]
        values_names = [
            f" {field.name:<{4 * field.length + 1}}" for field in self.values.fields
        ]
        header_values = [
            f" 0x{hexlify(int(field.value).to_bytes(field.length, 'big', signed=field.signed)).decode():<{4 * field.length - 1}}"
            for field in self.header.fields
        ]
        type_value = [
            f" 0x{hexlify(int(PayloadType(self.payload_type).value).to_bytes(1, 'big')).decode():<3}"
        ]
        values_values = [
            f" 0x{hexlify(int(field.value).to_bytes(field.length, 'big', signed=field.signed)).decode():<{4 * field.length - 1}}"
            for field in self.values.fields
        ]
        num_bytes = (
            sum(field.length for field in self.header.fields)
            + 1
            + sum(field.length for field in self.values.fields)
        )
        if num_bytes > 32:
            # put values on a separate row
            separators = header_separators + type_separators
            names = header_names + type_name
            values = header_values + type_value
            return (
                f" {' ' * 16}+{'+'.join(separators)}+\n"
                f" {PayloadType(self.payload_type).name:<16}|{'|'.join(names)}|\n"
                f" {f'({num_bytes} Bytes)':<16}|{'|'.join(values)}|\n"
                f" {' ' * 16}+{'+'.join(separators)}+\n"
                f" {' ' * 16}+{'+'.join(values_separators)}+\n"
                f" {' ' * 16}|{'|'.join(values_names)}|\n"
                f" {' ' * 16}|{'|'.join(values_values)}|\n"
                f" {' ' * 16}+{'+'.join(values_separators)}+\n"
            )

        # all in a row by default
        separators = header_separators + type_separators + values_separators
        names = header_names + type_name + values_names
        values = header_values + type_value + values_values
        return (
            f" {' ' * 16}+{'+'.join(separators)}+\n"
            f" {PayloadType(self.payload_type).name:<16}|{'|'.join(names)}|\n"
            f" {f'({num_bytes} Bytes)':<16}|{'|'.join(values)}|\n"
            f" {' ' * 16}+{'+'.join(separators)}+\n"
        )
