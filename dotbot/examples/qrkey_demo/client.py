# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-FileCopyrightText: 2026-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Interface of the QrKey client."""

import asyncio
import json
import os
import threading
import webbrowser
from dataclasses import dataclass

from pydantic import ValidationError
from pydantic.tools import parse_obj_as
from qrkey import QrkeyController, SubscriptionModel, qrkey_settings
from websockets import exceptions as websockets_exceptions
from websockets.asyncio.client import connect

from dotbot import CONTROLLER_HTTP_HOSTNAME_DEFAULT, CONTROLLER_HTTP_PORT_DEFAULT
from dotbot.logger import LOGGER
from dotbot.models import (
    DotBotAreaModel,
    DotBotMoveRawCommandModel,
    DotBotReplyModel,
    DotBotRequestModel,
    DotBotRequestType,
    DotBotRgbLedCommandModel,
    DotBotSiteModel,
    DotBotWaypoints,
    DotBotXGOActionCommandModel,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient

# PyDotBot's museum-demo UX prefers a long rotation window: operators
# scan a QR, walk away with a phone, come back later. Upstream qrkey
# defaults of 15min / 2min are too aggressive for that. Override the
# singleton in-place — QrkeyController reads these at runtime in the
# rotation loop, so post-import mutation is safe (only mqtt_* fields
# are read at QrkeyController.__init__ time).
qrkey_settings.pin_code_refresh_interval = 2 * 60 * 60  # 2 hours
qrkey_settings.pin_code_revoke_delay = 15 * 60  # 15 minutes

# What the relay asks the controller stream for: MQTT carries every frame
# to every phone, so the rate stays low; the trail is what the phone draws.
STREAM_HZ = 2
STREAM_TRAIL = 100
# Reconnect delays after the stream closes, doubling up to the cap
RECONNECT_MIN_S = 0.5
RECONNECT_MAX_S = 10.0


@dataclass
class QrKeyClientSettings:
    """Data class that holds QrKey client settings."""

    http_host: str = CONTROLLER_HTTP_HOSTNAME_DEFAULT
    http_port: int = CONTROLLER_HTTP_PORT_DEFAULT
    webbrowser: bool = False
    verbose: bool = False
    log_level: str = "info"
    log_output: str = os.path.join(os.getcwd(), "pydotbot-qrkey.log")


class AsyncWorker:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        # The 1-second timeout in the original qrkey 0.12.1 design was
        # too tight: every move_raw / rgb_led / waypoints command makes
        # an HTTP call to the controller, and a slow network or a busy
        # controller would trip a TimeoutError even though the command
        # was actually delivered. 10 s gives MQTT-side commands enough
        # slack without hanging forever if the controller is truly
        # unreachable.
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=10)


class QrKeyClient:
    """Abstract base class of specific implementations of Dotbot controllers."""

    def __init__(self, settings: QrKeyClientSettings, client: RestClient):
        self.client = client
        self.logger = LOGGER.bind(context=__name__)
        self.settings: QrKeyClientSettings = settings
        self.worker = AsyncWorker()
        self.qrkey = None

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
        ]

    def on_command_move_raw(self, topic, payload):
        """Called when a move raw command is received."""
        logger = self.logger.bind(command="move_raw")
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "move_raw":
            logger.warning("Invalid move_raw command topic")
            return
        _, address, application, _ = topic_split
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
        logger.info(
            "Forwarding move_raw command",
            address=address,
            command=command.__class__.__name__,
        )
        self.worker.run(
            self.client.send_move_raw_command(
                address, ApplicationType(int(application)), command
            )
        )

    def on_command_rgb_led(self, topic, payload):
        """Called when an rgb led command is received."""
        logger = self.logger.bind(command="rgb_led")
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "rgb_led":
            logger.warning("Invalid rgb_led command topic")
            return
        _, address, application, _ = topic_split
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
        logger.info(
            "Forwarding RGB LED command",
            address=address,
            command=command.__class__.__name__,
        )
        self.worker.run(self.client.send_rgb_led_command(address, command))

    def on_command_xgo_action(self, topic, payload):
        """Called when an rgb led command is received."""
        logger = self.logger.bind(command="xgo_action")
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "xgo_action":
            logger.warning("Invalid xgo_action command topic")
            return
        _, address, application, _ = topic_split
        try:
            command = DotBotXGOActionCommandModel(**payload)
        except ValidationError as exc:
            logger.warning(f"Invalid xgo_action command: {exc.errors()}")
            return
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            **command.model_dump(),
        )
        logger.info(
            "Forwarding XGO action command",
            address=address,
            command=command.__class__.__name__,
        )
        # TODO: implement xgo action command sending

    def on_command_waypoints(self, topic, payload):
        """Called when a list of waypoints is received."""
        logger = self.logger.bind(command="waypoints")
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "waypoints":
            logger.warning("Invalid waypoints command topic")
            return
        _, address, application, _ = topic_split
        command = parse_obj_as(DotBotWaypoints, payload)
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
            threshold=command.threshold,
            length=len(command.waypoints),
        )

        logger.info(
            "Forwarding waypoints command",
            address=address,
            command=payload.__class__.__name__,
        )
        self.worker.run(
            self.client.send_waypoint_command(
                address, ApplicationType(int(application)), command
            )
        )

    def on_command_clear_position_history(self, topic, _):
        """Called when a clear position history command is received."""
        logger = self.logger.bind(command="clear_position_history")
        topic_split = topic.split("/")[2:]
        if len(topic_split) != 4 or topic_split[-1] != "clear_position_history":
            logger.warning("Invalid clear_position_history command topic")
            return
        _, address, application, _ = topic_split
        logger = logger.bind(
            address=address,
            application=ApplicationType(int(application)).name,
        )
        logger.info("Notify clear command", address=address)
        self.worker.run(self.client.clear_trail(address))

    def on_request(self, payload):
        logger = LOGGER.bind(topic="/request")
        logger.info("Request received", **payload)
        try:
            request = DotBotRequestModel(**payload)
        except ValidationError as exc:
            logger.warning(f"Invalid request: {exc.errors()}")
            return

        reply_topic = f"/reply/{request.reply}"
        if request.request == DotBotRequestType.DOTBOTS:
            logger.info("Publish dotbots")
            dotbots = self.worker.run(self.client.fetch_dotbots())
            data = [dotbot.model_dump(exclude_none=True) for dotbot in dotbots]
            message = DotBotReplyModel(
                request=DotBotRequestType.DOTBOTS,
                data=data,
            ).model_dump(exclude_none=True)
            self.qrkey.publish(reply_topic, message)
        elif request.request == DotBotRequestType.SITE:
            logger.info("Publish the site")
            site = self.worker.run(self.client.fetch_site())
            model = DotBotSiteModel(
                name=site.name,
                anchor=site.anchor,
                extent_mm=list(site.extent_mm) if site.extent_mm else None,
                areas=[
                    DotBotAreaModel(**a.as_dict())
                    for a in sorted(site.areas.values(), key=lambda a: a.name)
                ],
            )
            message = DotBotReplyModel(
                request=DotBotRequestType.SITE,
                data=model.model_dump(),
            ).model_dump(exclude_none=True)
            self.qrkey.publish(reply_topic, message)
        else:
            logger.warning("Unsupported request command")

    async def _open_webbrowser(self):
        """Wait until the server is ready before opening a web browser."""
        while 1:
            try:
                _, writer = await asyncio.open_connection(
                    self.settings.http_host, self.settings.http_port
                )
            except ConnectionRefusedError:
                await asyncio.sleep(0.1)
            else:
                writer.close()
                break
        url = (
            f"{qrkey_settings.frontend_base_url}?"
            f"use_qrkey=true&"
            f"pin={self.qrkey.pin_code}&"
            f"mqtt_host={qrkey_settings.mqtt_host}&"
            f"mqtt_port={qrkey_settings.mqtt_ws_port}&"
            f"mqtt_version={qrkey_settings.mqtt_version}&"
            f"mqtt_use_ssl={qrkey_settings.mqtt_use_ssl}"
        )
        if qrkey_settings.mqtt_username is not None:
            url += f"&mqtt_username={qrkey_settings.mqtt_username}"
        if qrkey_settings.mqtt_password is not None:
            url += f"&mqtt_password={qrkey_settings.mqtt_password}"
        self.logger.debug("Using frontend URL", url=url)
        if self.settings.webbrowser is True:
            self.logger.info("Opening webbrowser", url=url)
            webbrowser.open(url)

    async def start_ws_client(self):
        """Relay the controller stream to MQTT `/notify`, frame by frame,
        reconnecting with backoff and resuming from the last frame relayed."""
        run, seq = None, None
        delay = RECONNECT_MIN_S
        while True:
            url = (
                f"ws://{self.settings.http_host}:{self.settings.http_port}"
                f"/controller/ws/stream?hz={STREAM_HZ}&trail={STREAM_TRAIL}"
            )
            if run is not None and seq is not None:
                url += f"&since={seq}&run={run}"
            try:
                async with connect(url, max_size=None) as websocket:
                    while True:
                        message = await websocket.recv()
                        delay = RECONNECT_MIN_S
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            self.logger.warning(
                                "Received invalid JSON message", message=message
                            )
                            continue
                        if payload.get("type") == "hello":
                            if payload.get("run") != run:
                                run, seq = payload.get("run"), None
                            continue
                        self.qrkey.publish("/notify", payload)
                        if "seq" in payload:
                            await websocket.send(json.dumps({"ack": payload["seq"]}))
                            if payload.get("type") != "snapshot" or (
                                payload.get("part") == payload.get("parts")
                            ):
                                seq = payload["seq"]
            except websockets_exceptions.ConnectionClosed as exc:
                self.logger.warning("Controller stream lost, reconnecting", error=str(exc))
            except OSError as exc:
                self.logger.warning("Controller unreachable, retrying", error=str(exc))
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_S)

    async def run(self):
        """Launch the controller."""
        tasks = []
        self.qrkey = QrkeyController(self.on_request, LOGGER, root_topic="/pydotbot")
        try:
            tasks = [
                asyncio.create_task(
                    name="QrKey controller",
                    coro=self.qrkey.start(subscriptions=self.subscriptions),
                ),
                asyncio.create_task(
                    name="WebSocket client", coro=self.start_ws_client()
                ),
            ]
            if self.settings.webbrowser:
                tasks.append(
                    asyncio.create_task(
                        name="Web browser opener", coro=self._open_webbrowser()
                    )
                )
            await asyncio.gather(*tasks)
        except ConnectionRefusedError as exc:
            self.logger.warning(f"Failed to connect to PyDotBot controller: {exc}")
        except websockets_exceptions.ConnectionClosed as exc:
            self.logger.warning(f"WebSocket connection closed: {exc}")
        except SystemExit:
            pass
        finally:
            self.logger.info("Stopping QrKey client")
            for task in tasks:
                self.logger.info(f"Cancelling task '{task.get_name()}'")
                task.cancel()
            self.logger.info("QrKey client stopped")
