"""Pydantic models used by the controller and server application."""
# pylint: disable=too-few-public-methods,no-name-in-module

from typing import Optional
from pydantic import BaseModel


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


class DotBotModel(BaseModel):
    """Model class that defines a DotBot."""

    address: str
    application: str = "DotBot"
    swarm: str = "0000"
    last_seen: float
    move_raw: Optional[DotBotMoveRawCommandModel]
    rgb_led: Optional[DotBotRgbLedCommandModel]
    lh2_position: Optional[DotBotLH2Position]
