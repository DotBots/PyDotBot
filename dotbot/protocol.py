# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the Dotbot protocol API."""

import dataclasses
import typing
from abc import ABC
from binascii import hexlify
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List

PROTOCOL_VERSION = 1
PAYLOAD_RESERVED_THRESHOLD = 0x80


class PayloadType(IntEnum):
    """Types of DotBot payload types."""

    CMD_MOVE_RAW = 0x00
    CMD_RGB_LED = 0x01
    LH2_RAW_LOCATION = 0x02
    LH2_LOCATION = 0x03
    ADVERTISEMENT = 0x04
    GPS_POSITION = 0x05
    DOTBOT_DATA = 0x06
    CONTROL_MODE = 0x07
    LH2_WAYPOINTS = 0x08
    GPS_WAYPOINTS = 0x09
    SAILBOT_DATA = 0x0A
    CMD_XGO_ACTION = 0x0B
    LH2_PROCESSED_DATA = 0x0C
    LH2_RAW_DATA = 0x0D
    RAW_DATA = 0x10
    LH2_CALIBRATION_HOMOGRAPHY = 0x11
    DOTBOT_SIMULATOR_DATA = 0xFA


class ApplicationType(IntEnum):
    """Types of DotBot applications."""

    DotBot = 0  # pylint: disable=invalid-name
    SailBot = 1  # pylint: disable=invalid-name
    Freebot = 2  # pylint: disable=invalid-name
    XGO = 3
    LH2_mini_mote = 4


class ControlModeType(IntEnum):
    """Types of DotBot control modes."""

    MANUAL = 0
    AUTO = 1


class ProtocolPayloadParserException(Exception):
    """Exception raised on invalid or unsupported payload."""


class PacketType(IntEnum):
    """Types of MAC layer packet."""

    BEACON = 1
    JOIN_REQUEST = 2
    JOIN_RESPONSE = 4
    KEEP_ALIVE = 8
    DATA = 16


@dataclass
class PayloadFieldMetadata:
    """Data class that describes a packet field metadata."""

    name: str = ""
    disp: str = ""
    length: int = 1
    signed: bool = False
    type_: typing.Any = int

    def __post_init__(self):
        if not self.disp:
            self.disp = self.name


@dataclass
class Payload(ABC):
    """Base class for packet classes."""

    @property
    def size(self) -> int:
        return sum(field.length for field in self.metadata)

    def from_bytes(self, bytes_):
        fields = dataclasses.fields(self)
        # base class makes metadata attribute mandatory so there's at least one
        # field defined in subclasses
        # first elements in fields has to be metadata
        if not fields or fields[0].name != "metadata":
            raise ValueError("metadata must be defined first")
        metadata = fields[0].default_factory()
        for idx, field in enumerate(fields[1:]):
            if metadata[idx].type_ is list:
                element_class = typing.get_args(field.type)[0]
                field_attribute = getattr(self, field.name)
                # subclass element is a list and previous attribute is called
                # "count" and should have already been retrieved from the byte
                # stream
                for _ in range(self.count):
                    element = element_class()
                    if len(bytes_) < element.size:
                        raise ValueError("Not enough bytes to parse")
                    field_attribute.append(element.from_bytes(bytes_))
                    bytes_ = bytes_[element.size :]
            elif metadata[idx].type_ in [bytes, bytearray]:
                # subclass element is bytes and previous attribute is called
                # "count" and should have already been retrieved from the byte
                # stream
                length = metadata[idx].length
                if hasattr(self, "count"):
                    length = self.count
                setattr(self, field.name, bytes_[0:length])
                bytes_ = bytes_[length:]
            else:
                length = metadata[idx].length
                if len(bytes_) < length:
                    raise ValueError("Not enough bytes to parse")
                setattr(
                    self,
                    field.name,
                    int.from_bytes(
                        bytes=bytes_[0:length],
                        signed=metadata[idx].signed,
                        byteorder="little",
                    ),
                )
                bytes_ = bytes_[length:]
        return self

    def to_bytes(self, byteorder="little") -> bytes:
        buffer = bytearray()
        metadata = dataclasses.fields(self)[0].default_factory()
        for idx, field in enumerate(dataclasses.fields(self)[1:]):
            value = getattr(self, field.name)
            if isinstance(value, list):
                for element in value:
                    buffer += element.to_bytes()
            elif isinstance(value, (bytes, bytearray)):
                buffer += value
            else:
                buffer += int(value).to_bytes(
                    length=metadata[idx].length,
                    byteorder=byteorder,
                    signed=metadata[idx].signed,
                )
        return buffer


@dataclass
class Header(Payload):
    """Dataclass that holds MAC header fields."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="version", disp="ver.", length=1),
            PayloadFieldMetadata(name="type_", disp="type", length=1),
            PayloadFieldMetadata(name="destination", disp="dst", length=8),
            PayloadFieldMetadata(name="source", disp="src", length=8),
        ]
    )
    version: int = PROTOCOL_VERSION
    type_: int = PacketType.DATA
    destination: int = 0xFFFFFFFFFFFFFFFF
    source: int = 0x0000000000000000


@dataclass
class PayloadAdvertisement(Payload):
    """Dataclass that holds an advertisement (emtpy)."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="application", disp="app"),
        ]
    )

    application: ApplicationType = ApplicationType.DotBot


@dataclass
class PayloadCommandMoveRaw(Payload):
    """Dataclass that holds move raw command data fields."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="lelf_x", disp="lx", signed=True),
            PayloadFieldMetadata(name="lelf_y", disp="ly", signed=True),
            PayloadFieldMetadata(name="right_y", disp="rx", signed=True),
            PayloadFieldMetadata(name="right_y", disp="ry", signed=True),
        ]
    )

    left_x: int = 0
    left_y: int = 0
    right_x: int = 0
    right_y: int = 0


@dataclass
class PayloadCommandRgbLed(Payload):
    """Dataclass that holds a complete rgb led command fields."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="red"),
            PayloadFieldMetadata(name="green"),
            PayloadFieldMetadata(name="blue"),
        ]
    )

    red: int = 0
    green: int = 0
    blue: int = 0


@dataclass
class PayloadCommandXgoAction(Payload):
    """Dataclass that holds an XGO action."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="action"),
        ]
    )
    action: int = 0


@dataclass
class PayloadLh2RawLocation(Payload):
    """Dataclass that holds LH2 raw location data."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="bits", length=8),
            PayloadFieldMetadata(name="polynomial_index", disp="poly", length=1),
            PayloadFieldMetadata(name="offset", disp="off.", length=1, signed=True),
        ]
    )

    bits: int = 0x0000000000000000
    polynomial_index: int = 0x00
    offset: int = 0x00


@dataclass
class PayloadLh2RawData(Payload):
    """Dataclass that holds LH2 raw data."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="count", disp="len"),
            PayloadFieldMetadata(name="locations", type_=list, length=0),
        ]
    )

    count: int = 0
    locations: list[PayloadLh2RawLocation] = dataclasses.field(
        default_factory=lambda: []
    )


@dataclass
class PayloadLh2ProcessedLocation(Payload):
    """Dataclass that holds LH2 processed location data."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="polynomial_index", disp="poly"),
            PayloadFieldMetadata(name="lfsr_index", length=4),
            PayloadFieldMetadata(name="timestamp_us", length=4),
        ]
    )

    polynomial_index: int = 0x00
    lfsr_index: int = 0x00000000
    timestamp_us: int = 0x00000000


@dataclass
class PayloadLH2Location(Payload):
    """Dataclass that holds LH2 computed location data."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="pos_x", disp="x", length=4),
            PayloadFieldMetadata(name="pos_y", disp="y", length=4),
            PayloadFieldMetadata(name="pos_z", disp="z", length=4),
        ]
    )

    pos_x: int = 0
    pos_y: int = 0
    pos_z: int = 0


@dataclass
class PayloadLh2CalibrationHomography(Payload):
    """Dataclass that holds computed LH2 homography for a basestation indicated by index."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="index", disp="idx"),
            PayloadFieldMetadata(name="homography_matrix", disp="mat.", type_=bytes, length=36),
        ]
    )

    index: int = 0
    homography_matrix: bytes = field(default_factory=lambda: bytearray)


@dataclass
class PayloadDotBotData(Payload):
    """Dataclass that holds direction and LH2 raw data from DotBot application."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="direction", disp="dir.", length=2, signed=True),
            PayloadFieldMetadata(name="count", disp="len"),
            PayloadFieldMetadata(name="locations", type_=list, length=0),
        ]
    )

    direction: int = 0xFFFF
    count: int = 0
    locations: List[PayloadLh2RawLocation] = dataclasses.field(
        default_factory=lambda: []
    )


@dataclass
class PayloadGPSPosition(Payload):
    """Dataclass that holds GPS positions."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="latitude", disp="lat.", length=4, signed=True),
            PayloadFieldMetadata(name="longitude", disp="long.", length=4, signed=True),
        ]
    )

    latitude: int = 0
    longitude: int = 0


@dataclass
class PayloadSailBotData(Payload):
    """Dataclass that holds SailBot data from SailBot application."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="direction", disp="dir.", length=2, signed=False),
            PayloadFieldMetadata(name="latitude", disp="lat.", length=4, signed=True),
            PayloadFieldMetadata(name="longitude", disp="long.", length=4, signed=True),
            PayloadFieldMetadata(
                name="wind_angle", disp="wind", length=2, signed=False
            ),
            PayloadFieldMetadata(name="rudder_angle", disp="rud.", signed=True),
            PayloadFieldMetadata(name="sail_angle", disp="sail.", signed=True),
        ]
    )

    direction: int = 0xFFFF
    latitude: int = 0
    longitude: int = 0
    wind_angle: int = 0xFFFF
    rudder_angle: int = 0
    sail_angle: int = 0


@dataclass
class PayloadDotBotSimulatorData(Payload):
    """Dataclass that holds direction and GPS data and heading from SailBot application."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="theta", length=2),
            PayloadFieldMetadata(name="pos_x", length=4),
            PayloadFieldMetadata(name="pos_y", length=4),
        ]
    )

    theta: int = 0xFFFF
    pos_x: int = 0
    pos_y: int = 0


@dataclass
class PayloadControlMode(Payload):
    """Dataclass that holds a control mode message."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [PayloadFieldMetadata(name="mode", disp="mode")]
    )

    mode: ControlModeType = ControlModeType.MANUAL


@dataclass
class PayloadLH2Waypoints(Payload):
    """Dataclass that holds a list of LH2 waypoints."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="threshold", disp="thr."),
            PayloadFieldMetadata(name="count", disp="len."),
            PayloadFieldMetadata(name="waypoints", type_=list, length=0),
        ]
    )

    threshold: int = 0
    count: int = 0
    waypoints: list[PayloadLH2Location] = dataclasses.field(default_factory=lambda: [])


@dataclass
class PayloadGPSWaypoints(Payload):
    """Dataclass that holds a list of GPS waypoints."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="threshold", disp="thr."),
            PayloadFieldMetadata(name="count", disp="len."),
            PayloadFieldMetadata(name="waypoints", type_=list, length=0),
        ]
    )

    threshold: int = 0
    count: int = 0
    waypoints: list[PayloadGPSPosition] = dataclasses.field(default_factory=lambda: [])


@dataclass
class PayloadRawData(Payload):
    """Dataclass that holds raw bytes data."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="count", disp="len."),
            PayloadFieldMetadata(name="data", type_=bytes, length=0),
        ]
    )

    count: int = 0
    data: bytes = dataclasses.field(default_factory=lambda: bytearray)


PAYLOAD_PARSERS: dict[int, Payload] = {
    PayloadType.ADVERTISEMENT: PayloadAdvertisement,
    PayloadType.CMD_MOVE_RAW: PayloadCommandMoveRaw,
    PayloadType.CMD_RGB_LED: PayloadCommandRgbLed,
    PayloadType.CMD_XGO_ACTION: PayloadCommandXgoAction,
    PayloadType.LH2_RAW_LOCATION: PayloadLh2RawLocation,
    PayloadType.LH2_PROCESSED_DATA: PayloadLh2ProcessedLocation,
    PayloadType.LH2_RAW_DATA: PayloadLh2RawData,
    PayloadType.LH2_LOCATION: PayloadLH2Location,
    PayloadType.DOTBOT_DATA: PayloadDotBotData,
    PayloadType.GPS_POSITION: PayloadGPSPosition,
    PayloadType.SAILBOT_DATA: PayloadSailBotData,
    PayloadType.DOTBOT_SIMULATOR_DATA: PayloadDotBotSimulatorData,
    PayloadType.CONTROL_MODE: PayloadControlMode,
    PayloadType.LH2_WAYPOINTS: PayloadLH2Waypoints,
    PayloadType.GPS_WAYPOINTS: PayloadGPSWaypoints,
    PayloadType.RAW_DATA: PayloadRawData,
}


def register_parser(payload_type: int, parser: Payload):
    """Register a new payload parser."""
    if payload_type in PAYLOAD_PARSERS:
        raise ValueError(f"Payload type '0x{payload_type:02X}' already registered")
    if payload_type < PAYLOAD_RESERVED_THRESHOLD:
        raise ValueError(f"Payload type '0x{payload_type:02X}' is reserved")
    PAYLOAD_PARSERS[payload_type] = parser


@dataclass
class Packet:
    """Dataclass that holds a payload."""

    payload_type: int = 0
    payload: Payload = None

    @classmethod
    def from_payload(cls, payload: Payload):
        """Initialize the payload from a packet."""
        payload_type = None
        for type_, cls_ in PAYLOAD_PARSERS.items():
            if cls_ == payload.__class__:
                payload_type = type_
                break
        if payload_type is None:
            raise ValueError(f"Unsupported payload class '{payload.__class__}'")
        return cls(payload_type=payload_type, payload=payload)

    @classmethod
    def from_bytes(cls, bytes_):
        payload_type = int.from_bytes(bytes_[0:1], "little")
        if payload_type not in PAYLOAD_PARSERS:
            raise ProtocolPayloadParserException(
                f"Unsupported payload type '0x{payload_type:02X}'"
            )
        payload = PAYLOAD_PARSERS[payload_type]().from_bytes(bytes_[1:])
        return cls(payload_type=payload_type, payload=payload)

    def to_bytes(self, byteorder="little") -> bytes:
        bytes_ = bytearray()
        bytes_ += int.to_bytes(self.payload_type, 1, byteorder)
        if self.payload is not None:
            bytes_ += self.payload.to_bytes(byteorder)
        return bytes_


@dataclass
class Frame:
    """Data class that holds a payload packet."""

    header: Header = None
    packet: Packet = None

    @property
    def payload_type(self) -> int:
        return self.packet.payload_type

    @classmethod
    def from_bytes(cls, bytes_):
        header = Header().from_bytes(bytes_[0:18])
        packet = Packet().from_bytes(bytes_[18:])
        return cls(header=header, packet=packet)

    def to_bytes(self, byteorder="little") -> bytes:
        header_bytes = self.header.to_bytes(byteorder)
        packet_bytes = self.packet.to_bytes(byteorder)
        return header_bytes + packet_bytes

    def __repr__(self):
        header_separators = [
            "-" * (2 * field.length + 4) for field in self.header.metadata
        ]
        type_separators = ["-" * 6]
        payload_separators = [
            "-" * (2 * field.length + 4)
            for field in self.packet.payload.metadata
            if field.type_ is int
        ]
        payload_separators += [
            "-" * (2 * field_metadata.length + 4)
            for metadata in self.packet.payload.metadata
            if metadata.type_ is list
            for field in getattr(self.packet.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        payload_separators += [
            "-" * (2 * len(getattr(self.packet.payload, field.name)) + 4)
            for field in self.packet.payload.metadata
            if field.type_ is bytes
        ]
        header_names = [
            f" {field.disp:<{2 * field.length + 3}}" for field in self.header.metadata
        ]
        payload_names = [
            f" {field.disp:<{2 * field.length + 3}}"
            for field in self.packet.payload.metadata
            if field.type_ in (int, bytes) and field.length > 0
        ]
        payload_names += [
            f" {field.disp:<{2 * len(getattr(self.packet.payload, field.name)) + 3}}"
            for field in self.packet.payload.metadata
            if field.type_ is bytes and field.length == 0
        ]
        payload_names += [
            f" {field_metadata.disp:<{2 * field_metadata.length + 3}}"
            for metadata in self.packet.payload.metadata
            if metadata.type_ is list
            for field in getattr(self.packet.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        header_values = [
            f" 0x{hexlify(int(getattr(self.header, field.name)).to_bytes(self.header.metadata[idx].length, 'big', signed=self.header.metadata[idx].signed)).decode():<{2 * self.header.metadata[idx].length + 1}}"
            for idx, field in enumerate(dataclasses.fields(self.header)[1:])
        ]
        type_value = [
            f" 0x{hexlify(self.packet.payload_type.to_bytes(1, 'big')).decode():<3}"
        ]
        payload_values = [
            f" 0x{hexlify(int(getattr(self.packet.payload, field.name)).to_bytes(self.packet.payload.metadata[idx].length, 'big', signed=self.packet.payload.metadata[idx].signed)).decode():<{2 * self.packet.payload.metadata[idx].length + 1}}"
            for idx, field in enumerate(dataclasses.fields(self.packet.payload)[1:])
            if self.packet.payload.metadata[idx].type_ is int
        ]
        payload_values += [
            f" 0x{hexlify(int(getattr(field, field_metadata.name)).to_bytes(field_metadata.length, 'big', signed=field_metadata.signed)).decode():<{2 *field_metadata.length + 1}}"
            for metadata in self.packet.payload.metadata
            if metadata.type_ is list
            for field in getattr(self.packet.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        payload_values += [
            f" 0x{hexlify(getattr(self.packet.payload, field.name)).decode():<{2 * self.packet.payload.count + 1}}"
            for idx, field in enumerate(dataclasses.fields(self.packet.payload)[1:])
            if self.packet.payload.metadata[idx].type_ is bytes
            and hasattr(self.packet.payload, "count")
        ]
        payload_values += [
            f" 0x{hexlify(getattr(self.packet.payload, field.name)).decode():<{2 * self.packet.payload.metadata[idx].length + 1}}"
            for idx, field in enumerate(dataclasses.fields(self.packet.payload)[1:])
            if self.packet.payload.metadata[idx].type_ is bytes
            and not hasattr(self.packet.payload, "count")
        ]
        num_bytes = (
            sum(field.length for field in self.header.metadata)
            + 1
            + sum(field.length for field in self.packet.payload.metadata)
        )
        num_bytes += sum(
            field_metadata.length
            for metadata in self.packet.payload.metadata
            if metadata.type_ is list
            for field in getattr(self.packet.payload, metadata.name)
            for field_metadata in field.metadata
        )
        num_bytes += sum(
            len(getattr(self.packet.payload, field.name))
            for field in self.packet.payload.metadata
            if field.type_ is bytes and field.length == 0
        )

        if self.packet.payload_type not in [*PayloadType]:
            payload_type_str = "CUSTOM_DATA"
        else:
            payload_type_str = PayloadType(self.packet.payload_type).name
        if num_bytes > 24:
            # put values on a separate row
            separators = header_separators + type_separators
            names = header_names + [" type "]
            values = header_values + type_value
            return (
                f" {' ' * 16}+{'+'.join(separators)}+\n"
                f" {payload_type_str:<16}|{'|'.join(names)}|\n"
                f" {f'({num_bytes} Bytes)':<16}|{'|'.join(values)}|\n"
                f" {' ' * 16}+{'+'.join(separators)}+\n"
                f" {' ' * 16}+{'+'.join(payload_separators)}+\n"
                f" {' ' * 16}|{'|'.join(payload_names)}|\n"
                f" {' ' * 16}|{'|'.join(payload_values)}|\n"
                f" {' ' * 16}+{'+'.join(payload_separators)}+\n"
            )

        # all in a row by default
        separators = header_separators + type_separators + payload_separators
        names = header_names + [" type "] + payload_names
        values = header_values + type_value + payload_values
        return (
            f" {' ' * 16}+{'+'.join(separators)}+\n"
            f" {payload_type_str:<16}|{'|'.join(names)}|\n"
            f" {f'({num_bytes} Bytes)':<16}|{'|'.join(values)}|\n"
            f" {' ' * 16}+{'+'.join(separators)}+\n"
        )
