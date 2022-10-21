"""Pydantic models used by the controller and server application."""
# pylint: disable=too-few-public-methods,no-name-in-module

from pydantic import BaseModel


class DotBotModel(BaseModel):
    """Model class that defines a DotBot."""

    address: str
    application: str = "DotBot"
    swarm: str = "0000"
    last_seen: float


class DotBotAddressModel(BaseModel):
    """Simple model to hold a DotBot address."""

    address: str


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
