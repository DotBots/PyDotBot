# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Pydantic models used by the controller and server application."""

# pylint: disable=too-few-public-methods,no-name-in-module

from enum import IntEnum
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel

from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.robots import ROBOT_DEFAULT, BodyPose

MAX_POSITION_HISTORY_SIZE = 1000


class DotBotAddressModel(BaseModel):
    """Simple model to hold a DotBot address."""

    address: str


class MqttPinCodeModel(BaseModel):
    """Pin code used to derive crypto keys for MQTT."""

    pin: int


class DotBotMoveRawCommandModel(BaseModel):
    """Model class that defines a move raw command."""

    left_x: int
    left_y: int
    right_x: int
    right_y: int


class DotBotRgbLedCommandModel(BaseModel):
    """Model class that defines an RGB LED command."""

    red: int
    green: int
    blue: int


class DotBotXGOActionCommandModel(BaseModel):
    """Model class that defines an XGO action command."""

    action: int


class DotBotLH2Position(BaseModel):
    """Position of a DotBot."""

    x: float
    y: float


class DotBotControlModeModel(BaseModel):
    """Mode of a DotBot."""

    mode: ControlModeType


class DotBotGPSPosition(BaseModel):
    """GPS position of a DotBot, usually running a SailBot application."""

    latitude: float
    longitude: float


class DotBotWaypoints(BaseModel):
    """Waypoints model.

    An LH2 waypoint is a target for the robot's LH2 photodiode, not for its
    body: the robot has arrived when its photodiode is within `threshold` mm
    of it.
    """

    threshold: int
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]]


class DotBotAreaModel(BaseModel):
    """One named rectangle in frame millimetres."""

    x: int
    y: int
    w: int
    h: int
    name: str = ""


class DotBotSiteModel(BaseModel):
    """The site the controller works in, and the areas it defines.

    `extent_mm` is `[width, height]`, zero at its top-left corner, which is
    where `anchor` points. A site with no measured extent reports none.
    """

    name: str
    anchor: str = ""
    extent_mm: Optional[List[int]] = None
    areas: List[DotBotAreaModel] = []


class DotBotCameraModel(BaseModel):
    """One registered camera, as the console needs it to draw the layer.

    `width` and `height` are the raster's, not the device's: the stream
    carries the area warped at `mm_per_px`, so they are the area's own size
    in raster pixels. `span_mm` is the quadrilateral through the four
    markers' outer corners, in frame millimetres, which is the region the
    registration is trustworthy inside. `coverage_mm` is the source frame's
    own rectangle in the same millimetres, so it is the floor the camera
    can see; empty when the homography maps it to no polygon.
    """

    area: str
    source: Union[int, str]
    mm_per_px: float
    width: int
    height: int
    span_mm: List[List[float]] = []
    coverage_mm: List[List[float]] = []
    residual_mm: float = 0.0
    id: str = ""
    lens: str = ""
    detect: bool = True


class DotBotCameraPoseModel(BaseModel):
    """Where one camera says a robot stands, in frame millimetres.

    `centre_mm` is the board outline's centre, which is what the outline is
    drawn around; `photodiode_mm` is the point the lighthouse reports, so it
    is the one to compare a `lh2_position` against. The two heading
    conventions are named in `dotbot.camera.detection.robot.frame_pose`.
    Both are the BODY's orientation, measured moving or not, which is not
    the quantity the firmware's `direction` reports.
    """

    centre_mm: List[float]
    photodiode_mm: List[float]
    nose_mm: List[float]
    outline_mm: List[List[float]] = []
    heading_deg: float
    heading_atan2_deg: float
    green_flare: float = 0.0
    tmpl_margin: float = 0.0
    refined: bool = False


class DotBotCameraDetectionModel(BaseModel):
    """One camera frame's verdict on whether a robot stands on its area.

    `status` is `found` when both confidence signals clear their floor,
    `refused` when a pose was fitted but one of them did not, and `none`
    when there was nothing to fit, in which case there is no `pose`.
    `sequence` is the warp counter, so a detection can be matched to the
    frame the stream showed, and `timestamp` is when that frame was read
    off the device.

    The detector identifies nothing: one pose per frame, the strongest
    candidate, with no association to any robot address.
    """

    area: str
    camera_id: str = ""
    sequence: int = 0
    timestamp: float = 0.0
    status: str = "none"
    candidates: int = 0
    elapsed_ms: float = 0.0
    pose: Optional[DotBotCameraPoseModel] = None


class DotBotCalibrationReadsModel(BaseModel):
    """How many reads one station contributed to one point."""

    station: int
    reads: int
    target: int


class DotBotCalibrationPointModel(BaseModel):
    """One point of the session: where it is, how to stand there, what it holds."""

    index: int
    x: float
    y: float
    corner: Optional[str] = None
    area: str = ""
    where: str = ""
    how: str = ""
    nose: str = ""
    captured: bool = False
    reads: List[DotBotCalibrationReadsModel] = []
    dropped: int = 0


class DotBotCalibrationStationModel(BaseModel):
    """One solved station and how well it fits its own evidence."""

    index: int
    points: int
    residual_mm: float
    solved_from: str = "direct"


class DotBotCalibrationUnsolvedModel(BaseModel):
    """A station seen at too few points for a homography."""

    index: int
    points: int


class DotBotCalibrationSessionModel(BaseModel):
    """The whole capture session, as every client renders it.

    `expected_error_mm` is None until the predictor exists, and a renderer
    shows the line only when it is a number.
    """

    at: str = ""
    site: str = ""
    # The area the expected error is evaluated over; empty means none chosen.
    area: str = ""
    device: str = ""
    reads: int = 0
    status: str = "collecting"
    outstanding: Optional[int] = None
    captured: int = 0
    total: int = 0
    expected_error_mm: Optional[float] = None
    points: List[DotBotCalibrationPointModel] = []
    stations: List[DotBotCalibrationStationModel] = []
    unsolved: List[DotBotCalibrationUnsolvedModel] = []
    saved_path: Optional[str] = None
    saved_id: str = ""
    error: str = ""


class DotBotCalibrationStartModel(BaseModel):
    """Where this session's points are, in `--points` form.

    `area` names the area the expected error is evaluated over; empty means
    none chosen. `reads` is captures averaged per point; None takes the
    session's own default.
    """

    points: Union[str, List[str]] = "arena:corners"
    device: str = ""
    area: str = ""
    reads: Optional[int] = None


class DotBotCalibrationPreviewModel(BaseModel):
    """What a session over one `--points` specification would open on.

    `reads` is the captures-per-point a start with no `reads` would use.
    """

    points: List[DotBotCalibrationPointModel] = []
    reads: int = 0


class DotBotCalibrationCaptureModel(BaseModel):
    """Which robot takes the outstanding point's reads."""

    device: str = ""


class DotBotCalibrationSaveModel(BaseModel):
    """An optional session label, written into the file's metadata."""

    tag: str = ""


class DotBotCalibrationPushModel(BaseModel):
    """The robots to push to; empty pushes to the whole swarm."""

    devices: List[str] = []


class DotBotCalibrationSavedModel(BaseModel):
    """What a save produced: the file, and the id the robots will report."""

    id: str
    id8: str
    path: Optional[str] = None
    session: DotBotCalibrationSessionModel


class DotBotCalibrationPushedModel(BaseModel):
    """What a push sent, and which robots still do not hold it."""

    id: str
    bytes: int
    stale: List[str] = []


class DotBotConnectionModel(BaseModel):
    """How the controller reaches the swarm, for display in a UI.

    A curated view, not the settings object: the same settings carry
    `mqtt_username` / `mqtt_password`, and this is served to any browser that
    can reach the controller.
    """

    adapter: str  # edge | cloud | dotbot-simulator | sailbot-simulator | serial
    connection: str  # display form: mqtt(s)://host:port, a device path, or simulator
    swarm_id: str  # hex network id
    gw_address: str


class DotBotBuildModel(BaseModel):
    """Which build of pydotbot the controller runs.

    `commit` and `dirty` are present only when the package runs from its own
    git checkout; an installed package reports the version alone.
    """

    version: str
    commit: Optional[str] = None
    dirty: Optional[bool] = None


class DotBotBackgroundMapModel(BaseModel):
    """Background map model."""

    data: Optional[str] = None  # Base64-encoded PNG image data


class DotBotStatus(IntEnum):
    """Status of a DotBot."""

    ACTIVE: int = 0
    INACTIVE: int = 1
    LOST: int = 2


class DotBotQueryModel(BaseModel):
    """Model class used to filter DotBots."""

    limit: Optional[int] = None
    address: Optional[str] = None
    application: Optional[ApplicationType] = None
    status: Optional[DotBotStatus] = None
    max_battery: Optional[float] = None
    min_battery: Optional[float] = None
    max_positions: int = None
    max_position_x: Optional[float] = None
    min_position_x: Optional[float] = None
    max_position_y: Optional[float] = None
    min_position_y: Optional[float] = None


class DotBotRequestType(IntEnum):
    """Request received from MQTT client."""

    DOTBOTS: int = 0
    SITE: int = 1


class DotBotRequestModel(BaseModel):
    """Model class used to handle controller request."""

    request: DotBotRequestType
    reply: str


class DotBotReplyModel(BaseModel):
    """Model class used to handle controller replies."""

    request: DotBotRequestType
    data: Any


class DotBotPoseModel(BaseModel):
    """A robot's body in the arena frame, expanded from its photodiode fix.

    `heading_source` says how `heading_deg` was made: "travel" is the bearing
    between fixes, "ekf" the robot's own estimate, and "none" means there was
    no heading and `heading_deg` is a placeholder.
    """

    heading_deg: float
    heading_source: Literal["none", "travel", "ekf"]
    axle: DotBotLH2Position
    centre: DotBotLH2Position
    nose: DotBotLH2Position
    led: DotBotLH2Position
    outline: List[DotBotLH2Position]
    wheels: List[List[DotBotLH2Position]] = []

    @classmethod
    def from_body_pose(cls, pose: BodyPose) -> "DotBotPoseModel":
        def point(p):
            return DotBotLH2Position(x=p.x, y=p.y)

        return cls(
            heading_deg=pose.heading_deg,
            heading_source=pose.heading_source.name.lower(),
            axle=point(pose.axle),
            centre=point(pose.centre),
            nose=point(pose.nose),
            led=point(pose.led),
            outline=[point(p) for p in pose.outline],
            wheels=[[point(p) for p in wheel] for wheel in pose.wheels],
        )


class DotBotModel(BaseModel):
    """Model class that defines a DotBot."""

    address: str
    application: ApplicationType = ApplicationType.DotBot
    swarm: str = "0000"
    status: DotBotStatus = DotBotStatus.ACTIVE
    mode: ControlModeType = ControlModeType.MANUAL
    last_seen: float
    direction: Optional[int] = None
    wind_angle: Optional[int] = None
    rudder_angle: Optional[int] = None
    sail_angle: Optional[int] = None
    move_raw: Optional[DotBotMoveRawCommandModel] = None
    rgb_led: Optional[DotBotRgbLedCommandModel] = None
    model: str = ROBOT_DEFAULT  # the geometry record's key
    # The LH2 photodiode, not a body point; `pose` is the body.
    lh2_position: Optional[DotBotLH2Position] = None
    pose: Optional[DotBotPoseModel] = None
    gps_position: Optional[DotBotGPSPosition] = None
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    waypoints_threshold: int = 100  # in mm
    position_history: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    calibrated: int = 0x00  # Bitmask: first lighthouse = 0x01, second lighthouse = 0x02
    battery: float = 3.0  # Voltage in Volts


class DotBotNotificationCommand(IntEnum):
    """Notification command of a DotBot."""

    NONE: int = 0
    RELOAD: int = 1
    UPDATE: int = 2
    PIN_CODE_UPDATE: int = 3
    NEW_DOTBOT: int = 4
    CALIBRATION_SESSION_UPDATE: int = 5
    CAMERA_DETECTION: int = 6


class DotBotNotificationUpdate(BaseModel):
    """Update notification model."""

    address: str
    direction: Optional[int] = None
    wind_angle: Optional[int] = None
    rudder_angle: Optional[int] = None
    sail_angle: Optional[int] = None
    lh2_position: Optional[DotBotLH2Position] = None
    pose: Optional[DotBotPoseModel] = None
    gps_position: Optional[DotBotGPSPosition] = None
    battery: Optional[float] = None
    rgb_led: Optional[DotBotRgbLedCommandModel] = None
    lh2_waypoints: Optional[List[DotBotLH2Position]] = None
    gps_waypoints: Optional[List[DotBotGPSPosition]] = None
    waypoints_threshold: Optional[int] = None
    position_history: Optional[List[Union[DotBotLH2Position, DotBotGPSPosition]]] = None


class DotBotNotificationModel(BaseModel):
    """Model class used to send controller notifications."""

    cmd: DotBotNotificationCommand
    data: Optional[Union[DotBotNotificationUpdate, DotBotModel]] = None
    pin_code: Optional[int] = None
    # Carried by CALIBRATION_SESSION_UPDATE; None also means "no session".
    calibration_session: Optional[DotBotCalibrationSessionModel] = None
    # Carried by CAMERA_DETECTION, one message per camera per new warp.
    camera_detection: Optional[DotBotCameraDetectionModel] = None


class WSBase(BaseModel):
    cmd: str
    address: str
    application: ApplicationType


class WSRgbLed(WSBase):
    cmd: Literal["rgb_led"]
    data: DotBotRgbLedCommandModel


class WSMoveRaw(WSBase):
    cmd: Literal["move_raw"]
    data: DotBotMoveRawCommandModel


class WSWaypoints(WSBase):
    cmd: Literal["waypoints"]
    data: DotBotWaypoints


WSMessage = Union[
    WSRgbLed,
    WSMoveRaw,
    WSWaypoints,
]
