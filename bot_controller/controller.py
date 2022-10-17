"""Interface of the Dotbot controller."""

import asyncio
import sys
import time

from abc import ABC, abstractmethod
from binascii import hexlify
from dataclasses import dataclass

import serial

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
        self.settings = settings
        self.hdlc_handler = HDLCHandler()
        self.serial = None

    @abstractmethod
    def init(self):
        """Abstract method to initialize a controller."""

    @abstractmethod
    async def start(self):
        """Abstract method to start a controller."""

    def _setup(self):
        """Setup the controller."""
        self.init()
        asyncio.create_task(self._start_serial())
        asyncio.create_task(self.update_known_dotbots())
        asyncio.create_task(self.known_dotbots_table())

    async def _start_serial(self):
        """Starts the serial listener thread in a coroutine."""
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def on_byte_received(byte):
            """Callback called on byte received."""
            event_loop.call_soon_threadsafe(queue.put_nowait, byte)

        try:
            self.serial = SerialInterface(
                self.settings.port, self.settings.baudrate, on_byte_received
            )
        except serial.serialutil.SerialException as exc:
            sys.exit(f"{exc}")

        while 1:
            byte = await queue.get()
            self.handle_byte(byte)

    def handle_byte(self, byte):
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
                if self.settings.verbose:
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
        if self.serial is not None:
            self.serial.write(hdlc_encode(payload.to_bytes()))

    async def update_known_dotbots(self):
        """Coroutine that periodically updates the list of known dotbots."""
        while 1:
            to_remove = []
            for dotbot, last_seen in self.known_dotbots.items():
                if last_seen + 3 < time.time():
                    to_remove.append(dotbot)
            for dotbot in to_remove:
                self.known_dotbots.pop(dotbot)
            await asyncio.sleep(1)

    async def run(self):
        """Launch the controller."""
        self._setup()  # Must be called from a coroutine because if needs a loop
        await self.start()

    async def known_dotbots_table(self):
        """Display and refresh a table of known dotbots."""

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
                await asyncio.sleep(1)


def register_controller(type_, cls):
    """Register a new controller."""
    CONTROLLERS.update({type_: cls})


def controller_factory(type_, settings: ControllerSettings):
    """Returns an instance of a concrete Dotbot controller."""
    if type_ not in CONTROLLERS:
        raise ControllerException("Invalid controller")
    return CONTROLLERS[type_](settings)
