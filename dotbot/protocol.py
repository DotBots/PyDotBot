# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the Dotbot protocol API."""

import dataclasses
import typing
from abc import ABC, abstractmethod
from binascii import hexlify
from dataclasses import dataclass
from enum import Enum, IntEnum
from itertools import chain
from typing import List

PROTOCOL_VERSION = 9


class PayloadType(Enum):
    """Types of DotBot payload types."""

    CMD_MOVE_RAW = 0
    CMD_RGB_LED = 1
    LH2_RAW_LOCATION = 2
    LH2_LOCATION = 3
    ADVERTISEMENT = 4
    GPS_POSITION = 5
    DOTBOT_DATA = 6
    CONTROL_MODE = 7
    LH2_WAYPOINTS = 8
    GPS_WAYPOINTS = 9
    SAILBOT_DATA = 10
    CMD_XGO_ACTION = 11
    LH2_PROCESSED_DATA = 12
    LH2_RAW_DATA = 13
    INVALID_PAYLOAD = 14  # Increase each time a new payload type is added
    DOTBOT_SIMULATOR_DATA = 250
    TEST_NOT_REGISTERED = 253
    TEST = 254


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


class PacketType(Enum):
    """Types of MAC layer packet."""

    BEACON = 1
    JOIN_REQUEST = 2
    JOIN_RESPONSE = 3
    LEAVE = 4
    DATA = 5


@dataclass
class PacketFieldMetadata:
    """Data class that describes a packet field metadata."""

    name: str = ""
    disp: str = ""
    length: int = 1
    signed: bool = False
    type_: typing.Any = int


@dataclass
class Packet(ABC):
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
            if metadata[idx].type_ == list:
                element_class =  typing.get_args(field.type)[0]
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
            else:
                buffer += int(value).to_bytes(
                    length=metadata[idx].length,
                    byteorder=byteorder,
                    signed=metadata[idx].signed,
                )
        return buffer


@dataclass
class Header(Packet):
    """Dataclass that holds MAC header fields."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="version", disp="ver.", length=1),
            PacketFieldMetadata(name="type_", disp="type", length=1),
            PacketFieldMetadata(name="destination", disp="dst", length=8),
            PacketFieldMetadata(name="source", disp="src", length=8),
        ]
    )
    version: int = PROTOCOL_VERSION
    type_: PacketType = PacketType.BEACON
    destination: int = 0xFFFFFFFFFFFFFFFF
    source: int = 0x0000000000000000


@dataclass
class PayloadAdvertisement(Packet):
    """Dataclass that holds an advertisement (emtpy)."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="application", disp="app"),
        ]
    )

    application: ApplicationType = ApplicationType.DotBot


@dataclass
class PayloadCommandMoveRaw(Packet):
    """Dataclass that holds move raw command data fields."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="lelf_x", disp="lx", signed=True),
            PacketFieldMetadata(name="lelf_y", disp="ly", signed=True),
            PacketFieldMetadata(name="right_y", disp="rx", signed=True),
            PacketFieldMetadata(name="right_y", disp="ry", signed=True),
        ]
    )

    left_x: int = 0
    left_y: int = 0
    right_x: int = 0
    right_y: int = 0


@dataclass
class PayloadCommandRgbLed(Packet):
    """Dataclass that holds a complete rgb led command fields."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="red", disp="red"),
            PacketFieldMetadata(name="green", disp="green"),
            PacketFieldMetadata(name="blue", disp="blue"),
        ]
    )

    red: int = 0
    green: int = 0
    blue: int = 0


@dataclass
class PayloadCommandXgoAction(Packet):
    """Dataclass that holds an XGO action."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="action", disp="action"),
        ]
    )
    action: int = 0


@dataclass
class PayloadLh2RawLocation(Packet):
    """Dataclass that holds LH2 raw location data."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="bits", disp="bits", length=8),
            PacketFieldMetadata(name="polynomial_index", disp="poly", length=1),
            PacketFieldMetadata(name="offset", disp="off.", length=1, signed=True),
        ]
    )

    bits: int = 0x0000000000000000
    polynomial_index: int = 0x00
    offset: int = 0x00


@dataclass
class PayloadLh2RawData(Packet):
    """Dataclass that holds LH2 raw data."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="count", disp="len"),
            PacketFieldMetadata(name="locations", type_=list, length=0),
        ]
    )

    count: int = 0
    locations: list[PayloadLh2RawLocation] = dataclasses.field(
        default_factory=lambda: []
    )


@dataclass
class PayloadLh2ProcessedLocation(Packet):
    """Dataclass that holds LH2 processed location data."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="polynomial_index", disp="poly"),
            PacketFieldMetadata(name="lfsr_index", disp="lfsr_index", length=4),
            PacketFieldMetadata(name="timestamp_us", disp="off.", length=4),
        ]
    )

    polynomial_index: int = 0x00
    lfsr_index: int = 0x00000000
    timestamp_us: int = 0x00000000


@dataclass
class PayloadLH2Location(Packet):
    """Dataclass that holds LH2 computed location data."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="pos_x", disp="x", length=4),
            PacketFieldMetadata(name="pos_y", disp="y", length=4),
            PacketFieldMetadata(name="pos_z", disp="z", length=4),
        ]
    )

    pos_x: int = 0
    pos_y: int = 0
    pos_z: int = 0


@dataclass
class PayloadDotBotData(Packet):
    """Dataclass that holds direction and LH2 raw data from DotBot application."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="direction", disp="dir.", length=2, signed=True),
            PacketFieldMetadata(name="count", disp="len"),
            PacketFieldMetadata(name="locations", type_=list, length=0),
        ]
    )

    direction: int = 0xFFFF
    count: int = 0
    locations: List[PayloadLh2RawLocation] = dataclasses.field(
        default_factory=lambda: []
    )


@dataclass
class PayloadGPSPosition(Packet):
    """Dataclass that holds GPS positions."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="latitude", disp="lat.", length=4, signed=True),
            PacketFieldMetadata(name="longitude", disp="long.", length=4, signed=True),
        ]
    )

    latitude: int = 0
    longitude: int = 0


@dataclass
class PayloadSailBotData(Packet):
    """Dataclass that holds SailBot data from SailBot application."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="direction", disp="dir.", length=2, signed=False),
            PacketFieldMetadata(name="latitude", disp="lat.", length=4, signed=True),
            PacketFieldMetadata(name="longitude", disp="long.", length=4, signed=True),
            PacketFieldMetadata(
                name="wind_angle", disp="wind ang", length=2, signed=False
            ),
            PacketFieldMetadata(name="rudder_angle", disp="rud.", signed=True),
            PacketFieldMetadata(name="sail_angle", disp="sail.", signed=True),
        ]
    )

    direction: int = 0xFFFF
    latitude: int = 0
    longitude: int = 0
    wind_angle: int = 0xFFFF
    rudder_angle: int = 0
    sail_angle: int = 0


@dataclass
class PayloadDotBotSimulatorData(Packet):
    """Dataclass that holds direction and GPS data and heading from SailBot application."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="theta", disp="theta", length=2),
            PacketFieldMetadata(name="pos_x", disp="pos_x", length=4),
            PacketFieldMetadata(name="pos_y", disp="pos_y", length=4),
        ]
    )

    theta: int = 0xFFFF
    pos_x: int = 0
    pos_y: int = 0


@dataclass
class PayloadControlMode(Packet):
    """Dataclass that holds a control mode message."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [PacketFieldMetadata(name="mode", disp="mode")]
    )

    mode: ControlModeType = ControlModeType.MANUAL


@dataclass
class PayloadLH2Waypoints(Packet):
    """Dataclass that holds a list of LH2 waypoints."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="threshold", disp="thr."),
            PacketFieldMetadata(name="count", disp="len."),
            PacketFieldMetadata(name="waypoints", type_=list, length=0),
        ]
    )

    threshold: int = 0
    count: int = 0
    waypoints: list[PayloadLH2Location] = dataclasses.field(default_factory=lambda: [])


@dataclass
class PayloadGPSWaypoints(Packet):
    """Dataclass that holds a list of GPS waypoints."""

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="threshold", disp="thr."),
            PacketFieldMetadata(name="count", disp="len."),
            PacketFieldMetadata(name="waypoints", type_=list, length=0),
        ]
    )

    threshold: int = 0
    count: int = 0
    waypoints: list[PayloadGPSPosition] = dataclasses.field(default_factory=lambda: [])


PAYLOAD_PARSERS: dict[PayloadType, Packet] = {
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
}


def register_parser(payload_type: PayloadType, parser):
    PAYLOAD_PARSERS[payload_type] = parser


@dataclass
class PayloadFrame:
    """Data class that holds a payload packet."""

    header: Header = None
    payload: Packet = None

    @property
    def payload_type(self) -> PayloadType:
        for payload_type, cls_ in PAYLOAD_PARSERS.items():
            if cls_ == self.payload.__class__:
                return payload_type
        raise ValueError(f"Unsupported payload class '{self.payload.__class__}'")

    def from_bytes(self, bytes_):
        self.header = Header().from_bytes(bytes_[0:18])
        payload_type = PayloadType(int.from_bytes(bytes_[18:19], "little"))
        if payload_type not in PAYLOAD_PARSERS:
            raise ProtocolPayloadParserException(
                f"Unsupported payload type '{payload_type}'"
            )
        self.payload = PAYLOAD_PARSERS[payload_type]().from_bytes(bytes_[19:])
        return self

    def to_bytes(self, byteorder="little") -> bytes:
        header_bytes = self.header.to_bytes(byteorder)
        payload_bytes = self.payload.to_bytes(byteorder)
        return header_bytes + int.to_bytes(self.payload_type.value) + payload_bytes

    def __repr__(self):
        header_separators = [
            "-" * (4 * field.length + 2) for field in self.header.metadata
        ]
        type_separators = ["-" * 6]
        payload_separators = [
            "-" * (4 * field.length + 2) for field in self.payload.metadata if field.type_ != list
        ]
        payload_separators += [
            "-" * (4 * field_metadata.length + 2)
            for metadata in self.payload.metadata if metadata.type_ == list
            for field in getattr(self.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        header_names = [
            f" {field.disp:<{4 * field.length + 1}}" for field in self.header.metadata
        ]
        payload_names = [
            f" {field.disp:<{4 * field.length + 1}}" for field in self.payload.metadata if field.type_ != list
        ]
        payload_names += [
            f" {field_metadata.disp:<{4 * field_metadata.length + 1}}"
            for metadata in self.payload.metadata if metadata.type_ == list
            for field in getattr(self.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        header_values = [
            f" 0x{hexlify(int(getattr(self.header, field.name)).to_bytes(self.header.metadata[idx].length, 'big', signed=self.header.metadata[idx].signed)).decode():<{4 * self.header.metadata[idx].length - 1}}"
            for idx, field in enumerate(dataclasses.fields(self.header)[1:])
        ]
        type_value = [
            f" 0x{hexlify(int(PayloadType(self.payload_type).value).to_bytes(1, 'big')).decode():<3}"
        ]
        payload_values = [
            f" 0x{hexlify(int(getattr(self.payload, field.name)).to_bytes(self.payload.metadata[idx].length, 'big', signed=self.payload.metadata[idx].signed)).decode():<{4 * self.payload.metadata[idx].length - 1}}"
            for idx, field in enumerate(dataclasses.fields(self.payload)[1:]) if self.payload.metadata[idx].type_ != list
        ]
        payload_values += [
            f" 0x{hexlify(int(getattr(field, field_metadata.name)).to_bytes(field_metadata.length, 'big', signed=field_metadata.signed)).decode():<{4 *field_metadata.length - 1}}"
            for metadata in self.payload.metadata if metadata.type_ == list
            for field in getattr(self.payload, metadata.name)
            for field_metadata in field.metadata
        ]
        num_bytes = (
            sum(field.length for field in self.header.metadata)
            + 1
            + sum(field.length for field in self.payload.metadata)
        )
        num_bytes += sum(
            field_metadata.length for metadata in self.payload.metadata if metadata.type_ == list
            for field in getattr(self.payload, metadata.name)
            for field_metadata in field.metadata
        )

        if num_bytes > 24:
            # put values on a separate row
            separators = header_separators + type_separators
            names = header_names + [" type "]
            values = header_values + type_value
            return (
                f" {' ' * 16}+{'+'.join(separators)}+\n"
                f" {PayloadType(self.payload_type).name:<16}|{'|'.join(names)}|\n"
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
            f" {PayloadType(self.payload_type).name:<16}|{'|'.join(names)}|\n"
            f" {f'({num_bytes} Bytes)':<16}|{'|'.join(values)}|\n"
            f" {' ' * 16}+{'+'.join(separators)}+\n"
        )


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
class CommandXgoAction(ProtocolData):
    """Dataclass that holds an XGO action."""

    action: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.action, name="action"),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return CommandXgoAction(bytes_[0])


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
class Lh2ProcessedLocation(ProtocolData):
    """Dataclass that holds LH2 processed location data."""

    polynomial_index: int = 0x00
    lfsr_index: int = 0x00000000
    timestamp_us: int = 0x00000000

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.polynomial_index, name="poly", length=1),
            ProtocolField(self.lfsr_index, name="lfsr_index", length=4),
            ProtocolField(self.timestamp_us, name="timestamp_us", length=4),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return Lh2ProcessedLocation(
            int.from_bytes(bytes_[0:1], "little"),
            int.from_bytes(bytes_[1:5], "little"),
            int.from_bytes(bytes_[5:9], "little"),
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

    direction: int = 0xFFFF
    latitude: int = 0
    longitude: int = 0
    wind_angle: int = 0xFFFF  # uint angles from 0 to 359
    rudder_angle: int = 0
    sail_angle: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.direction, name="dir.", length=2, signed=False),
            ProtocolField(self.latitude, name="latitude", length=4, signed=True),
            ProtocolField(self.longitude, name="longitude", length=4, signed=True),
            ProtocolField(self.wind_angle, name="wind ang", length=2, signed=False),
            ProtocolField(self.rudder_angle, name="rud.", length=1, signed=True),
            ProtocolField(self.sail_angle, name="sail.", length=1, signed=True),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return SailBotData(
            direction=int.from_bytes(bytes_[0:2], "little", signed=False),
            latitude=int.from_bytes(bytes_[2:6], "little", signed=True),
            longitude=int.from_bytes(bytes_[6:10], "little", signed=True),
            wind_angle=int.from_bytes(bytes_[10:12], "little", signed=False),
            rudder_angle=int.from_bytes(bytes_[12:13], "little", signed=True),
            sail_angle=int.from_bytes(bytes_[13:14], "little", signed=True),
        )


@dataclass
class DotBotSimulatorData(ProtocolData):
    """Dataclass that holds direction and GPS data and heading from SailBot application."""

    theta: int = 0xFFFF
    pos_x: int = 0
    pos_y: int = 0

    @property
    def fields(self) -> List[ProtocolField]:
        return [
            ProtocolField(self.theta, name="theta", length=2),
            ProtocolField(self.pos_x, name="pos_x", length=4),
            ProtocolField(self.pos_y, name="pos_y", length=4),
        ]

    @staticmethod
    def from_bytes(bytes_) -> ProtocolData:
        return DotBotSimulatorData(
            theta=int.from_bytes(bytes_[0:2], "little"),
            pos_x=int.from_bytes(bytes_[2:6], "little"),
            pos_y=int.from_bytes(bytes_[6:10], "little"),
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
    def from_bytes(bytes_) -> ProtocolData:
        waypoints_count = int(bytes_[0])
        threshold = int(bytes_[1])
        waypoints_bytes = bytes_[2:]
        waypoints = []
        for idx in range(waypoints_count):
            for i in range(3):
                waypoints.append(
                    int.from_bytes(
                        waypoints_bytes[12 * idx + i * 4 : 12 * idx + (i + 1) * 4],
                        byteorder="little",
                    )
                )
        waypoints = [
            (waypoints[i], waypoints[i + 1], waypoints[i + 2])
            for i in range(0, 3 * waypoints_count, 3)
        ]
        return LH2Waypoints(threshold=threshold, waypoints=waypoints)


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
    def from_bytes(bytes_) -> ProtocolData:
        waypoints_count = int(bytes_[0])
        threshold = int(bytes_[1])
        waypoints_bytes = bytes_[2:]
        waypoints = []
        for idx in range(2 * waypoints_count):
            waypoints.append(
                float(
                    int.from_bytes(
                        waypoints_bytes[4 * idx : 4 * (idx + 1)], byteorder="little"
                    )
                    / 1e6
                )
            )
        waypoints = [
            (waypoints[i], waypoints[i + 1]) for i in range(0, 2 * waypoints_count, 2)
        ]
        return GPSWaypoints(threshold=threshold, waypoints=waypoints)


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
        elif payload_type == PayloadType.DOTBOT_SIMULATOR_DATA:
            values = DotBotSimulatorData.from_bytes(bytes_[25:35])
        elif payload_type == PayloadType.CONTROL_MODE:
            values = ControlMode.from_bytes(bytes_[25:26])
        elif payload_type == PayloadType.LH2_WAYPOINTS:
            values = LH2Waypoints.from_bytes(bytes_[25:])
        elif payload_type == PayloadType.GPS_WAYPOINTS:
            values = GPSWaypoints.from_bytes(bytes_[25:])
        elif payload_type == PayloadType.LH2_PROCESSED_DATA:
            values = Lh2ProcessedLocation.from_bytes(bytes_[25:34])
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
