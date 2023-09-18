"""Interface of the Dotbot controller."""

import asyncio
import json
import math
import time
import webbrowser

from abc import ABC, abstractmethod
from binascii import hexlify
from dataclasses import dataclass
from typing import Dict, List, Optional

import serial
import websockets

from fastapi import WebSocket

from haversine import haversine, Unit

from rich.live import Live
from rich.table import Table

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    ProtocolPayload,
    ProtocolHeader,
    PROTOCOL_VERSION,
    ProtocolPayloadParserException,
    PayloadType,
    ApplicationType,
    LH2Location,
)
from dotbot.serial_interface import SerialInterface, SerialInterfaceException

# from dotbot.models import (
#     DotBotModel,
#     DotBotGPSPosition,
#     DotBotLH2Position,
#     DotBotRgbLedCommandModel,
# )

from dotbot.models import (
    DotBotModel,
    DotBotQueryModel,
    DotBotStatus,
    DotBotLH2Position,
    DotBotGPSPosition,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    MAX_POSITION_HISTORY_SIZE,
)
from dotbot.server import web
from dotbot.lighthouse2 import LighthouseManager, LighthouseManagerState


CONTROLLERS = {}
LOST_DELAY = 5  # seconds
DEAD_DELAY = 60  # seconds
LH2_POSITION_DISTANCE_THRESHOLD = 0.01
GPS_POSITION_DISTANCE_THRESHOLD = 5  # meters


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


@dataclass
class ControllerSettings:
    """Data class that holds controller settings."""

    port: str
    baudrate: int
    dotbot_address: str
    gw_address: str
    swarm_id: str
    webbrowser: bool = False
    table: bool = False
    handshake: bool = False
    verbose: bool = False


def lh2_distance(last: DotBotLH2Position, new: DotBotLH2Position) -> float:
    """Helper function that computes the distance between 2 LH2 positions."""
    return math.sqrt(((new.x - last.x) ** 2) + ((new.y - last.y) ** 2))


def gps_distance(last: DotBotGPSPosition, new: DotBotGPSPosition) -> float:
    """Helper function that computes the distance between 2 GPS positions in m."""
    return haversine(
        (last.latitude, last.longitude), (new.latitude, new.longitude), unit=Unit.METERS
    )


class ControllerBase(ABC):
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, settings: ControllerSettings):
        self.dotbots: Dict[str, DotBotModel] = {}
        # self.dotbots: Dict[str, DotBotModel] = {
        #     "0000000000000001": DotBotModel(
        #         address="0000000000000001",
        #         last_seen=time.time(),
        #         lh2_position=DotBotLH2Position(x=0.5, y=0.5, z=0),
        #         rgb_led=DotBotRgbLedCommandModel(red=255, green=0, blue=0),
        #     ),
        #     "0000000000000002": DotBotModel(
        #         address="0000000000000002",
        #         last_seen=time.time(),
        #         lh2_position=DotBotLH2Position(x=0.2, y=0.2, z=0),
        #         rgb_led=DotBotRgbLedCommandModel(red=0, green=255, blue=0),
        #     ),
        #     "0000000000000003": DotBotModel(
        #         address="0000000000000003",
        #         last_seen=time.time(),
        #     ),
        #     "0000000000000004": DotBotModel(
        #         address="0000000000000004",
        #         application=ApplicationType.SailBot,
        #         last_seen=time.time(),
        #         gps_position=DotBotGPSPosition(latitude=48.832313766146896, longitude=2.4126897594949184),
        #     ),
        # }
        self.header = ProtocolHeader(
            destination=int(settings.dotbot_address, 16),
            source=int(settings.gw_address, 16),
            swarm_id=int(settings.swarm_id, 16),
            application=ApplicationType.DotBot,
            version=PROTOCOL_VERSION,
        )
        self.settings = settings
        self.hdlc_handler = HDLCHandler()
        self.serial = None
        self.websockets = []
        self.lh2_manager = LighthouseManager()
        self.logger = LOGGER.bind(context=__name__)

    @abstractmethod
    def init(self):
        """Abstract method to initialize a controller."""

    @abstractmethod
    async def start(self):
        """Abstract method to start a controller."""

    async def _start_serial(self):
        """Starts the serial listener thread in a coroutine."""
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def on_byte_received(byte):
            """Callback called on byte received."""
            event_loop.call_soon_threadsafe(queue.put_nowait, byte)

        async def _wait_for_handshake(queue):
            """Waits for handshake reply and checks it."""
            try:
                byte = await queue.get()
            except asyncio.exceptions.CancelledError as exc:
                raise SerialInterfaceException("Handshake timeout") from exc
            if int.from_bytes(byte, byteorder="little") != PROTOCOL_VERSION:
                raise SerialInterfaceException("Handshake failed")

        self.serial = SerialInterface(
            self.settings.port, self.settings.baudrate, on_byte_received
        )

        self.serial.write(
            int(PROTOCOL_VERSION).to_bytes(length=1, byteorder="little", signed=False)
        )
        if self.settings.handshake is True:
            await asyncio.wait_for(_wait_for_handshake(queue), timeout=0.2)
            self.logger.info("Serial handshake success")

        while 1:
            byte = await queue.get()
            self.handle_byte(byte)

    async def _open_webbrowser(self):
        """Wait until the server is ready before opening a web browser."""
        while 1:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", 8000)
            except ConnectionRefusedError:
                await asyncio.sleep(0.1)
            else:
                writer.close()
                break
        if self.settings.webbrowser is True:
            url = "http://localhost:8000/dotbots"
            self.logger.info("Opening webbrowser", url=url)
            webbrowser.open(url)

    async def _dotbots_status_refresh(self):
        """Coroutine that periodically updates the status of known dotbot."""
        while 1:
            needs_refresh = False
            for dotbot in self.dotbots.values():
                previous_status = dotbot.status
                if dotbot.last_seen + DEAD_DELAY < time.time():
                    dotbot.status = DotBotStatus.DEAD
                elif dotbot.last_seen + LOST_DELAY < time.time():
                    dotbot.status = DotBotStatus.LOST
                else:
                    dotbot.status = DotBotStatus.ALIVE
                logger = self.logger.bind(
                    source=dotbot.address,
                    application=dotbot.application.name,
                )
                needs_refresh = previous_status != dotbot.status
                if needs_refresh:
                    logger.info(
                        "Dotbot status changed",
                        previous_status=previous_status.name,
                        status=dotbot.status.name,
                    )
            if needs_refresh is True:
                await self.notify_clients(
                    DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD)
                )
            await asyncio.sleep(1)

    async def _dotbots_table_refresh(self):
        """Display and refresh a table of known dotbot."""

        def table():
            table = Table()
            if self.dotbots:
                table.add_column("#", style="cyan")
                table.add_column("address", style="magenta")
                table.add_column("application", style="yellow")
                table.add_column("status", style="green")
                table.add_column("mode", style="green")
                table.add_column("active", style="green")
                for idx, dotbot in enumerate(self.dotbots.values()):
                    table.add_row(
                        f"{idx:<4}",
                        f"0x{dotbot.address}",
                        f"{dotbot.application.name}",
                        f"{dotbot.status.name.capitalize()}",
                        f"{dotbot.mode.name.capitalize()}",
                        f"{int(dotbot.address, 16) == self.header.destination}",
                    )
            return table

        with Live(table(), refresh_per_second=10) as live:
            while 1:
                live.update(table())
                await asyncio.sleep(1)

    def _compute_lh2_position(
        self, payload: ProtocolPayload
    ) -> Optional[DotBotLH2Position]:
        if payload.payload_type not in (
            PayloadType.LH2_RAW_DATA,
            PayloadType.DOTBOT_DATA,
        ):
            return None
        self.lh2_manager.last_raw_data = payload.values
        if self.lh2_manager.state != LighthouseManagerState.Calibrated:
            return None
        return self.lh2_manager.compute_position(payload.values)

    def handle_byte(self, byte):
        """Called on each byte received over UART."""
        self.hdlc_handler.handle_byte(byte)
        if self.hdlc_handler.state == HDLCState.READY:
            payload = self.hdlc_handler.payload
            if payload:
                try:
                    payload = ProtocolPayload.from_bytes(payload)
                except ProtocolPayloadParserException:
                    self.logger.warning("Cannot parse payload")
                    if self.settings.verbose is True:
                        print(payload)
                    return
                self.handle_received_payload(payload)

    def handle_received_payload(
        self, payload: ProtocolPayload
    ):  # pylint:disable=too-many-branches,too-many-statements
        """Handle a received payload."""
        # Controller is not interested by command messages received
        if payload.payload_type in [
            PayloadType.CMD_MOVE_RAW,
            PayloadType.CMD_RGB_LED,
        ]:
            return
        source = hexlify(int(payload.header.source).to_bytes(8, "big")).decode()
        logger = self.logger.bind(
            source=source,
            payload_type=payload.payload_type.name,
            application=payload.header.application.name,
            msg_id=payload.header.msg_id,
        )
        if source == GATEWAY_ADDRESS_DEFAULT:
            logger.warning("Invalid source in payload")
            return
        dotbot = DotBotModel(
            address=source,
            application=payload.header.application,
            last_seen=time.time(),
            active=(int(source, 16) == self.header.destination),
        )
        notification_cmd = DotBotNotificationCommand.NONE
        if source in self.dotbots:
            dotbot.mode = self.dotbots[source].mode
            dotbot.status = self.dotbots[source].status
            dotbot.direction = self.dotbots[source].direction
            dotbot.rgb_led = self.dotbots[source].rgb_led
            dotbot.lh2_position = self.dotbots[source].lh2_position
            dotbot.gps_position = self.dotbots[source].gps_position
            dotbot.waypoints = self.dotbots[source].waypoints
            dotbot.waypoints_threshold = self.dotbots[source].waypoints_threshold
            dotbot.position_history = self.dotbots[source].position_history
        else:
            # reload if a new dotbot comes in
            logger.info("New dotbot")
            notification_cmd = DotBotNotificationCommand.RELOAD

        if (
            payload.payload_type in [PayloadType.DOTBOT_DATA, PayloadType.SAILBOT_DATA]
            and -500 <= payload.values.direction <= 500
        ):
            dotbot.direction = payload.values.direction
            logger = logger.bind(direction=dotbot.direction)

        dotbot.lh2_position = self._compute_lh2_position(payload)
        if (
            dotbot.lh2_position is not None
            and 0 <= dotbot.lh2_position.x <= 1
            and 0 <= dotbot.lh2_position.y <= 1
        ):
            new_position = DotBotLH2Position(
                x=dotbot.lh2_position.x,
                y=dotbot.lh2_position.y,
                z=dotbot.lh2_position.z,
            )
            logger.info("lh2", x=dotbot.lh2_position.x, y=dotbot.lh2_position.y)
            if (
                not dotbot.position_history
                or lh2_distance(dotbot.position_history[-1], new_position)
                >= LH2_POSITION_DISTANCE_THRESHOLD
            ):
                dotbot.position_history.append(new_position)
                notification_cmd = DotBotNotificationCommand.UPDATE
            if len(dotbot.position_history) > MAX_POSITION_HISTORY_SIZE:
                dotbot.position_history.pop(0)
            # Send the computed position back to the dotbot
            header = ProtocolHeader(
                destination=int(source, 16),
                source=int(self.settings.gw_address, 16),
                swarm_id=int(self.settings.swarm_id, 16),
                application=dotbot.application,
                version=PROTOCOL_VERSION,
            )
            self.send_payload(
                ProtocolPayload(
                    header,
                    PayloadType.LH2_LOCATION,
                    LH2Location(
                        int(dotbot.lh2_position.x * 1e6),
                        int(dotbot.lh2_position.y * 1e6),
                        int(dotbot.lh2_position.z * 1e6),
                    ),
                )
            )
        elif payload.payload_type == PayloadType.DOTBOT_DATA:
            logger.warning("lh2: invalid position")

        if payload.payload_type in [PayloadType.GPS_POSITION, PayloadType.SAILBOT_DATA]:
            new_position = DotBotGPSPosition(
                latitude=float(payload.values.latitude) / 1e6,
                longitude=float(payload.values.longitude) / 1e6,
            )
            dotbot.gps_position = new_position
            logger.info("gps", lat=new_position.latitude, long=new_position.longitude)
            if (
                not dotbot.position_history
                or gps_distance(dotbot.position_history[-1], new_position)
                >= GPS_POSITION_DISTANCE_THRESHOLD
            ):
                dotbot.position_history.append(new_position)
            if len(dotbot.position_history) > MAX_POSITION_HISTORY_SIZE:
                dotbot.position_history.pop(0)
            notification_cmd = DotBotNotificationCommand.UPDATE

        if notification_cmd == DotBotNotificationCommand.UPDATE:
            notification = DotBotNotificationModel(
                cmd=notification_cmd.value,
                data=DotBotNotificationUpdate(
                    address=dotbot.address,
                    direction=dotbot.direction,
                    lh2_position=dotbot.lh2_position,
                    gps_position=dotbot.gps_position,
                ),
            )
        else:
            notification = DotBotNotificationModel(cmd=notification_cmd.value)

        if self.settings.verbose is True:
            print(payload)
        self.dotbots.update({dotbot.address: dotbot})
        if notification_cmd != DotBotNotificationCommand.NONE:
            asyncio.create_task(self.notify_clients(notification))

    async def _ws_send_safe(self, websocket: WebSocket, msg: str):
        """Safely send a message to a websocket client."""
        try:
            await websocket.send_text(msg)
        except websockets.exceptions.ConnectionClosedError:
            await asyncio.sleep(0.1)

    async def notify_clients(self, notification):
        """Send a message to all clients connected."""
        self.logger.debug("notify", cmd=notification.cmd.name)
        await asyncio.gather(
            *[
                self._ws_send_safe(
                    websocket, json.dumps(notification.dict(exclude_none=True))
                )
                for websocket in self.websockets
            ]
        )

    def send_payload(self, payload: ProtocolPayload):
        """Sends a command in an HDLC frame over serial."""
        destination = hexlify(
            int(payload.header.destination).to_bytes(8, "big")
        ).decode()
        if destination not in self.dotbots:
            return
        # make sure the application in the payload matches the bot application
        payload.header.application = self.dotbots[destination].application
        if self.serial is not None:
            self.serial.write(hdlc_encode(payload.to_bytes()))
            self.logger.debug(
                "Payload sent",
                application=payload.header.application.name,
                destination=destination,
                payload_type=payload.payload_type.name,
            )

    def get_dotbots(self, query: DotBotQueryModel) -> List[DotBotModel]:
        """Returns the list of dotbots matching the query."""
        dotbots: List[DotBotModel] = []
        for dotbot in self.dotbots.values():
            if (
                query.application is not None
                and dotbot.application != query.application
            ):
                continue
            if query.mode is not None and dotbot.mode != query.mode:
                continue
            if query.status is not None and dotbot.status != query.status:
                continue
            _dotbot = DotBotModel(**dotbot.dict())
            _dotbot.position_history = _dotbot.position_history[: query.max_positions]
            dotbots.append(_dotbot)
        return sorted(dotbots, key=lambda dotbot: dotbot.address)

    async def run(self):
        """Launch the controller."""
        tasks = []
        try:
            self.init()
            tasks = [
                asyncio.create_task(web(self)),
                asyncio.create_task(self._open_webbrowser()),
                asyncio.create_task(self._start_serial()),
                asyncio.create_task(self._dotbots_status_refresh()),
                asyncio.create_task(self.start()),
            ]
            if self.settings.table is True:
                tasks.append(asyncio.create_task(self._dotbots_table_refresh()))
            await asyncio.gather(*tasks)
        except (
            SerialInterfaceException,
            serial.serialutil.SerialException,
        ) as exc:
            self.logger.error(f"Error: {exc}")
        except SystemExit:
            self.logger.info("Stopping controller")
        finally:
            for task in tasks:
                task.cancel()


def register_controller(type_, cls):
    """Register a new controller."""
    CONTROLLERS.update({type_: cls})


def controller_factory(type_, settings: ControllerSettings):
    """Returns an instance of a concrete Dotbot controller."""
    if type_ not in CONTROLLERS:
        raise ControllerException("Invalid controller")
    return CONTROLLERS[type_](settings)
