"""Pydotbot module."""

from importlib.metadata import version, PackageNotFoundError


SERIAL_PORT_DEFAULT = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 1000000
DOTBOT_ADDRESS_DEFAULT = "FFFFFFFFFFFFFFFF"  # Broadcast by default
GATEWAY_ADDRESS_DEFAULT = "0000000000000000"
SWARM_ID_DEFAULT = "0000"


def pydotbot_version() -> str:
    """Returns the version of the pydotdot package."""
    try:
        return version("pydotbot")
    except PackageNotFoundError:
        return "unknown"
