"""Pydantic models used by the controller and server application."""
# pylint: disable=too-few-public-methods,no-name-in-module

from enum import IntEnum
from typing import List, Optional, Union

from pydantic import BaseModel

from dotbot.protocol import ApplicationType, ControlModeType

MAX_POSITION_HISTORY_SIZE = 1000


class DotBotAddressModel(BaseModel):
    """Simple model to hold a DotBot address."""

    address: str


class DotBotCalibrationStateModel(BaseModel):
    """Model that holds the controller LH2 calibration state."""

    state: str


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


class DotBotLH2Position(BaseModel):
    """Position of a DotBot."""

    x: float
    y: float
    z: float


class DotBotControlModeModel(BaseModel):
    """Mode of a DotBot."""

    mode: ControlModeType


class DotBotGPSPosition(BaseModel):
    """GPS position of a DotBot, usually running a SailBot application."""

    latitude: float
    longitude: float


class DotBotWaypoints(BaseModel):
    """Waypoints model."""

    threshold: int
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]]


class DotBotStatus(IntEnum):
    """Status of a DotBot."""

    ALIVE: int = 0
    LOST: int = 1
    DEAD: int = 2


class DotBotQueryModel(BaseModel):
    """Model class used to filter DotBots."""

    max_positions: int = MAX_POSITION_HISTORY_SIZE
    application: Optional[ApplicationType] = None
    mode: Optional[ControlModeType] = None
    status: Optional[DotBotStatus] = None
    swarm: Optional[str] = None


class DotBotNotificationCommand(IntEnum):
    """Notification command of a DotBot."""

    NONE: int = 0
    RELOAD: int = 1
    UPDATE: int = 2


class DotBotNotificationUpdate(BaseModel):
    """Update notification model."""

    address: str
    direction: Optional[int]
    lh2_position: Optional[DotBotLH2Position] = None
    gps_position: Optional[DotBotGPSPosition] = None


class DotBotNotificationModel(BaseModel):
    """Model class used to send controller notifications."""

    cmd: DotBotNotificationCommand
    data: Optional[DotBotNotificationUpdate] = None


class DotBotModel(BaseModel):
    """Model class that defines a DotBot."""

    address: str
    application: ApplicationType = ApplicationType.DotBot
    swarm: str = "0000"
    status: DotBotStatus = DotBotStatus.ALIVE
    mode: ControlModeType = ControlModeType.MANUAL
    last_seen: float
    direction: Optional[int] = None
    wind_angle: Optional[int] = None
    move_raw: Optional[DotBotMoveRawCommandModel] = None
    rgb_led: Optional[DotBotRgbLedCommandModel] = None
    lh2_position: Optional[DotBotLH2Position] = None
    gps_position: Optional[DotBotGPSPosition] = None
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    waypoints_threshold: int = 40
    position_history: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
