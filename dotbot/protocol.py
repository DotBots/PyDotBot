# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the Dotbot protocol API."""

import dataclasses
from dataclasses import dataclass
from enum import IntEnum

from dotbot_utils.protocol import Payload, PayloadFieldMetadata, register_parser


class PayloadType(IntEnum):
    """Types of DotBot payload types."""

    CMD_MOVE_RAW = 0x00
    CMD_RGB_LED = 0x01
    ADVERTISEMENT = 0x04
    GPS_POSITION = 0x05
    DOTBOT_ADVERTISEMENT = 0x06
    CONTROL_MODE = 0x07
    LH2_WAYPOINTS = 0x08
    GPS_WAYPOINTS = 0x09
    SAILBOT_DATA = 0x0A
    CMD_XGO_ACTION = 0x0B
    LH2_PROCESSED_DATA = 0x0C
    LH2_CALIBRATION_HOMOGRAPHY = 0x0E
    RAW_DATA = 0x10
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
class PayloadDotBotAdvertisement(Payload):
    """Dataclass that holds a dotbot advertisement packet."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="calibrated", disp="cal."),
            PayloadFieldMetadata(name="direction", disp="dir.", length=2, signed=True),
            PayloadFieldMetadata(name="pos_x", disp="x", length=4),
            PayloadFieldMetadata(name="pos_y", disp="y", length=4),
            PayloadFieldMetadata(name="pos_z", disp="z", length=4),
            PayloadFieldMetadata(name="battery", disp="bat.", length=2),
        ]
    )

    calibrated: int = 0x00  # Bitmask: first lighthouse = 0x01, second lighthouse = 0x02
    direction: int = 0xFFFF
    pos_x: int = 0xFFFFFFFF
    pos_y: int = 0xFFFFFFFF
    pos_z: int = 0xFFFFFFFF
    battery: int = 0


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
            PayloadFieldMetadata(
                name="homography_matrix", disp="mat.", type_=bytes, length=36
            ),
        ]
    )

    index: int = 0
    homography_matrix: bytes = dataclasses.field(default_factory=lambda: bytearray)


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


register_parser(PayloadType.ADVERTISEMENT, PayloadAdvertisement)
register_parser(PayloadType.CMD_MOVE_RAW, PayloadCommandMoveRaw)
register_parser(PayloadType.CMD_RGB_LED, PayloadCommandRgbLed)
register_parser(PayloadType.CMD_XGO_ACTION, PayloadCommandXgoAction)
register_parser(PayloadType.LH2_PROCESSED_DATA, PayloadLh2ProcessedLocation)
register_parser(PayloadType.DOTBOT_ADVERTISEMENT, PayloadDotBotAdvertisement)
register_parser(PayloadType.GPS_POSITION, PayloadGPSPosition)
register_parser(PayloadType.SAILBOT_DATA, PayloadSailBotData)
register_parser(PayloadType.DOTBOT_SIMULATOR_DATA, PayloadDotBotSimulatorData)
register_parser(PayloadType.CONTROL_MODE, PayloadControlMode)
register_parser(PayloadType.LH2_WAYPOINTS, PayloadLH2Waypoints)
register_parser(PayloadType.GPS_WAYPOINTS, PayloadGPSWaypoints)
register_parser(PayloadType.RAW_DATA, PayloadRawData)
register_parser(PayloadType.LH2_CALIBRATION_HOMOGRAPHY, PayloadLh2CalibrationHomography)
