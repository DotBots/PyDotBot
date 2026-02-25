# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Interface of the Dotbot controller."""

import asyncio
import dataclasses
import json
import math
import os
import time
import webbrowser
from binascii import hexlify
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import serial
import starlette
import uvicorn
import websockets
from dotbot_utils.protocol import Frame, Payload
from dotbot_utils.serial_interface import SerialInterfaceException
from fastapi import WebSocket

from dotbot import (
    CONTROLLER_ADAPTER_DEFAULT,
    CONTROLLER_HTTP_PORT_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    MAP_SIZE_DEFAULT,
    MQTT_HOST_DEFAULT,
    MQTT_PORT_DEFAULT,
    NETWORK_ID_DEFAULT,
    SERIAL_BAUDRATE_DEFAULT,
    SERIAL_PORT_DEFAULT,
    SIMULATOR_INIT_STATE_PATH_DEFAULT,
)
from dotbot.adapter import (
    DotBotSimulatorAdapter,
    GatewayAdapterBase,
    MarilibCloudAdapter,
    MarilibEdgeAdapter,
    SailBotSimulatorAdapter,
    SerialAdapter,
)
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotMapSizeModel,
    DotBotModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotQueryModel,
    DotBotStatus,
)
from dotbot.protocol import (
    ApplicationType,
    PayloadLh2CalibrationHomography,
    PayloadType,
)
from dotbot.server import api

# from dotbot.models import (
#     DotBotModel,
#     DotBotGPSPosition,
#     DotBotLH2Position,
#     DotBotRgbLedCommandModel,
# )


INACTIVE_DELAY = 5  # seconds
LOST_DELAY = 60  # seconds
LH2_POSITION_DISTANCE_THRESHOLD = 20  # mm
GPS_POSITION_DISTANCE_THRESHOLD = 5  # meters
CALIBRATION_PATH = Path.home() / ".dotbot" / "calibration.out"


@dataclass
class CalibrationHomography:
    """Dataclass that holds computed LH2 homography for a basestation indicated by index."""

    homography_matrix: bytes = dataclasses.field(default_factory=lambda: bytearray)


def load_calibration() -> list[CalibrationHomography]:
    if not os.path.exists(CALIBRATION_PATH):
        return []
    with open(CALIBRATION_PATH, "rb") as calibration_file:
        homographies: list[CalibrationHomography] = []
        homographies_num = int.from_bytes(
            calibration_file.read(1), "little", signed=False
        )
        for _ in range(homographies_num):
            homographies.append(
                CalibrationHomography(homography_matrix=calibration_file.read(36))
            )
    return homographies


class ControllerException(Exception):
    """Exception raised by Dotbot controllers."""


@dataclass
class ControllerSettings:
    """Data class that holds controller settings."""

    adapter: str = CONTROLLER_ADAPTER_DEFAULT
    port: str = SERIAL_PORT_DEFAULT
    baudrate: int = SERIAL_BAUDRATE_DEFAULT
    mqtt_host: str = MQTT_HOST_DEFAULT
    mqtt_port: int = MQTT_PORT_DEFAULT
    mqtt_use_tls: bool = False
    gw_address: str = GATEWAY_ADDRESS_DEFAULT
    network_id: str = NETWORK_ID_DEFAULT
    controller_http_port: int = CONTROLLER_HTTP_PORT_DEFAULT
    map_size: str = MAP_SIZE_DEFAULT
    webbrowser: bool = False
    verbose: bool = False
    log_level: str = "info"
    log_output: str = os.path.join(os.getcwd(), "pydotbot.log")
    simulator_init_state_path: str = SIMULATOR_INIT_STATE_PATH_DEFAULT


def lh2_distance(last: DotBotLH2Position, new: DotBotLH2Position) -> float:
    """Helper function that computes the distance between 2 LH2 positions."""
    return math.sqrt(((new.x - last.x) ** 2) + ((new.y - last.y) ** 2))


def gps_distance(last: DotBotGPSPosition, new: DotBotGPSPosition) -> float:
    """Helper function that computes the distance between 2 GPS positions in m."""
    # Simple haversine formula implementation
    lat1, lon1 = math.radians(last.latitude), math.radians(last.longitude)
    lat2, lon2 = math.radians(new.latitude), math.radians(new.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    # Earth's radius in meters
    earth_radius = 6371000
    return earth_radius * c


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
        self.settings = settings
        self.adapter: GatewayAdapterBase = None
        self.websockets = []
        self.lh2_calibration: list[CalibrationHomography] = load_calibration()
        self.api = api
        self.map_size = DotBotMapSizeModel(
            width=int(settings.map_size.split("x")[0]),
            height=int(settings.map_size.split("x")[1]),
        )
        api.controller = self

    async def _open_webbrowser(self):
        """Wait until the server is ready before opening a web browser."""
        while 1:
            try:
                _, writer = await asyncio.open_connection(
                    "127.0.0.1", self.settings.controller_http_port
                )
            except ConnectionRefusedError:
                await asyncio.sleep(0.1)
            else:
                writer.close()
                break
        url = f"http://localhost:{self.settings.controller_http_port}/PyDotBot"
        self.logger.debug("Using frontend URL", url=url)
        if self.settings.webbrowser is True:
            self.logger.info("Opening webbrowser", url=url)
            webbrowser.open(url)

    async def _dotbots_status_refresh(self):
        """Coroutine that periodically updates the status of known dotbot."""
        while 1:
            needs_refresh = [False] * len(self.dotbots)
            for idx, dotbot in enumerate(self.dotbots.values()):
                previous_status = dotbot.status
                if dotbot.last_seen + LOST_DELAY < time.time():
                    dotbot.status = DotBotStatus.LOST
                elif dotbot.last_seen + INACTIVE_DELAY < time.time():
                    dotbot.status = DotBotStatus.INACTIVE
                else:
                    dotbot.status = DotBotStatus.ACTIVE
                logger = self.logger.bind(
                    source=dotbot.address,
                    application=dotbot.application.name,
                )
                if len(needs_refresh) > idx:
                    needs_refresh[idx] = bool(previous_status != dotbot.status)
                    if needs_refresh[idx]:
                        logger.info(
                            "Dotbot status changed",
                            previous_status=previous_status.name,
                            status=dotbot.status.name,
                        )
            if any(needs_refresh) is True:
                await self.notify_clients(
                    DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD)
                )
            await asyncio.sleep(1)

    def handle_received_frame(
        self, frame: Frame
    ):  # pylint:disable=too-many-branches,too-many-statements
        """Handle a received frame."""
        # Controller is not interested by command messages received
        if frame.packet.payload_type in [
            PayloadType.CMD_MOVE_RAW,
            PayloadType.CMD_RGB_LED,
        ]:
            return
        source = hexlify(int(frame.header.source).to_bytes(8, "big")).decode()
        logger = self.logger.bind(
            source=source,
            payload_type=PayloadType(frame.packet.payload_type).name,
        )
        if source == GATEWAY_ADDRESS_DEFAULT:
            logger.warning("Invalid source in payload")
            return
        dotbot = DotBotModel(
            address=source,
            last_seen=time.time(),
        )
        notification_cmd = DotBotNotificationCommand.NONE

        if source not in self.dotbots and frame.packet.payload_type not in [
            PayloadType.ADVERTISEMENT,
            PayloadType.DOTBOT_ADVERTISEMENT,
        ]:
            logger.info("Ignoring non advertised dotbot")
            return

        if source in self.dotbots:
            dotbot.application = self.dotbots[source].application
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
            dotbot.battery = self.dotbots[source].battery
            dotbot.calibrated = self.dotbots[source].calibrated
        else:
            # reload if a new dotbot comes in
            logger.info("New robot")
            notification_cmd = DotBotNotificationCommand.NEW_DOTBOT

        if frame.packet.payload_type == PayloadType.ADVERTISEMENT:
            logger = logger.bind(
                application=ApplicationType(frame.packet.payload.application).name,
            )
            dotbot.application = ApplicationType(frame.packet.payload.application)
            self.dotbots.update({dotbot.address: dotbot})
            logger.debug("Advertisement received")

        if frame.packet.payload_type == PayloadType.DOTBOT_ADVERTISEMENT:
            logger = logger.bind(application=ApplicationType.DotBot.name)
            dotbot.calibrated = int(frame.packet.payload.calibrated)
            logger.info("Advertisement received", calibrated=hex(dotbot.calibrated))
            # Send calibration to dotbot if it's not calibrated and the localization system has calibration
            need_update = False
            is_fully_calibrated = all(
                [
                    dotbot.calibrated >> index & 0x01
                    for index in range(len(self.lh2_calibration))
                ]
            )
            if is_fully_calibrated is False and self.lh2_calibration:
                # Send calibration to new dotbot if the localization system is calibrated
                self.logger.info("Send calibration data", payload=self.lh2_calibration)
                self.dotbots.update({dotbot.address: dotbot})
                for index, homography in enumerate(self.lh2_calibration):
                    self.logger.info(
                        "Sending calibration homography",
                        index=index,
                        matrix=homography.homography_matrix,
                    )
                    payload = PayloadLh2CalibrationHomography(
                        index=index,
                        homography_matrix=homography.homography_matrix,
                    )
                    self.send_payload(int(source, 16), payload=payload)
            elif is_fully_calibrated is True:
                if frame.packet.payload.direction != 0xFFFF:
                    dotbot.direction = frame.packet.payload.direction
                new_position = DotBotLH2Position(
                    x=frame.packet.payload.pos_x,
                    y=frame.packet.payload.pos_y,
                    z=0.0,
                )
                if new_position.x != 0xFFFFFFFF and new_position.y != 0xFFFFFFFF:
                    dotbot.lh2_position = new_position
                    if (
                        dotbot.position_history
                        and lh2_distance(dotbot.position_history[-1], new_position)
                        < LH2_POSITION_DISTANCE_THRESHOLD
                    ):
                        # If the new position is too close from the last one, we consider it as noise and we don't add it to the position history
                        logger.debug(
                            "Discarding LH2 position update because it's too close from the last one",
                            last_position=dotbot.position_history[-1].model_dump(),
                            new_position=new_position.model_dump(),
                            distance=lh2_distance(
                                dotbot.position_history[-1], new_position
                            ),
                        )
                    else:
                        dotbot.position_history.append(new_position)
                        if len(dotbot.position_history) > MAX_POSITION_HISTORY_SIZE:
                            dotbot.position_history.pop(0)
                need_update = True

            if dotbot.battery != frame.packet.payload.battery / 1000.0:
                dotbot.battery = frame.packet.payload.battery / 1000.0  # mV to V
                need_update = True

            self.logger.debug(
                "Advertisement Data",
                direction=frame.packet.payload.direction,
                X=frame.packet.payload.pos_x,
                Y=frame.packet.payload.pos_x,
                battery=frame.packet.payload.battery,
            )
            if need_update is True:
                notification_cmd = DotBotNotificationCommand.UPDATE

        if (
            frame.packet.payload_type == PayloadType.SAILBOT_DATA
            and -500 <= frame.packet.payload.direction <= 500
        ):
            dotbot.direction = frame.packet.payload.direction
            logger = logger.bind(direction=dotbot.direction)

        if frame.packet.payload_type in [PayloadType.SAILBOT_DATA]:
            logger = logger.bind(
                wind_angle=dotbot.wind_angle,
                rudder_angle=dotbot.rudder_angle,
                sail_angle=dotbot.sail_angle,
            )

        if frame.packet.payload_type in [
            PayloadType.GPS_POSITION,
            PayloadType.SAILBOT_DATA,
        ]:
            new_position = DotBotGPSPosition(
                latitude=float(frame.packet.payload.latitude) / 1e6,
                longitude=float(frame.packet.payload.longitude) / 1e6,
            )
            dotbot.gps_position = new_position
            # Read wind sensor measurements
            dotbot.wind_angle = frame.packet.payload.wind_angle
            dotbot.rudder_angle = frame.packet.payload.rudder_angle
            dotbot.sail_angle = frame.packet.payload.sail_angle
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
                    battery=dotbot.battery,
                ),
            )
        else:
            notification = DotBotNotificationModel(cmd=notification_cmd.value)

        if self.settings.verbose is True:
            print(frame)
        self.dotbots.update({dotbot.address: dotbot})
        if notification_cmd != DotBotNotificationCommand.NEW_DOTBOT:
            notification.data = DotBotModel(**dotbot.model_dump(exclude_none=True))
        if notification_cmd != DotBotNotificationCommand.NONE:
            asyncio.create_task(self.notify_clients(notification))

    async def _ws_send_safe(self, websocket: WebSocket, msg: str):
        """Safely send a message to a websocket client."""
        try:
            await websocket.send_text(msg)
        except (
            websockets.exceptions.ConnectionClosedError,
            RuntimeError,
            starlette.websockets.WebSocketDisconnect,
        ) as exc:
            self.logger.warning(
                "Failed to send message to websocket client",
                error=str(exc),
            )
            if websocket in self.websockets:
                self.websockets.remove(websocket)

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

    def send_payload(self, destination: int, payload: Payload):
        """Sends a command in an HDLC frame over serial."""
        if self.adapter is None:
            self.logger.warning("Adapter not started")
            return
        dest_str = hexlify(destination.to_bytes(8, "big")).decode()
        if dest_str not in self.dotbots:
            return
        self.adapter.send_payload(destination, payload=payload)
        self.logger.debug(
            "Payload sent",
            application=self.dotbots[dest_str].application.name,
            destination=dest_str,
            payload=payload,
        )

    def get_dotbots(self, query: DotBotQueryModel) -> List[DotBotModel]:
        """Returns the list of dotbots matching the query."""
        dotbots: List[DotBotModel] = []
        for dotbot in self.dotbots.values():
            if query.address is not None and dotbot.address != query.address:
                continue
            if (
                query.application is not None
                and dotbot.application.value != query.application
            ):
                continue
            if query.status is not None and dotbot.status.value != query.status:
                continue
            if query.max_battery is not None and dotbot.battery is not None:
                if dotbot.battery > query.max_battery:
                    continue
            if query.min_battery is not None and dotbot.battery is not None:
                if dotbot.battery < query.min_battery:
                    continue
            if (
                any(
                    [
                        query.max_position_x is not None,
                        query.min_position_x is not None,
                        query.max_position_y is not None,
                        query.min_position_y is not None,
                    ]
                )
                and dotbot.lh2_position is None
            ):
                continue
            if dotbot.lh2_position is None and query.max_positions is not None:
                continue
            if dotbot.lh2_position is not None:
                if query.max_position_x is not None:
                    if query.max_position_x < dotbot.lh2_position.x:
                        continue
                if query.min_position_x is not None:
                    if query.min_position_x > dotbot.lh2_position.x:
                        continue
                if query.max_position_y is not None:
                    if query.max_position_y < dotbot.lh2_position.y:
                        continue
                if query.min_position_y is not None:
                    if query.min_position_y > dotbot.lh2_position.y:
                        continue
            _dotbot = DotBotModel(**dotbot.model_dump())
            max_positions = (
                MAX_POSITION_HISTORY_SIZE
                if query.max_positions is None
                else query.max_positions
            )
            _dotbot.position_history = _dotbot.position_history[:max_positions]
            dotbots.append(_dotbot)
        dotbots = sorted(dotbots, key=lambda dotbot: dotbot.address)
        if query.limit is not None:
            dotbots = dotbots[: query.limit]
        return dotbots

    async def web(self):
        """Starts the web server application."""
        logger = LOGGER.bind(context=__name__)
        config = uvicorn.Config(
            api,
            host="0.0.0.0",
            port=self.settings.controller_http_port,
            log_level="critical",
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

    async def _start_adapter(self):
        """Starts the communication adapter."""
        if self.settings.adapter == "edge":
            self.adapter = MarilibEdgeAdapter(
                self.settings.port, self.settings.baudrate
            )
        elif self.settings.adapter == "cloud":
            self.adapter = MarilibCloudAdapter(
                host=self.settings.mqtt_host,
                port=self.settings.mqtt_port,
                use_tls=self.settings.mqtt_use_tls,
                network_id=int(self.settings.network_id, 16),
            )
        elif self.settings.adapter == "dotbot-simulator":
            self.adapter = DotBotSimulatorAdapter(
                self.settings.simulator_init_state_path,
            )
        elif self.settings.adapter == "sailbot-simulator":
            self.adapter = SailBotSimulatorAdapter()
        else:
            self.adapter = SerialAdapter(
                self.settings.port,
                self.settings.baudrate,
            )
        self.logger.info(
            "Starting communication adapter", adapter=self.settings.adapter
        )
        await self.adapter.start(self.handle_received_frame)

    async def run(self):
        """Launch the controller."""
        tasks = []
        try:
            tasks = [
                asyncio.create_task(name="Web server", coro=self.web()),
                asyncio.create_task(name="Web browser", coro=self._open_webbrowser()),
                asyncio.create_task(
                    name="Dotbots status refresh", coro=self._dotbots_status_refresh()
                ),
                asyncio.create_task(
                    name="Start communication adapter", coro=self._start_adapter()
                ),
            ]
            await asyncio.gather(*tasks)
        except (
            SerialInterfaceException,
            serial.serialutil.SerialException,
        ) as exc:
            self.logger.error(f"Error: {exc}")
        except SystemExit:
            pass
        finally:
            self.adapter.close()
            self.logger.info("Stopping controller")
            for task in tasks:
                self.logger.info(f"Cancelling task '{task.get_name()}'")
                task.cancel()
            self.logger.info("Controller stopped")
