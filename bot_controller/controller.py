"""Interface of the Dotbot controller."""

from abc import ABC, abstractmethod

from bot_controller.hdlc import HDLCHandler, HDLCState, hdlc_encode
from bot_controller.protocol import (
    ProtocolPayload,
    ProtocolHeader,
    PROTOCOL_VERSION,
    ProtocolPayloadParserException,
)
from bot_controller.serial_interface import SerialInterface

CONTROLLERS = {}


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, port, baudrate, dotbot_address, gw_address, swarm_id):
        # pylint: disable=too-many-arguments
        self.header = ProtocolHeader(
            dotbot_address,
            gw_address,
            swarm_id,
            PROTOCOL_VERSION,
        )
        self.init()
        self.hdlc_handler = HDLCHandler()
        self.serial = SerialInterface(port, baudrate, self.on_byte_received)

    @abstractmethod
    def init(self):
        """Abstract method to initialize a controller."""

    @abstractmethod
    def start(self):
        """Abstract method to start a controller."""

    def on_byte_received(self, byte):
        """Called on each byte received over UART."""
        self.hdlc_handler.handle_byte(byte)
        if self.hdlc_handler.state == HDLCState.READY:
            payload = self.hdlc_handler.payload
            if payload:
                try:
                    print(ProtocolPayload.from_bytes(payload))
                except ProtocolPayloadParserException:
                    pass

    def send_payload(self, payload: ProtocolPayload):
        """Sends a command in an HDLC frame over serial."""
        self.serial.write(hdlc_encode(payload.to_bytes()))


def register_controller(type_, cls):
    """Register a new controller."""
    CONTROLLERS.update({type_: cls})


def controller_factory(type_, port, baudrate, dotbot_address, gw_address, swarm_id):
    # pylint: disable=too-many-arguments
    """Returns an instance of a concrete Dotbot controller."""
    if type_ not in CONTROLLERS:
        raise ControllerException("Invalid controller")
    return CONTROLLERS[type_](port, baudrate, dotbot_address, gw_address, swarm_id)
