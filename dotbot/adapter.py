"""Module containing classes for interfacing with the DotBot gateway."""

import asyncio
from abc import ABC, abstractmethod

from marilib.communication_adapter import MQTTAdapter as MarilibMQTTAdapter
from marilib.communication_adapter import SerialAdapter as MarilibSerialAdapter
from marilib.mari_protocol import Frame as MariFrame
from marilib.marilib_cloud import MarilibCloud
from marilib.marilib_edge import MarilibEdge
from marilib.model import EdgeEvent, MariNode

from dotbot.dotbot_simulator import DotBotSimulatorSerialInterface
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.logger import LOGGER
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
                #print(data, len(data))
                try:
                    frame = Frame.from_bytes(data)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    LOGGER.error(f"Error parsing frame: {exc}")
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

        LOGGER.info("Connected to gateway over serial")
        while 1:
            byte = await queue.get()
            self.on_byte_received(byte)

    def close(self):
        LOGGER.info("Disconnect from gateway...")
        self.serial.stop()

    def send_payload(self, destination: int, payload: Payload):
        frame = Frame(
            header=Header(destination=destination),
            packet=Packet.from_payload(payload),
        )
        self.serial.write(hdlc_encode(frame.to_bytes()))
        self.serial.serial.flush()


class MarilibEdgeAdapter(GatewayAdapterBase):
    """Class used to interface with Marilib."""

    def __init__(self, port: str, baudrate: int, verbose: bool = False):
        self.port = port
        self.baudrate = baudrate

    async def start(self, on_frame_received: callable):
        self.on_frame_received = on_frame_received
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def _on_mari_event(event: EdgeEvent, event_data: MariNode | MariFrame):
            if event == EdgeEvent.NODE_JOINED:
                LOGGER.debug("Node joined", event_data)
            elif event == EdgeEvent.NODE_LEFT:
                LOGGER.debug("Node left", event_data)
            elif event == EdgeEvent.NODE_DATA:
                try:
                    packet = Packet.from_bytes(event_data.payload)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    LOGGER.error(f"Error parsing packet: {exc}")
                    return
                if not hasattr(self, "on_frame_received"):
                    return
                event_loop.call_soon_threadsafe(
                    queue.put_nowait, Frame(header=event_data.header, packet=packet)
                )

        self.mari = MarilibEdge(
            _on_mari_event, MarilibSerialAdapter(self.port, self.baudrate)
        )
        await asyncio.sleep(3)

        LOGGER.info("Connected to mari edge")
        while 1:
            frame = await queue.get()
            self.on_frame_received(frame)

    def close(self):
        self.mari.close()

    def send_payload(self, destination: int, payload: Payload):
        self.mari.send_frame(
            dst=destination,
            payload=Packet.from_payload(payload).to_bytes(),
        )


class MarilibCloudAdapter(GatewayAdapterBase):
    """Class used to interface with Marilib."""

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool,
        network_id: int,
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.network_id = network_id

    async def start(self, on_frame_received: callable):
        self.on_frame_received = on_frame_received
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def _on_mari_event(event: EdgeEvent, event_data: MariNode | MariFrame):
            if event == EdgeEvent.NODE_JOINED:
                LOGGER.debug("Node joined:", event_data)
            elif event == EdgeEvent.NODE_LEFT:
                LOGGER.debug("Node left:", event_data)
            elif event == EdgeEvent.NODE_DATA:
                try:
                    packet = Packet.from_bytes(event_data.payload)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    LOGGER.error(f"Error parsing packet: {exc}")
                    return
                if not hasattr(self, "on_frame_received"):
                    return
                event_loop.call_soon_threadsafe(
                    queue.put_nowait, Frame(header=event_data.header, packet=packet)
                )

        self.mari = MarilibCloud(
            _on_mari_event,
            MarilibMQTTAdapter(
                self.host, self.port, use_tls=self.use_tls, is_edge=False
            ),
            self.network_id,
        )
        await asyncio.sleep(3)

        while 1:
            frame = await queue.get()
            self.on_frame_received(frame)
        LOGGER.info("Connected to mari edge")

    def close(self):
        pass

    def send_payload(self, destination: int, payload: Payload):
        self.mari.send_frame(
            dst=destination,
            payload=Packet.from_payload(payload).to_bytes(),
        )
