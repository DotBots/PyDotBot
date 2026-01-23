"""Pydotbot module."""

from importlib.metadata import PackageNotFoundError, version

from dotbot_utils.serial_interface import get_default_port

SERIAL_PORT_DEFAULT = get_default_port()
SERIAL_BAUDRATE_DEFAULT = 1000000
DOTBOT_ADDRESS_DEFAULT = "FFFFFFFFFFFFFFFF"  # Broadcast by default
GATEWAY_ADDRESS_DEFAULT = "0000000000000000"
NETWORK_ID_DEFAULT = "0000"
CONTROLLER_HTTP_PROTOCOL_DEFAULT = "http"
CONTROLLER_HTTP_HOSTNAME_DEFAULT = "localhost"
CONTROLLER_HTTP_PORT_DEFAULT = "8000"
CONTROLLER_ADAPTER_DEFAULT = "serial"
MQTT_HOST_DEFAULT = "localhost"
MQTT_PORT_DEFAULT = 1883
MAP_SIZE_DEFAULT = "2000x2000"  # in mm unit
SIMULATOR_INIT_STATE_PATH_DEFAULT = "simulator_init_state.toml"


def pydotbot_version() -> str:
    """Returns the version of the pydotdot package."""
    try:
        return version("pydotbot")
    except PackageNotFoundError:
        return "unknown"
