"""Interface of the Dotbot controller."""

import time

from abc import ABC, abstractmethod
from binascii import hexlify

from bot_controller.hdlc import HDLCHandler, HDLCState, hdlc_encode
from bot_controller.protocol import (
    ProtocolPayload,
    ProtocolHeader,
    PROTOCOL_VERSION,
    ProtocolPayloadParserException,
    PayloadType,
)
from bot_controller.serial_interface import SerialInterface

CONTROLLERS = {}


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, port, baudrate, dotbot_address, gw_address, swarm_id):
        # pylint: disable=too-many-arguments
        self.known_dotbots = {}
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
                    protocol = ProtocolPayload.from_bytes(payload)
                except ProtocolPayloadParserException:
                    print(f"Cannot parse payload '{payload}'")
                    return
                # Controller is not interested by command messages received
                if protocol.payload_type in [
                    PayloadType.CMD_MOVE_RAW,
                    PayloadType.CMD_RGB_LED,
                ]:
                    return
                print(protocol)
                source = hexlify(
                    int(protocol.header.source).to_bytes(8, "big")
                ).decode()
                self.known_dotbots.update({source: time.time()})

    def send_payload(self, payload: ProtocolPayload):
        """Sends a command in an HDLC frame over serial."""
        destination = hexlify(
            int(payload.header.destination).to_bytes(8, "big")
        ).decode()
        if destination not in self.known_dotbots:
            return
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
