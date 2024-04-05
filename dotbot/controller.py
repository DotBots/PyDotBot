"""Interface of the Dotbot controller."""

import asyncio
import json
import math
import time
import webbrowser
import random
from binascii import hexlify
from dataclasses import dataclass
from typing import Dict, List, Optional

import lakers
import requests
import serial
import uvicorn
import websockets
from fastapi import WebSocket
from haversine import Unit, haversine

from dotbot import DOTBOT_ADDRESS_DEFAULT, GATEWAY_ADDRESS_DEFAULT
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.lighthouse2 import LighthouseManager, LighthouseManagerState
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotQueryModel,
    DotBotStatus,
)
from dotbot.mqtt import mqtt
from dotbot.protocol import (
    PROTOCOL_VERSION,
    ApplicationType,
    EdhocMessage,
    LH2Location,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
    ProtocolPayloadParserException,
)
from dotbot.serial_interface import SerialInterface, SerialInterfaceException
from dotbot.server import api
from dotbot.authz import fetch_credential_remotely, PendingEdhocSession

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

CRED_I = bytes.fromhex(
    "A2027734322D35302D33312D46462D45462D33372D33322D333908A101A5010202412B2001215820AC75E9ECE3E50BFC8ED60399889522405C47BF16DF96660A41298CB4307F7EB62258206E5DE611388A4B8A8211334AC7D37ECB52A387D257E6DB3C2A93DF21FF3AFFC8"
)
V = bytes.fromhex("72cc4761dbd4c78f758931aa589d348d1ef874a7e303ede2f140dcf3e6aa4aac")
CRED_V = bytes.fromhex(
    "a2026b6578616d706c652e65647508a101a501020241322001215820bbc34960526ea4d32e940cad2a234148ddc21791a12afbcbac93622046dd44f02258204519e257236b2a0ce2023f0931f1f386ca7afda64fcde0108c224c51eabf6072"
)


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
    handshake: bool = False
    use_mqtt: bool = False
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
        #         gps_position=DotBotGPSPosition(latitude=48.832313766146896, longitude=2.4126897594949184),
        #     ),
        # }
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
        self.mqtt = mqtt
        mqtt.controller = self
        if settings.use_mqtt is True:
            self.mqtt.init_app(api)
        self.logger = LOGGER.bind(context=__name__)
        self.pending_edhoc_sessions: Dict[str, PendingEdhocSession] = {}
        # self.edhoc_responder = lakers.EdhocResponder(V, CRED_V)
        # self.edhoc_ead_authenticator = lakers.AuthzAutenticator()

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

    async def request_voucher_for_dotbot(
        self, dotbot: DotBotModel, edhoc_responder: lakers.EdhocResponder, ead_1: bytes, message_1: bytes
    ):
        edhoc_ead_authenticator = lakers.AuthzAutenticator()
        loc_w, voucher_request = edhoc_ead_authenticator.process_ead_1(
            ead_1, message_1
        )
        voucher_request_url = f"{loc_w}/.well-known/lake-authz/voucher-request"
        self.logger.info(
            "Requesting voucher",
            url=voucher_request_url,
            voucher_request=voucher_request.hex(' ').upper(),
        )
        response = requests.post(voucher_request_url, data=voucher_request)
        if response.status_code == 200:
            self.logger.info("Got an ok voucher response", voucher_response=response.content.hex(' ').upper())
            ead_2 = edhoc_ead_authenticator.prepare_ead_2(response.content)
            c_r = random.randint(0, 23) # already cbor-encoded as single-byte integer
            message_2 = edhoc_responder.prepare_message_2(
                lakers.CredentialTransfer.ByValue, c_r, ead_2
            )
            self.pending_edhoc_sessions[dotbot.address] = PendingEdhocSession(dotbot, edhoc_responder, edhoc_ead_authenticator, loc_w, c_r)

            header = ProtocolHeader(
                destination=int(dotbot.address, 16),
                source=int(self.settings.gw_address, 16),
                swarm_id=int(self.settings.swarm_id, 16),
                application=dotbot.application,
                version=PROTOCOL_VERSION,
            )
            self.send_payload_to_pending(
                ProtocolPayload(
                    header,
                    PayloadType.EDHOC_MESSAGE,
                    EdhocMessage(value=message_2),
                )
            )
            self.logger.debug("Sent EDHOC message 2", message_2=message_2.hex(' ').upper())
        else:
            self.logger.error(
                "Error requesting voucher", status_code=response.status_code
            )

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

        if (
            source not in self.dotbots
            and source not in self.pending_edhoc_sessions
            and payload.payload_type == PayloadType.EDHOC_MESSAGE
        ):
            logger.info("New potential dotbot")
            edhoc_responder = lakers.EdhocResponder(V, CRED_V)
            try:
                message_1 = payload.values.value
                logger.debug("Will process EDHOC message", message_1=message_1.hex(' ').upper())
                ead_1 = edhoc_responder.process_message_1(message_1)
            except Exception as e:
                logger.error("Error processing message 1", error=e)
                return
            if ead_1 and ead_1.label() == lakers.consts.EAD_AUTHZ_LABEL:
                asyncio.create_task(
                    self.request_voucher_for_dotbot(dotbot, edhoc_responder, ead_1, message_1)
                )
                return
            else:
                logger.error("EDHOC message 1 should contain a valid EAD_1")
                return
        elif (
            source not in self.dotbots
            and source in self.pending_edhoc_sessions
            and payload.payload_type == PayloadType.EDHOC_MESSAGE
        ):
            logger.info("Potential EDHOC message 3")
            try:
                # check connection identifier
                assert payload.values.value[0] == self.pending_edhoc_sessions[source].c_r
                message_3 = payload.values.value[1:]
                logger.debug("Will process EDHOC message", message_3=message_3.hex(' ').upper())
                edhoc_responder = self.pending_edhoc_sessions[source].responder
                id_cred_i, _ead_3 = edhoc_responder.parse_message_3(message_3)
                try:
                    if len(id_cred_i) > 1:
                        cred_i = id_cred_i
                    else:
                        cred_i = fetch_credential_remotely(self.pending_edhoc_sessions[source].loc_w, id_cred_i)
                except Exception as e:
                    logger.error("Error fetching credential", error=e)
                    self.pending_edhoc_sessions.pop(source)
                    return
                r_prk_out = edhoc_responder.verify_message_3(cred_i)
                logger.info("EDHOC handshake worked")
                logger.debug("Derived prk_out", prk_out=r_prk_out.hex(' ').upper())
            except Exception as e:
                logger.error("Error processing message 3", error=e)
                self.pending_edhoc_sessions.pop(source)
                return
            logger.info("New dotbot")
            # NOTE: could save self.pending_edhoc_sessions[source].responder state for future use, e.g. to derive OSCORE keys
            self.pending_edhoc_sessions.pop(source)
            notification_cmd = DotBotNotificationCommand.RELOAD
        elif source in self.dotbots:
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
            # what do to here?
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
        if self.mqtt.client.is_connected is True:
            self.mqtt.publish(
                f"/dotbots/{self.settings.swarm_id}/notifications",
                json.dumps(notification.dict(exclude_none=True)),
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
            self.logger.info(
                "Payload sent",
                application=payload.header.application.name,
                destination=destination,
                payload_type=payload.payload_type.name,
            )

    def send_payload_to_pending(self, payload: ProtocolPayload):
        """Sends a command in an HDLC frame over serial."""
        destination = hexlify(
            int(payload.header.destination).to_bytes(8, "big")
        ).decode()
        if destination not in self.pending_edhoc_sessions:
            return
        # make sure the application in the payload matches the bot application
        payload.header.application = self.pending_edhoc_sessions[destination].dotbot.application
        print("sending...")
        if self.serial is not None:
            self.serial.write(hdlc_encode(payload.to_bytes()))
            self.logger.info(
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

    async def _publish_dotbots(self):
        while 1:
            if self.mqtt.client.is_connected is False:
                await asyncio.sleep(1)
                continue
            self.logger.debug("Publish dotbots to MQTT")
            self.mqtt.publish(
                f"/dotbots/{self.settings.swarm_id}",
                [
                    dotbot.dict(exclude_none=True)
                    for dotbot in self.get_dotbots(DotBotQueryModel())
                ],
            )
            await asyncio.sleep(1)

    async def web(self):
        """Starts the web server application."""
        logger = LOGGER.bind(context=__name__)
        config = uvicorn.Config(api, port=8000, log_level="critical")
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
                asyncio.create_task(self.web()),
                asyncio.create_task(self._open_webbrowser()),
                asyncio.create_task(self._start_serial()),
                asyncio.create_task(self._dotbots_status_refresh()),
                asyncio.create_task(self._publish_dotbots()),
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
