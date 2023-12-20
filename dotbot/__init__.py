"""Pydotbot module."""

from importlib.metadata import PackageNotFoundError, version

from dotbot.serial_interface import get_default_port

SERIAL_PORT_DEFAULT = get_default_port()
SERIAL_BAUDRATE_DEFAULT = 1000000
DOTBOT_ADDRESS_DEFAULT = "FFFFFFFFFFFFFFFF"  # Broadcast by default
GATEWAY_ADDRESS_DEFAULT = "0000000000000000"
SWARM_ID_DEFAULT = "0000"
CONTROLLER_PROTOCOL_DEFAULT = "http"
CONTROLLER_HOSTNAME_DEFAULT = "localhost"
CONTROLLER_PORT_DEFAULT = "8000"


def pydotbot_version() -> str:
    """Returns the version of the pydotdot package."""
    try:
        return version("pydotbot")
    except PackageNotFoundError:
        return "unknown"
