"""Pydantic models used by the controller and server application."""
# pylint: disable=too-few-public-methods,no-name-in-module

from enum import IntEnum
from typing import List, Optional, Union
from pydantic import BaseModel

from dotbot.protocol import ApplicationType, ControlModeType


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


class DotBotStatus(IntEnum):
    """Status of a DotBot."""

    ALIVE: int = 0
    LOST: int = 1
    DEAD: int = 2


class DotBotQueryModel(BaseModel):
    """Model class used to filter DotBots."""

    max_positions: int = 100
    application: Optional[ApplicationType] = None
    mode: Optional[ControlModeType] = None
    status: Optional[DotBotStatus] = None
    swarm: Optional[str] = None


class DotBotModel(BaseModel):
    """Model class that defines a DotBot."""

    address: str
    application: ApplicationType = ApplicationType.DotBot
    swarm: str = "0000"
    status: DotBotStatus = DotBotStatus.ALIVE
    mode: ControlModeType = ControlModeType.MANUAL
    last_seen: float
    direction: Optional[int]
    move_raw: Optional[DotBotMoveRawCommandModel]
    rgb_led: Optional[DotBotRgbLedCommandModel]
    lh2_position: Optional[DotBotLH2Position]
    gps_position: Optional[DotBotGPSPosition]
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    position_history: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
