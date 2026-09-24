# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the Dotbot protocol API."""

import dataclasses
import struct
from dataclasses import dataclass
from enum import IntEnum

from dotbot_utils.protocol import Payload, PayloadFieldMetadata, register_parser

# The advertised `direction` when the robot has no heading.
DIRECTION_NONE = -1000

# A waypoint heading's value when the point has none.
WAYPOINT_NO_HEADING = 0x7FFF

# The waypoint report's axle coordinate while the robot has no heading.
AXLE_UNKNOWN = 0xFFFF


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
    CMD_WHEEL_VELOCITY = 0x0F
    RAW_DATA = 0x10
    CMD_MAX_SPEED = 0x11
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


class WaypointsStatus(IntEnum):
    """How the last waypoint batch stands, as the robot reports it."""

    NONE = 0
    IN_PROGRESS = 1
    ARRIVED = 2
    FAILED = 3
    ABORTED = 4


class WaypointsFailReason(IntEnum):
    """Why a batch FAILED."""

    NO_HEADING = 1
    TURN = 2
    PROGRESS = 3
    HEADING_LOST = 4
    HOLD = 5
    SETTLE = 6


class WaypointsAbortReason(IntEnum):
    """Why a batch was ABORTED."""

    STOP = 1
    DIRECT = 2
    CONTROL_MODE = 3


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
            PayloadFieldMetadata(name="battery", disp="bat.", length=2),
            PayloadFieldMetadata(name="pwm_left", disp="pwm_l", signed=True),
            PayloadFieldMetadata(name="pwm_right", disp="pwm_r", signed=True),
            PayloadFieldMetadata(name="mode", disp="mode"),
            PayloadFieldMetadata(
                name="encoder_left", disp="enc_l", signed=True, length=4
            ),
            PayloadFieldMetadata(
                name="encoder_right", disp="enc_r", signed=True, length=4
            ),
            PayloadFieldMetadata(name="waypoint_x", disp="wp_x", length=4),
            PayloadFieldMetadata(name="waypoint_y", disp="wp_y", length=4),
            PayloadFieldMetadata(name="waypoint_idx", disp="wp_idx"),
            PayloadFieldMetadata(name="waypoints_status", disp="wp_st"),
            PayloadFieldMetadata(name="waypoints_reason", disp="wp_why"),
            PayloadFieldMetadata(name="batch_id", disp="batch"),
            PayloadFieldMetadata(name="max_speed_10mm", disp="vmax"),
            PayloadFieldMetadata(name="axle_x", disp="axl_x", length=2),
            PayloadFieldMetadata(name="axle_y", disp="axl_y", length=2),
        ]
    )

    calibrated: int = 0x00  # Bitmask: first lighthouse = 0x01, second lighthouse = 0x02
    direction: int = 0xFFFF
    pos_x: int = 0xFFFFFFFF
    pos_y: int = 0xFFFFFFFF
    battery: int = 0
    pwm_left: int = 0
    pwm_right: int = 0
    mode: int = ControlModeType.MANUAL
    encoder_left: int = 0
    encoder_right: int = 0
    waypoint_x: int = 0
    waypoint_y: int = 0
    waypoint_idx: int = 0
    waypoints_status: int = WaypointsStatus.NONE
    waypoints_reason: int = 0
    batch_id: int = 0
    max_speed_10mm: int = 0
    axle_x: int = AXLE_UNKNOWN  # the estimator's axle midpoint, mm
    axle_y: int = AXLE_UNKNOWN
    # Whether the waypoint report (the six fields above) is on the wire; apps
    # other than dotbot-next do not send it
    report: dataclasses.InitVar[bool] = False

    REPORT_SIZE = 8

    def __post_init__(self, report):
        self.has_report = report

    def from_bytes(self, bytes_):
        base = self.size - self.REPORT_SIZE
        self.has_report = len(bytes_) >= self.size
        if self.has_report:
            return super().from_bytes(bytes_)
        if len(bytes_) < base:
            raise ValueError("Not enough bytes to parse")
        return super().from_bytes(bytes(bytes_[:base]) + bytes(self.REPORT_SIZE))

    def to_bytes(self, byteorder="little") -> bytes:
        buffer = super().to_bytes(byteorder)
        return buffer if self.has_report else buffer[: -self.REPORT_SIZE]


@dataclass
class PayloadCommandMaxSpeed(Payload):
    """Dataclass that holds a max speed command, in mm/s; 0 restores the default."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="max_speed_mm_s", disp="vmax", length=2),
        ]
    )

    max_speed_mm_s: int = 0


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
class PayloadCommandWheelVelocity(Payload):
    """Dataclass that holds a wheel velocity command, in mm/s per wheel."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="left_mm_s", disp="l", length=2, signed=True),
            PayloadFieldMetadata(name="right_mm_s", disp="r", length=2, signed=True),
        ]
    )

    left_mm_s: int = 0
    right_mm_s: int = 0


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
        ]
    )

    pos_x: int = 0
    pos_y: int = 0


@dataclass
class PayloadLh2CalibrationHomography(Payload):
    """One basestation's homography, for the station at `index`.

    `homography_matrix` is nine little-endian float32, row-major: the
    `protocol_lh2_homography_t` of DotBot-libs.
    """

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

    @property
    def matrix(self) -> list[list[float]]:
        """The matrix decoded, three rows of three."""
        values = struct.unpack("<9f", bytes(self.homography_matrix))
        return [list(values[row * 3 : row * 3 + 3]) for row in range(3)]


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
class PayloadWaypointHeading(Payload):
    """One waypoint's heading, in centidegrees, 0 facing +y and clockwise
    positive, or WAYPOINT_NO_HEADING."""

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(
                name="heading_cdeg", disp="hdg", length=2, signed=True
            ),
        ]
    )

    heading_cdeg: int = WAYPOINT_NO_HEADING


@dataclass
class PayloadLH2Waypoints(Payload):
    """Dataclass that holds a list of LH2 waypoints.

    Each point is a position for the robot's centre, the axle midpoint. After
    the points comes a trailer: the batch id, which the robot echoes in its
    advertisement and uses to ignore a repeated batch, the heading tolerance
    in degrees and the intermediate pass radius in mm (0 for the firmware's
    defaults), then one heading per point; the robot turns in place to a
    point's heading there. Apps that read only the points ignore the trailer;
    the older dotbot apps steer their photodiode, not the axle, onto a point.
    """

    metadata: list[PayloadFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PayloadFieldMetadata(name="threshold", disp="thr.", length=2),
            PayloadFieldMetadata(name="count", disp="len."),
            PayloadFieldMetadata(name="waypoints", type_=list, length=0),
            PayloadFieldMetadata(name="batch_id", disp="batch"),
            PayloadFieldMetadata(name="heading_tol_deg", disp="tol"),
            PayloadFieldMetadata(name="pass_mm", disp="pass", length=2),
            PayloadFieldMetadata(name="headings", type_=list, length=0),
        ]
    )

    threshold: int = 0
    count: int = 0
    waypoints: list[PayloadLH2Location] = dataclasses.field(default_factory=lambda: [])
    batch_id: int = 0
    heading_tol_deg: int = 0
    pass_mm: int = 0
    headings: list[PayloadWaypointHeading] = dataclasses.field(
        default_factory=lambda: []
    )

    def from_bytes(self, bytes_):
        points_end = 3 + 8 * (bytes_[2] if len(bytes_) > 2 else 0)
        if len(bytes_) >= points_end + 4 + 2 * (points_end - 3) // 8:
            return super().from_bytes(bytes_)
        # No trailer: points only, every one without a heading
        self.batch_id = self.heading_tol_deg = self.pass_mm = 0
        super().from_bytes(
            bytes(bytes_[:points_end])
            + bytes(4)
            + WAYPOINT_NO_HEADING.to_bytes(2, "little") * ((points_end - 3) // 8)
        )
        return self

    def __post_init__(self):
        self._pad_headings()

    def _pad_headings(self):
        """One heading per point, none for those not given one."""
        missing = len(self.waypoints) - len(self.headings)
        if missing > 0:
            self.headings = self.headings + [
                PayloadWaypointHeading() for _ in range(missing)
            ]

    def to_bytes(self, byteorder="little") -> bytes:
        self._pad_headings()
        return super().to_bytes(byteorder)


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
register_parser(PayloadType.CMD_WHEEL_VELOCITY, PayloadCommandWheelVelocity)
register_parser(PayloadType.CMD_MAX_SPEED, PayloadCommandMaxSpeed)
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
