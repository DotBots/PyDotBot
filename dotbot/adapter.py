"""Module containing classes for interfacing with the DotBot gateway."""

import asyncio
from abc import ABC, abstractmethod

from dotbot_utils.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot_utils.protocol import (
    Frame,
    Header,
    Packet,
    Payload,
    ProtocolPayloadParserException,
)
from dotbot_utils.serial_interface import SerialInterface
from marilib.communication_adapter import MQTTAdapter as MarilibMQTTAdapter
from marilib.communication_adapter import SerialAdapter as MarilibSerialAdapter
from marilib.mari_protocol import Frame as MariFrame
from marilib.mari_protocol import NextProto
from marilib.marilib_cloud import MarilibCloud
from marilib.marilib_edge import MarilibEdge
from marilib.model import EdgeEvent, MariNode

from dotbot import SIMULATOR_INIT_STATE_DEFAULT
from dotbot.dotbot_simulator import DotBotSimulatorCommunicationInterface
from dotbot.logger import LOGGER
from dotbot.sailbot_simulator import SailBotSimulatorCommunicationInterface


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
    """Raw (non-Mari) serial gateway interface.

    Deprecated: the `--conn` CLI no longer selects this — a device-path
    connection maps to the Mari `edge` adapter, since bare DotBot apps now
    emit Mari-shaped frames and the gateway speaks Mari-shaped UART
    packets (so the edge adapter handles both sandbox and bare). Kept for
    now as no CLI path constructs it; likely removed in a future cleanup.
    """

    def __init__(
        self,
        port: str,
        baudrate: int,
    ):
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
                    LOGGER.debug(f"Error parsing frame: {exc}")
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
        self.serial.flush()


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
                LOGGER.debug(f"Node joined: {event_data.address:016x}")
            elif event == EdgeEvent.NODE_LEFT:
                LOGGER.debug(f"Node left: {event_data.address:016x}")
            elif event == EdgeEvent.NODE_DATA:
                if event_data.header.next_proto != NextProto.DOTBOT_APP:
                    return
                try:
                    packet = Packet.from_bytes(event_data.payload)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    LOGGER.debug(f"Error parsing packet: {exc}")
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
            next_proto=NextProto.DOTBOT_APP,
        )


class MarilibCloudAdapter(GatewayAdapterBase):
    """Class used to interface with Marilib."""

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool,
        network_id: int,
        username: str | None = None,
        password: str | None = None,
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.network_id = network_id
        self.username = username
        self.password = password

    async def start(self, on_frame_received: callable):
        self.on_frame_received = on_frame_received
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def _on_mari_event(event: EdgeEvent, event_data: MariNode | MariFrame):
            if event == EdgeEvent.NODE_JOINED:
                LOGGER.debug(f"Node joined: {event_data.address:016x}")
            elif event == EdgeEvent.NODE_LEFT:
                LOGGER.debug(f"Node left: {event_data.address:016x}")
            elif event == EdgeEvent.NODE_DATA:
                if event_data.header.next_proto != NextProto.DOTBOT_APP:
                    return
                try:
                    packet = Packet.from_bytes(event_data.payload)
                except (ValueError, ProtocolPayloadParserException) as exc:
                    LOGGER.debug(f"Error parsing packet: {exc}")
                    return
                if not hasattr(self, "on_frame_received"):
                    return
                event_loop.call_soon_threadsafe(
                    queue.put_nowait, Frame(header=event_data.header, packet=packet)
                )

        # Broker credentials (from DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS,
        # threaded down by controller_app) are passed only when set.
        # NOTE: requires the marilib companion that adds username/password
        # to MarilibMQTTAdapter; until that lands, set credentials are a
        # no-op (anonymous connect), which matches today's behaviour.
        mqtt_kwargs = {}
        if self.username is not None:
            mqtt_kwargs["username"] = self.username
        if self.password is not None:
            mqtt_kwargs["password"] = self.password
        self.mari = MarilibCloud(
            _on_mari_event,
            MarilibMQTTAdapter(
                self.host,
                self.port,
                use_tls=self.use_tls,
                is_edge=False,
                **mqtt_kwargs,
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
            next_proto=NextProto.DOTBOT_APP,
        )


class SimulatorAdapterBase(GatewayAdapterBase):
    """Base class used to interface with the simulator."""

    # Assigned in start(); stays None if start() failed before the
    # simulator was constructed, so close() can no-op instead of raising.
    simulator = None

    @abstractmethod
    def create_simulator(self, _byte_received: callable):
        """Create the simulator instance."""

    async def start(self, on_frame_received: callable):
        self.on_frame_received = on_frame_received
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def _frame_received(frame):
            """Callback called on byte received."""
            event_loop.call_soon_threadsafe(queue.put_nowait, frame)

        self.simulator = self.create_simulator(_frame_received)
        self.simulator.start()

        LOGGER.info("Connected to simulator")
        while 1:
            frame = await queue.get()
            self.on_frame_received(frame)

    def close(self):
        if self.simulator is None:
            return
        LOGGER.info("Disconnect from simulator...")
        self.simulator.stop()

    def send_payload(self, destination: int, payload: Payload):
        frame = Frame(
            header=Header(destination=destination),
            packet=Packet.from_payload(payload),
        )
        self.simulator.write(frame.to_bytes())


class DotBotSimulatorAdapter(SimulatorAdapterBase):
    """Class used to interface with the dotbot simulator."""

    def __init__(
        self,
        simulator_init_state: str = SIMULATOR_INIT_STATE_DEFAULT,
    ):
        self.simulator_init_state = simulator_init_state

    def create_simulator(self, on_frame_received: callable):
        return DotBotSimulatorCommunicationInterface(
            on_frame_received, self.simulator_init_state
        )


class SailBotSimulatorAdapter(SimulatorAdapterBase):
    """Class used to interface with the sailbot simulator."""

    def create_simulator(self, on_frame_received: callable):
        return SailBotSimulatorCommunicationInterface(on_frame_received)
