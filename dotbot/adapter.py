"""Module containing classes for interfacing with the DotBot gateway."""

import asyncio
from abc import ABC, abstractmethod

from dotbot.dotbot_simulator import DotBotSimulatorSerialInterface
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.protocol import (
    Frame,
    Header,
    Packet,
    Payload,
    ProtocolPayloadParserException,
)
from dotbot.sailbot_simulator import SailBotSimulatorSerialInterface
from dotbot.serial_interface import SerialInterface


class GatewayAdapterBase(ABC):
    """Base class for interface adapters."""

    @abstractmethod
    async def start(self, on_frame_received: callable):
        """Initialize the interface."""

    @abstractmethod
    def close(self):
        """Close the interface."""

    @abstractmethod
    def send_payload(self, destination: int, payload: Payload):
        """Send payload to the interface."""


class SerialAdapter(GatewayAdapterBase):
    """Class used to interface with the serial port."""

    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.hdlc_handler = HDLCHandler()

    def on_byte_received(self, byte: bytes):
        self.hdlc_handler.handle_byte(byte)
        if self.hdlc_handler.state == HDLCState.READY:
            try:
                data = self.hdlc_handler.payload
                try:
                    frame = Frame.from_bytes(data)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    print(f"[red]Error parsing frame: {exc}[/]")
                    return
            except Exception as _:
                return
            self.on_frame_received(frame)

    async def start(self, on_frame_received: callable):
        self.on_frame_received = on_frame_received
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def _byte_received(byte):
            """Callback called on byte received."""
            event_loop.call_soon_threadsafe(queue.put_nowait, byte)

        if self.port == "sailbot-simulator":
            self.serial = SailBotSimulatorSerialInterface(_byte_received)
        elif self.port == "dotbot-simulator":
            self.serial = DotBotSimulatorSerialInterface(_byte_received)
        else:
            self.serial = SerialInterface(self.port, self.baudrate, _byte_received)
            await asyncio.sleep(1)

        while 1:
            byte = await queue.get()
            self.on_byte_received(byte)
        print("[yellow]Connected to gateway over serial[/]")

    def close(self):
        print("[yellow]Disconnect from gateway...[/]")
        self.serial.stop()

    def send_payload(self, destination: int, payload: Payload):
        frame = Frame(
            header=Header(destination=destination),
            packet=Packet.from_payload(payload),
        )
        self.serial.write(hdlc_encode(frame.to_bytes()))
        self.serial.serial.flush()
