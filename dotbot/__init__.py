"""Pydotbot module."""

from binascii import hexlify
from importlib.metadata import PackageNotFoundError, version

from dotbot_utils.serial_interface import get_default_port

SERIAL_PORT_DEFAULT = get_default_port()
SERIAL_BAUDRATE_DEFAULT = 1000000
DOTBOT_ADDRESS_DEFAULT = "FFFFFFFFFFFFFFFF"  # Broadcast by default
GATEWAY_ADDRESS_DEFAULT = "0000000000000000"
NETWORK_ID_DEFAULT = "0000"
CONTROLLER_HTTP_PROTOCOL_DEFAULT = "http"
CONTROLLER_HTTP_HOSTNAME_DEFAULT = "localhost"
CONTROLLER_HTTP_PORT_DEFAULT = 8000
# Loopback by default: the REST/WS API is unauthenticated and, since the
# controller proxies /swarmit/*, binding wider also republishes the swarmit
# server at the controller's reachability.
CONTROLLER_HTTP_HOST_DEFAULT = "127.0.0.1"
CONTROLLER_ADAPTER_DEFAULT = "serial"
MQTT_HOST_DEFAULT = "localhost"
MQTT_PORT_DEFAULT = 1883
MAP_SIZE_DEFAULT = "2000x2000"  # in mm unit
SIMULATOR_INIT_STATE_DEFAULT = "simulator_init_state.toml"
SWARMIT_URL_DEFAULT = "http://localhost:8001"  # swarmit server default port
MRTA_URL_DEFAULT = "http://localhost:8002"  # MRTA mode server (dotbot-logistics) default port


def addr_to_hex(addr: int) -> str:
    """Render a 64-bit device address as canonical hex.

    Uppercase is the canonical form across the DotBot stack: the swarm side
    (swarmit) renders addresses this way, and `DOTBOT_ADDRESS_DEFAULT` /
    `GATEWAY_ADDRESS_DEFAULT` are written this way. `binascii.hexlify` returns
    lowercase, so every address that becomes a string goes through here.
    """
    return hexlify(addr.to_bytes(8, "big")).decode().upper()


def pydotbot_version() -> str:
    """Returns the version of the pydotdot package."""
    try:
        return version("pydotbot")
    except PackageNotFoundError:
        return "unknown"
