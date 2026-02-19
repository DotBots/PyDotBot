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
    z: float = 0.0


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


class DotBotMapSizeModel(BaseModel):
    """Map size model."""

    width: int  # in mm unit
    height: int  # in mm unit


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


class DotBotNotificationCommand(IntEnum):
    """Notification command of a DotBot."""

    NONE: int = 0
    RELOAD: int = 1
    UPDATE: int = 2
    PIN_CODE_UPDATE: int = 3


class DotBotNotificationUpdate(BaseModel):
    """Update notification model."""

    address: str
    direction: Optional[int] = None
    wind_angle: Optional[int] = None
    rudder_angle: Optional[int] = None
    sail_angle: Optional[int] = None
    lh2_position: Optional[DotBotLH2Position] = None
    gps_position: Optional[DotBotGPSPosition] = None
    battery: Optional[float] = None


class DotBotNotificationModel(BaseModel):
    """Model class used to send controller notifications."""

    cmd: DotBotNotificationCommand
    data: Optional[DotBotNotificationUpdate] = None
    pin_code: Optional[int] = None


class DotBotRequestType(IntEnum):
    """Request received from MQTT client."""

    DOTBOTS: int = 0
    MAP_SIZE: int = 1


class DotBotRequestModel(BaseModel):
    """Model class used to handle controller request."""

    request: DotBotRequestType
    reply: str


class DotBotReplyModel(BaseModel):
    """Model class used to handle controller replies."""

    request: DotBotRequestType
    data: Any


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
    lh2_position: Optional[DotBotLH2Position] = None
    gps_position: Optional[DotBotGPSPosition] = None
    waypoints: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
    waypoints_threshold: int = 100  # in mm
    position_history: List[Union[DotBotLH2Position, DotBotGPSPosition]] = []
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
