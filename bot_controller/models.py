"""Pydantic models used by the controller and server application."""

from pydantic import BaseModel  # pylint: disable=no-name-in-module


class DotBotModel(BaseModel):  # pylint: disable=too-few-public-methods
    """Model class that defines a DotBot."""

    address: str
    last_seen: float
    active: bool = False
