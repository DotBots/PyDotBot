# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Pydantic models used by the controller and server application."""

# pylint: disable=too-few-public-methods,no-name-in-module

from enum import IntEnum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from dotbot.area import Area, Role
from dotbot.calibration.points import PointsKind
from dotbot.protocol import ApplicationType, ControlModeType, WaypointsStatus
from dotbot.robots import ROBOT_DEFAULT, BodyPose
from dotbot.site import Obstacle, Site, Wall

# Points of trail the controller keeps per robot
MAX_TRAIL_SIZE = 1000


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


class DotBotWheelVelocityCommandModel(BaseModel):
    """Model class that defines a wheel velocity command, in mm/s per wheel."""

    left_mm_s: int = Field(ge=-700, le=700)
    right_mm_s: int = Field(ge=-700, le=700)


class DotBotMaxSpeedCommandModel(BaseModel):
    """Cruise speed limit for waypoint moves, in mm/s; 0 restores the default."""

    max_speed_mm_s: int = Field(ge=0, le=700)


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


class DotBotLH2Waypoint(DotBotLH2Position):
    """An LH2 waypoint: a position for the robot's centre, the axle midpoint.

    With `heading_deg` the robot also turns in place to face it there: degrees
    clockwise from +y, as the advertised `direction`, normalised to [0, 360).
    """

    heading_deg: Optional[float] = Field(default=None, allow_inf_nan=False)

    @field_validator("heading_deg")
    @classmethod
    def _normalise(cls, value: Optional[float]) -> Optional[float]:
        return None if value is None else value % 360.0


def _positions_as_waypoints(value):
    # DotBotLH2Position is left out of the union so that a point whose
    # heading is invalid is refused, not parsed as a point without one
    if not isinstance(value, list):
        return value
    return [
        (
            DotBotLH2Waypoint(x=point.x, y=point.y)
            if type(point) is DotBotLH2Position
            else point
        )
        for point in value
    ]


# One robot's batch. DB_MAX_WAYPOINTS: the firmware drops the points beyond it.
WaypointList = Annotated[
    List[Union[DotBotLH2Waypoint, DotBotGPSPosition]],
    Field(max_length=16),
    BeforeValidator(_positions_as_waypoints),
]


class DotBotWaypointSettings(BaseModel):
    """How a batch is driven, shared by every point in it.

    The robot passes an intermediate point once its centre is within
    `intermediate_threshold` mm of it, or past it along the leg, without
    stopping, and stops at the last one within `threshold` mm; below 5 mm it
    settles at rest until within it. At a point with a heading it stops within
    `threshold`, turns to the heading within `heading_tolerance` degrees, then
    goes on. None leaves the firmware's default.
    """

    threshold: int = Field(ge=0, le=65535)
    intermediate_threshold: Optional[int] = Field(default=None, ge=0, le=65535)
    heading_tolerance: Optional[int] = Field(default=None, ge=0, le=255)


class DotBotWaypoints(DotBotWaypointSettings):
    """Waypoints model.

    Each point is a position for the robot's centre, the axle midpoint (the
    bare dotbot app steers its LH2 photodiode onto it instead). The robot
    drives through the points in order; a point with a heading is a pose.
    """

    waypoints: WaypointList


class DotBotWaypointBatches(DotBotWaypointSettings):
    """One batch per DotBot, keyed by address, all under the same settings.

    An empty list stops that robot and clears its batch.
    """

    dotbots: Dict[str, WaypointList]

    def batch(self, address: str) -> DotBotWaypoints:
        """The batch for one robot, as the single-robot route takes it."""
        return DotBotWaypoints(
            threshold=self.threshold,
            intermediate_threshold=self.intermediate_threshold,
            heading_tolerance=self.heading_tolerance,
            waypoints=self.dotbots[address],
        )


class DotBotWaypointsSent(BaseModel):
    """The DotBots a bulk waypoint request reached, the addresses it named
    that the controller does not know, and the known ones it could not send
    to."""

    applied: List[str]
    unknown: List[str]
    failed: List[str] = []


class DotBotAreaModel(BaseModel):
    """One named rectangle in frame millimetres, and its role if it has one."""

    x: int
    y: int
    w: int
    h: int
    name: str = ""
    role: Optional[Role] = None


class DotBotBarrierModel(BaseModel):
    """A wall (a polyline) or an obstacle (a closed polygon), in frame mm."""

    name: str = ""
    points: List[List[int]]


class DotBotPointsFromModel(BaseModel):
    """How a placement's points were chosen: the field's corners, the corners
    of `area`, a `side_mm` square centred in the field, or given by hand."""

    kind: PointsKind
    area: Optional[str] = None
    side_mm: Optional[int] = None


class DotBotPlacementSpanModel(BaseModel):
    """One placement's points, in frame millimetres, and how they were chosen."""

    points_mm: List[List[float]]
    points_from: Optional[DotBotPointsFromModel] = None


class DotBotCalibrationSpanModel(BaseModel):
    """The loaded LH2 calibration's placements, which span the part of the
    site it was fitted over; positions outside them are extrapolated."""

    id: str
    tag: str = ""
    created_at: str = ""
    placements: List[DotBotPlacementSpanModel] = []

    @classmethod
    def from_calibration(cls, calibration: Any) -> "DotBotCalibrationSpanModel":
        return cls(
            id=calibration.id,
            tag=calibration.tag,
            created_at=calibration.created_at,
            placements=[
                DotBotPlacementSpanModel(
                    points_mm=[list(point) for point in placement.points_mm],
                    points_from=(
                        None
                        if placement.points_from is None
                        else DotBotPointsFromModel(**placement.points_from.to_dict())
                    ),
                )
                for placement in calibration.placements
            ],
        )


class DotBotSiteModel(BaseModel):
    """The site the controller works in, and the areas it defines.

    `extent_mm` is `[width, height]`, zero at its top-left corner, which is
    where `anchor` points. A site with no measured extent reports none.
    `areas` are in the order the config declares them. `field` names the
    area experiments and calibration default to (`Site.field`): an area's
    name, an `x,y,w,h` literal for a site with an extent and no areas, or
    None for a site that declares neither. `calibration` is the LH2
    calibration the controller loaded, if any. `walls` (polylines) and
    `obstacles` (closed polygons) are where robots cannot go.
    """

    name: str
    anchor: str = ""
    extent_mm: Optional[List[int]] = None
    areas: List[DotBotAreaModel] = []
    field: Optional[str] = None
    calibration: Optional[DotBotCalibrationSpanModel] = None
    walls: List[DotBotBarrierModel] = []
    obstacles: List[DotBotBarrierModel] = []

    @classmethod
    def from_site(cls, site: Site, calibration: Any = None) -> "DotBotSiteModel":
        field = site.field
        return cls(
            name=site.name,
            anchor=site.anchor,
            extent_mm=list(site.extent_mm) if site.extent_mm else None,
            areas=[DotBotAreaModel(**a.as_dict()) for a in site.areas.values()],
            field=field.name if field is not None else None,
            walls=[
                DotBotBarrierModel(name=w.name, points=[list(p) for p in w.points])
                for w in site.walls
            ],
            obstacles=[
                DotBotBarrierModel(name=o.name, points=[list(p) for p in o.points])
                for o in site.obstacles
            ],
            calibration=(
                DotBotCalibrationSpanModel.from_calibration(calibration)
                if calibration is not None
                else None
            ),
        )

    def to_site(self) -> Site:
        return Site(
            name=self.name,
            anchor=self.anchor,
            extent_mm=(
                (self.extent_mm[0], self.extent_mm[1]) if self.extent_mm else None
            ),
            areas={
                a.name: Area(a.x, a.y, a.w, a.h, a.name, a.role) for a in self.areas
            },
            walls=[Wall(tuple(tuple(p) for p in w.points), w.name) for w in self.walls],
            obstacles=[
                Obstacle(tuple(tuple(p) for p in o.points), o.name)
                for o in self.obstacles
            ],
        )


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
    wheels_mm: List[List[List[float]]] = []
    heading_deg: float
    heading_atan2_deg: float
    green_flare: float = 0.0
    tmpl_margin: float = 0.0
    refined: bool = False


class DotBotCameraRobotModel(BaseModel):
    """One robot a camera frame found, and whose it is when that is known.

    `address` is the robot whose lighthouse fix stands on this candidate,
    or null when none does. `status` is `found` when both confidence
    signals clear their floor and `refused` when one does not. `timestamp`
    is when the frame the pose was fitted on was read, which is an earlier
    frame's than the detection's own when the frame ran out of time.
    """

    address: Optional[str] = None
    status: str = "found"
    timestamp: float = 0.0
    pose: DotBotCameraPoseModel


class DotBotCameraDetectionModel(BaseModel):
    """One camera frame's verdict on the robots standing on its area.

    `status` is `found` when any robot's pose clears both confidence
    signals, `refused` when poses were fitted but none did, and `none` when
    there was nothing to fit, in which case `robots` is empty. `sequence`
    is the warp counter, so a detection can be matched to the frame the
    stream showed, and `timestamp` is when that frame was read off the
    device. `rate_hz` is the rate the detector was running at.
    """

    area: str
    camera_id: str = ""
    sequence: int = 0
    timestamp: float = 0.0
    status: str = "none"
    candidates: int = 0
    elapsed_ms: float = 0.0
    rate_hz: float = 0.0
    robots: List[DotBotCameraRobotModel] = []


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

    Empty `points` means the site's field corners. `area` names the area the
    expected error is evaluated over; empty means none chosen. `reads` is
    captures averaged per point; None takes the session's own default.
    """

    points: Union[str, List[str]] = []
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
    """How recently a DotBot was last heard, by the controller's thresholds.

    A robot silent past the forget threshold is no status at all: the
    controller drops it until it advertises again.
    """

    ACTIVE: int = 0
    STALE: int = 1
    LOST: int = 2


class DotBotQueryModel(BaseModel):
    """Model class used to filter DotBots."""

    limit: Optional[int] = None
    address: Optional[str] = None
    application: Optional[ApplicationType] = None
    status: Optional[DotBotStatus] = None
    # Lost robots are left out unless asked for, here, by `status` or `address`
    include_lost: bool = False
    max_battery: Optional[float] = None
    min_battery: Optional[float] = None
    # The newest points of each robot's trail to return
    trail: int = Field(default=0, ge=0, le=MAX_TRAIL_SIZE)
    # Add each robot's `body`, its pose expanded into the drawn body
    body: bool = False
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


HeadingSourceName = Literal["none", "travel", "ekf"]


class DotBotPoseModel(BaseModel):
    """Where a robot stands: its axle midpoint in mm and its heading.

    `heading_source` says how `heading_deg` was made: "travel" is the bearing
    between fixes, "ekf" the robot's own estimate, and "none" means there was
    no heading, `heading_deg` is a placeholder and so is the axle, placed
    from the photodiode as if the robot faced it. The body drawn around the
    axle is the robot model's shape turned by `heading_deg`.
    """

    x: float
    y: float
    heading_deg: float
    heading_source: HeadingSourceName


class DotBotBodyModel(BaseModel):
    """A robot's body in the arena frame, expanded from its pose.

    `heading_source` is the pose's.
    """

    heading_deg: float
    heading_source: HeadingSourceName
    photodiode: DotBotLH2Position  # where the pose places the LH2 photodiode
    axle: DotBotLH2Position
    centre: DotBotLH2Position
    nose: DotBotLH2Position
    led: DotBotLH2Position
    outline: List[DotBotLH2Position]
    wheels: List[List[DotBotLH2Position]] = []
    # Radii about the photodiode, whatever the heading: `reach_mm` holds the
    # whole body, tyres included, and `core_mm` is covered by the board.
    reach_mm: float
    core_mm: float
    envelope_mm: float

    @classmethod
    def from_body_pose(cls, pose: BodyPose) -> "DotBotBodyModel":
        # One validation of plain data, rather than one per nested point
        def point(p):
            return {"x": p.x, "y": p.y}

        return cls.model_validate(
            {
                "heading_deg": pose.heading_deg,
                "heading_source": pose.heading_source.name.lower(),
                "photodiode": point(pose.photodiode),
                "axle": point(pose.axle),
                "centre": point(pose.centre),
                "nose": point(pose.nose),
                "led": point(pose.led),
                "outline": [point(p) for p in pose.outline],
                "wheels": [[point(p) for p in wheel] for wheel in pose.wheels],
                "reach_mm": pose.reach_mm,
                "core_mm": pose.core_mm,
                "envelope_mm": pose.envelope_mm,
            }
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
    # The LH2 photodiode, not a body point; `pose` places the body.
    lh2_position: Optional[DotBotLH2Position] = None
    pose: Optional[DotBotPoseModel] = None
    # Only when asked for: the body the pose places, in frame millimetres
    body: Optional[DotBotBodyModel] = None
    gps_position: Optional[DotBotGPSPosition] = None
    waypoints: List[Union[DotBotLH2Waypoint, DotBotLH2Position, DotBotGPSPosition]] = []
    waypoints_threshold: int = 100  # in mm
    # The waypoint report, from apps that send one (the sandbox dotbot app)
    waypoints_status: Optional[WaypointsStatus] = None
    waypoints_reason: Optional[str] = None  # why FAILED or ABORTED
    waypoint_index: Optional[int] = (
        None  # the point being driven to; the count once arrived
    )
    max_speed: Optional[int] = None  # cruise speed limit in force, mm/s
    axle_position: Optional[DotBotLH2Position] = None  # the robot's own estimate
    # Where the robot has been, oldest first
    trail: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    calibrated: int = 0x00  # Bitmask: first lighthouse = 0x01, second lighthouse = 0x02
    battery: float = 3.0  # Voltage in Volts


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
