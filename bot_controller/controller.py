"""Interface of the Dotbot controller."""

import time

from abc import ABC, abstractmethod
from binascii import hexlify
from dataclasses import dataclass
from threading import Thread

from rich.live import Live
from rich.table import Table

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


class ControllerDeadDotBotCleaner(Thread):
    """Threads that cleans DotBot from known ones if inactive."""

    def __init__(self, controller):
        self.controller: ControllerBase = controller
        super().__init__()
        self.daemon = True

    def run(self):
        """Periodically looks for dead DotBot."""
        while 1:
            to_remove = []
            for dotbot, last_seen in self.controller.known_dotbots.items():
                if last_seen + 2 < time.time():
                    to_remove.append(dotbot)
            for dotbot in to_remove:
                self.controller.known_dotbots.pop(dotbot)
            time.sleep(1)


@dataclass
class ControllerSettings:
    """Data class that holds controller settings."""

    port: str
    baudrate: int
    dotbot_address: int
    gw_address: int
    swarm_id: int
    verbose: bool = False


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, settings: ControllerSettings):
        self.known_dotbots = {}
        self.header = ProtocolHeader(
            settings.dotbot_address,
            settings.gw_address,
            settings.swarm_id,
            PROTOCOL_VERSION,
        )
        self.verbose = settings.verbose
        self.init()
        self.hdlc_handler = HDLCHandler()
        self.serial = SerialInterface(
            settings.port, settings.baudrate, self.on_byte_received
        )
        self.cleaner = ControllerDeadDotBotCleaner(self)
        self.cleaner.start()

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
                if self.verbose:
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

    def scan(self):
        """Maintain a table of known dotbots."""

        def table():
            table = Table()
            if self.known_dotbots:
                table.add_column("id", justify="right", style="cyan", no_wrap=True)
                table.add_column("address", style="magenta")
                table.add_column("last seen", justify="right", style="green")
                for idx, values in enumerate(self.known_dotbots.items()):
                    table.add_row(f"{idx:>5}", f"0x{values[0]}", f"{values[1]:.3f}")
            return table

        with Live(table(), refresh_per_second=10) as live:
            while 1:
                live.update(table())
                time.sleep(1)


def register_controller(type_, cls):
    """Register a new controller."""
    CONTROLLERS.update({type_: cls})


def controller_factory(type_, settings: ControllerSettings):
    """Returns an instance of a concrete Dotbot controller."""
    if type_ not in CONTROLLERS:
        raise ControllerException("Invalid controller")
    return CONTROLLERS[type_](settings)
