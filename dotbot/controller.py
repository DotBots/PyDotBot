"""Interface of the Dotbot controller."""

import asyncio
import json
import math
import time
import webbrowser
from binascii import hexlify
from dataclasses import dataclass
from typing import Dict, List, Optional

import serial
import uvicorn
import websockets
from fastapi import WebSocket
from haversine import Unit, haversine
from pydantic import ValidationError
from pydantic.tools import parse_obj_as
from qrkey import QrkeyController, SubscriptionModel

from dotbot import (
    CONTROLLER_PORT_DEFAULT,
    DOTBOT_ADDRESS_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
)
from dotbot.dotbot_simulator import DotBotSimulatorSerialInterface
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.lighthouse2 import LighthouseManager, LighthouseManagerState
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotCalibrationIndexModel,
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotQueryModel,
    DotBotReplyModel,
    DotBotRequestModel,
    DotBotRequestType,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
    DotBotXGOActionCommandModel,
)
from dotbot.protocol import (
    PROTOCOL_VERSION,
    ApplicationType,
    CommandMoveRaw,
    CommandRgbLed,
    CommandXgoAction,
    GPSPosition,
    GPSWaypoints,
    LH2Location,
    LH2Waypoints,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
    ProtocolPayloadParserException,
)
from dotbot.sailbot_simulator import SailBotSimulatorSerialInterface
from dotbot.serial_interface import SerialInterface, SerialInterfaceException
from dotbot.server import api

# from dotbot.models import (
#     DotBotModel,
#     DotBotGPSPosition,
#     DotBotLH2Position,
#     DotBotRgbLedCommandModel,
# )


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
    controller_port: int = CONTROLLER_PORT_DEFAULT
    webbrowser: bool = False
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


class Controller:
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
        #         wind_angle=135,
        #         rotation=49,
        #         gps_position=DotBotGPSPosition(latitude=48.832313766146896, longitude=2.4126897594949184),
        #     ),
        # }
        self.logger = LOGGER.bind(context=__name__)
        self.header = ProtocolHeader(
            destination=int(DOTBOT_ADDRESS_DEFAULT, 16),
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
        self.api = api
        api.controller = self
        self.qrkey = QrkeyController(self.on_request, LOGGER, root_topic="/pydotbot")
        self.subscriptions = [
            SubscriptionModel(
                topic="/command/+/+/+/move_raw", callback=self.on_command_move_raw
            ),
            SubscriptionModel(
                topic="/command/+/+/+/rgb_led", callback=self.on_command_rgb_led
            ),
            SubscriptionModel(
                topic="/command/+/+/+/xgo_action", callback=self.on_command_xgo_action
            ),
            SubscriptionModel(
                topic="/command/+/+/+/waypoints", callback=self.on_command_waypoints
            ),
            SubscriptionModel(
                topic="/command/+/+/+/clear_position_history",
                callback=self.on_command_clear_position_history,
            ),
            SubscriptionModel(topic="/lh2/add", callback=self.on_lh2_add),
            SubscriptionModel(topic="/lh2/start", callback=self.on_lh2_start),
        ]

    def on_command_move_raw(self, topic, payload):
        """Called when a move raw command is received."""
        logger = self.logger.bind(command="move_raw", topic=topic)
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "move_raw":
            logger.warning("Invalid move_raw command topic")
            return
        swarm_id, address, application, _ = topic_split
        try:
            command = DotBotMoveRawCommandModel(**payload)
        except ValidationError as exc:
            self.logger.warning(f"Invalid move raw command: {exc.errors()}")
            return
        logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            **command.model_dump(),
        )
        if address not in self.dotbots:
            logger.warning("DotBot not found")
            return
        logger.info("Sending command")
        header = ProtocolHeader(
            destination=int(address, 16),
            source=int(self.settings.gw_address, 16),
            swarm_id=int(swarm_id, 16),
            application=ApplicationType(int(application)),
            version=PROTOCOL_VERSION,
        )
        payload = ProtocolPayload(
            header,
            PayloadType.CMD_MOVE_RAW,
            CommandMoveRaw(
                left_x=command.left_x,
                left_y=command.left_y,
                right_x=command.right_x,
                right_y=command.right_y,
            ),
        )
        self.send_payload(payload)
        self.dotbots[address].move_raw = command

    def on_command_rgb_led(self, topic, payload):
        """Called when an rgb led command is received."""
        logger = self.logger.bind(command="rgb_led", topic=topic)
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "rgb_led":
            logger.warning("Invalid rgb_led command topic")
            return
        swarm_id, address, application, _ = topic_split
        try:
            command = DotBotRgbLedCommandModel(**payload)
        except ValidationError as exc:
            LOGGER.warning(f"Invalid rgb led command: {exc.errors()}")
            return
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            **command.model_dump(),
        )
        if address not in self.dotbots:
            logger.warning("DotBot not found")
            return
        logger.info("Sending command")
        header = ProtocolHeader(
            destination=int(address, 16),
            source=int(self.settings.gw_address, 16),
            swarm_id=int(swarm_id, 16),
            application=ApplicationType(int(application)),
            version=PROTOCOL_VERSION,
        )
        payload = ProtocolPayload(
            header,
            PayloadType.CMD_RGB_LED,
            CommandRgbLed(command.red, command.green, command.blue),
        )
        self.send_payload(payload)
        self.dotbots[address].rgb_led = command

    def on_command_xgo_action(self, topic, payload):
        """Called when an rgb led command is received."""
        logger = self.logger.bind(command="xgo_action", topic=topic)
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "xgo_action":
            logger.warning("Invalid xgo_action command topic")
            return
        swarm_id, address, application, _ = topic_split
        try:
            command = DotBotXGOActionCommandModel(**payload)
        except ValidationError as exc:
            LOGGER.warning(f"Invalid rgb led command: {exc.errors()}")
            return
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            **command.model_dump(),
        )
        if address not in self.dotbots:
            logger.warning("DotBot not found")
            return
        logger.info("Sending command")
        header = ProtocolHeader(
            destination=int(address, 16),
            source=int(self.settings.gw_address, 16),
            swarm_id=int(swarm_id, 16),
            application=ApplicationType(int(application)),
            version=PROTOCOL_VERSION,
        )
        payload = ProtocolPayload(
            header,
            PayloadType.CMD_XGO_ACTION,
            CommandXgoAction(command.action),
        )
        self.send_payload(payload)

    def on_command_waypoints(self, topic, payload):
        """Called when a list of waypoints is received."""
        logger = self.logger.bind(command="waypoints", topic=topic)
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "waypoints":
            logger.warning("Invalid waypoints command topic")
            return
        swarm_id, address, application, _ = topic_split
        command = parse_obj_as(DotBotWaypoints, payload)
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            threshold=command.threshold,
            length=len(command.waypoints),
        )
        if address not in self.dotbots:
            logger.warning("DotBot not found")
            return
        logger.info("Sending command")
        header = ProtocolHeader(
            destination=int(address, 16),
            source=int(self.settings.gw_address, 16),
            swarm_id=int(swarm_id, 16),
            application=ApplicationType(int(application)),
            version=PROTOCOL_VERSION,
        )
        waypoints_list = command.waypoints
        if ApplicationType(int(application)) == ApplicationType.SailBot:
            if self.dotbots[address].gps_position is not None:
                waypoints_list = [
                    self.dotbots[address].gps_position
                ] + command.waypoints
            payload = ProtocolPayload(
                header,
                PayloadType.GPS_WAYPOINTS,
                GPSWaypoints(
                    threshold=command.threshold,
                    waypoints=[
                        GPSPosition(
                            latitude=int(waypoint.latitude * 1e6),
                            longitude=int(waypoint.longitude * 1e6),
                        )
                        for waypoint in command.waypoints
                    ],
                ),
            )
        else:  # DotBot application
            if self.dotbots[address].lh2_position is not None:
                waypoints_list = [
                    self.dotbots[address].lh2_position
                ] + command.waypoints
            payload = ProtocolPayload(
                header,
                PayloadType.LH2_WAYPOINTS,
                LH2Waypoints(
                    threshold=command.threshold,
                    waypoints=[
                        LH2Location(
                            pos_x=int(waypoint.x * 1e6),
                            pos_y=int(waypoint.y * 1e6),
                            pos_z=int(waypoint.z * 1e6),
                        )
                        for waypoint in command.waypoints
                    ],
                ),
            )
        self.send_payload(payload)
        self.dotbots[address].waypoints = waypoints_list
        self.dotbots[address].waypoints_threshold = command.threshold
        self.qrkey.publish(
            "/notify",
            DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD).model_dump(
                exclude_none=True
            ),
        )

    def on_command_clear_position_history(self, topic, _):
        """Called when a clear position history command is received."""
        logger = self.logger.bind(command="clear_position_history", topic=topic)
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "clear_position_history":
            logger.warning("Invalid clear_position_history command topic")
            return
        _, address, application, _ = topic_split
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
        )
        if address not in self.dotbots:
            logger.warning("DotBot not found")
            return
        logger.info("Sending command")
        self.dotbots[address].position_history = []
        self.qrkey.publish(
            "/notify",
            DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD).model_dump(
                exclude_none=True
            ),
        )

    def on_lh2_add(self, topic, payload):
        """Called when an lh2 calibration point is added."""
        logger = self.logger.bind(lh2="add", topic=topic)
        topic_split = topic.split("/")[1:]
        if len(topic_split) != 2 or topic_split[-1] != "add":
            logger.warning("Invalid lh2 add topic")
            return
        try:
            payload = DotBotCalibrationIndexModel(**payload)
        except ValidationError as exc:
            self.logger.warning(f"Invalid calibration index payload: {exc.errors()}")
            return
        logger = self.logger.bind(**payload.model_dump())
        logger.info("Add calibration point")
        self.lh2_manager.add_calibration_point(payload.index)

    def on_lh2_start(self, topic, _):
        """Called to start the lh2 calibration."""
        logger = self.logger.bind(lh2="start", topic=topic)
        topic_split = topic.split("/")[1:]
        if len(topic_split) != 2 or topic_split[-1] != "start":
            logger.warning("Invalid lh2 start topic")
            return
        logger.info("Start calibration")
        self.lh2_manager.compute_calibration()

    def on_request(self, payload):
        logger = LOGGER.bind(topic="/request")
        logger.info("Request received")
        try:
            request = DotBotRequestModel(**payload)
        except ValidationError as exc:
            logger.warning(f"Invalid request: {exc.errors()}")
            return

        reply_topic = f"/reply/{request.reply}"
        if request.request == DotBotRequestType.DOTBOTS:
            logger.info("Publish dotbots")
            data = [
                dotbot.model_dump(exclude_none=True)
                for dotbot in self.get_dotbots(DotBotQueryModel())
            ]
            message = DotBotReplyModel(
                request=DotBotRequestType.DOTBOTS,
                data=data,
            ).model_dump(exclude_none=True)
            self.qrkey.publish(reply_topic, message)
        elif request.request == DotBotRequestType.LH2_CALIBRATION_STATE:
            logger.info("Publish LH2 state")
            message = DotBotReplyModel(
                request=DotBotRequestType.LH2_CALIBRATION_STATE,
                data=self.lh2_manager.state_model.model_dump(),
            ).model_dump(exclude_none=True)
            self.qrkey.publish(reply_topic, message)
        else:
            logger.warning("Unsupported request command")

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

        if self.settings.port == "sailbot-simulator":
            self.serial = SailBotSimulatorSerialInterface(on_byte_received)
        elif self.settings.port == "dotbot-simulator":
            self.serial = DotBotSimulatorSerialInterface(on_byte_received)
        else:
            self.serial = SerialInterface(
                self.settings.port, self.settings.baudrate, on_byte_received
            )
            self.serial.write(
                int(PROTOCOL_VERSION).to_bytes(
                    length=1, byteorder="little", signed=False
                )
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
                _, writer = await asyncio.open_connection(
                    "127.0.0.1", self.settings.controller_port
                )
            except ConnectionRefusedError:
                await asyncio.sleep(0.1)
            else:
                writer.close()
                break
        if self.settings.webbrowser is True:
            url = f"http://localhost:{self.settings.controller_port}/PyDotBot?pin={self.qrkey.pin_code}"
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
        )
        notification_cmd = DotBotNotificationCommand.NONE
        if source in self.dotbots:
            dotbot.mode = self.dotbots[source].mode
            dotbot.status = self.dotbots[source].status
            dotbot.direction = self.dotbots[source].direction
            dotbot.wind_angle = self.dotbots[source].wind_angle
            dotbot.rudder_angle = self.dotbots[source].rudder_angle
            dotbot.sail_angle = self.dotbots[source].sail_angle
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

        if payload.payload_type in [PayloadType.SAILBOT_DATA]:
            logger = logger.bind(
                wind_angle=dotbot.wind_angle,
                rudder_angle=dotbot.rudder_angle,
                sail_angle=dotbot.sail_angle,
            )

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

        if payload.payload_type == PayloadType.DOTBOT_SIMULATOR_DATA:
            dotbot.direction = payload.values.theta
            new_position = DotBotLH2Position(
                x=payload.values.pos_x / 1e6,
                y=payload.values.pos_y / 1e6,
                z=0,
            )
            dotbot.lh2_position = new_position
            dotbot.position_history.append(new_position)
            notification_cmd = DotBotNotificationCommand.UPDATE

        if payload.payload_type in [PayloadType.GPS_POSITION, PayloadType.SAILBOT_DATA]:
            new_position = DotBotGPSPosition(
                latitude=float(payload.values.latitude) / 1e6,
                longitude=float(payload.values.longitude) / 1e6,
            )
            dotbot.gps_position = new_position
            # Read wind sensor measurements
            dotbot.wind_angle = payload.values.wind_angle
            dotbot.rudder_angle = payload.values.rudder_angle
            dotbot.sail_angle = payload.values.sail_angle
            logger.info(
                "gps",
                lat=new_position.latitude,
                long=new_position.longitude,
                wind_angle=dotbot.wind_angle,
                rudder_angle=dotbot.rudder_angle,
                sail_angle=dotbot.sail_angle,
            )
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
                    wind_angle=dotbot.wind_angle,
                    rudder_angle=dotbot.rudder_angle,
                    sail_angle=dotbot.sail_angle,
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
                    websocket, json.dumps(notification.model_dump(exclude_none=True))
                )
                for websocket in self.websockets
            ]
        )
        self.qrkey.publish("/notify", notification.model_dump(exclude_none=True))

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
            _dotbot = DotBotModel(**dotbot.model_dump())
            _dotbot.position_history = _dotbot.position_history[: query.max_positions]
            dotbots.append(_dotbot)
        return sorted(dotbots, key=lambda dotbot: dotbot.address)

    async def web(self):
        """Starts the web server application."""
        logger = LOGGER.bind(context=__name__)
        config = uvicorn.Config(
            api, port=self.settings.controller_port, log_level="critical"
        )
        server = uvicorn.Server(config)

        try:
            logger.info("Starting web server")
            await server.serve()
        except asyncio.exceptions.CancelledError:
            logger.info("Web server cancelled")
        else:
            logger.info("Stopping web server")
            raise SystemExit()

    async def run(self):
        """Launch the controller."""
        tasks = []
        try:
            tasks = [
                asyncio.create_task(self.qrkey.start(subscriptions=self.subscriptions)),
                asyncio.create_task(self.web()),
                asyncio.create_task(self._open_webbrowser()),
                asyncio.create_task(self._start_serial()),
                asyncio.create_task(self._dotbots_status_refresh()),
            ]
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
