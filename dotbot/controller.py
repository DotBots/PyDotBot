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
import queue
import time
import webbrowser
from dataclasses import dataclass
from typing import Dict, List, Optional

import serial
import starlette
import uvicorn
import websockets
from dotbot_utils.protocol import Frame, Payload
from dotbot_utils.serial_interface import SerialInterfaceException
from fastapi import WebSocket

from dotbot import (
    CONTROLLER_ADAPTER_DEFAULT,
    CONTROLLER_HTTP_HOST_DEFAULT,
    CONTROLLER_HTTP_PORT_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    MQTT_HOST_DEFAULT,
    MQTT_PORT_DEFAULT,
    MRTA_URL_DEFAULT,
    NETWORK_ID_DEFAULT,
    SERIAL_BAUDRATE_DEFAULT,
    SERIAL_PORT_DEFAULT,
    SIMULATOR_INIT_STATE_DEFAULT,
    SWARMIT_URL_DEFAULT,
    addr_to_hex,
)
from dotbot.adapter import (
    DotBotSimulatorAdapter,
    GatewayAdapterBase,
    MarilibCloudAdapter,
    MarilibEdgeAdapter,
    SailBotSimulatorAdapter,
    SerialAdapter,
)
from dotbot.calibration.driver import SessionDriver
from dotbot.calibration.lighthouse2 import homography_as_float32
from dotbot.camera.raster import WARP_FPS_MAX
from dotbot.camera.service import CameraService
from dotbot.csv_data_logger import (
    CameraCSVLogger,
    CSVDataLogger,
    CSVLog,
    camera_log_path,
)
from dotbot.dotbot_simulator import DotBotSimulator, SimulatedDotBotSettings
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotCalibrationSessionModel,
    DotBotCameraDetectionModel,
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotQueryModel,
    DotBotStatus,
)
from dotbot.protocol import (
    ApplicationType,
    ControlModeType,
    PayloadLh2CalibrationHomography,
    PayloadType,
)
from dotbot.server import api, default_ui_path
from dotbot.site import Site
from dotbot.swarm_client import build_swarmit_client, conn_string

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


def load_calibration(spec: str, site: Optional[str] = None):
    """The schema 2 calibration `spec` names: a file path or an id prefix.

    Never the newest file on disk: a controller runs on the calibration it
    was told to run on, so that two bots reporting the same id are known to
    carry the same numbers. An id prefix resolves under `site` only.
    """
    from dotbot.calibration.lighthouse2 import load_calibration as _load

    return _load(spec, site=site)


def load_camera_calibration(spec: str, site: Optional[str] = None):
    """The camera registration `spec` names: a file path or an id prefix."""
    from dotbot.camera.registration import load_camera_calibration as _load

    return _load(spec, site=site)


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
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    gw_address: str = GATEWAY_ADDRESS_DEFAULT
    network_id: str = NETWORK_ID_DEFAULT
    controller_http_port: int = CONTROLLER_HTTP_PORT_DEFAULT
    controller_http_host: str = CONTROLLER_HTTP_HOST_DEFAULT
    site: Optional[Site] = None
    lh2_calibration: Optional[str] = None
    camera_calibration: Optional[str] = None
    camera_detect: bool = True
    background_map: str = ""
    headless: bool = False
    verbose: bool = False
    log_level: str = "info"
    log_output: str = os.path.join(os.getcwd(), "pydotbot.log")
    csv_data_output: Optional[str] = None
    simulator_init_state: str = SIMULATOR_INIT_STATE_DEFAULT
    swarmit_url: str = SWARMIT_URL_DEFAULT
    mrta_url: str = MRTA_URL_DEFAULT


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
        self.site = settings.site or Site()
        self.calibration = None
        self.lh2_calibration = []
        if settings.lh2_calibration:
            self.calibration = load_calibration(
                settings.lh2_calibration, site=self.site.name
            )
            self.lh2_calibration = self.calibration.stations
            self.logger.info(
                "Calibration loaded",
                path=str(self.calibration.path),
                site=self.calibration.site.name,
                calibration_id=self.calibration.id,
                stations=len(self.lh2_calibration),
            )
        else:
            self.logger.info(
                "No calibration selected: robots keep whatever they hold. "
                "Pass --lh2-calibration <path|id> or set [run.controller] lh2_calibration."
            )
        self.cameras: List[CameraService] = []
        # The warp each camera's last pushed detection came from, so a
        # console is told about a frame once.
        self._camera_pushed: Dict[str, int] = {}
        self.camera_csv_loggers: Dict[str, CameraCSVLogger] = {}
        if settings.camera_calibration:
            self._start_camera(settings.camera_calibration)
        self.calibration_session = SessionDriver(
            client_factory=self._swarmit_client,
            notify=self._notify_calibration_session,
            site=self.site,
        )
        self.api = api
        if settings.csv_data_output is not None:
            self.logger.info("CSV data output enabled", path=settings.csv_data_output)
            self.csv_data_logger = CSVDataLogger(settings.csv_data_output)
        else:
            self.csv_data_logger = None
        self._dotbot_twins: Dict[str, DotBotSimulator] = {}
        self._dotbot_twin_timestamps: Dict[str, float] = {}
        api.controller = self

    def _start_camera(self, spec: str) -> None:
        """Open the camera layer one registration describes.

        Every way this can fail is a warning and no layer, never a stop: a
        controller without a camera is a missing layer, not a broken console.
        """
        try:
            calibration = load_camera_calibration(spec, site=self.site.name)
        except (ValueError, OSError) as exc:
            self.logger.warning(
                "Camera calibration not loaded, so no camera layer is served",
                camera_calibration=spec,
                error=str(exc),
            )
            return
        try:
            area = self.site.registry().resolve(calibration.area)
        except ValueError as exc:
            self.logger.warning(
                "Camera calibration names an area this site does not define, "
                "so no camera layer is served",
                path=str(calibration.path),
                area=calibration.area,
                error=str(exc),
            )
            return
        self.logger.info(
            "Camera calibration loaded",
            path=str(calibration.path),
            site=calibration.site.name,
            area=area.name,
            camera_id=calibration.id,
            residual_mm=round(calibration.residual_mm, 2),
        )
        if not self.settings.camera_detect:
            self.logger.info(
                "Camera detection disabled, so the layer is served without it",
                area=area.name,
            )
        service = CameraService(
            calibration,
            area,
            detect=self.settings.camera_detect,
            on_detection=self._on_camera_detection,
        )
        # `start()` hands the detector its first frame before it returns, so
        # the bookkeeping a detection row needs is in place first and rolled
        # back if the camera turns out not to serve.
        self.cameras.append(service)
        if self.settings.csv_data_output is not None and self.settings.camera_detect:
            self._open_camera_log(area, calibration.id)
        if not service.start():
            self.cameras.remove(service)
            rolled_back = self.camera_csv_loggers.pop(area.name, None)
            if rolled_back is not None:
                rolled_back.close()

    def _open_camera_log(self, area, camera_id: str) -> None:
        """The detection log for one camera, or a message saying why not.

        A log that cannot be appended to is an error and no log, never a
        stop, and the camera layer is served either way.
        """
        path = camera_log_path(self.settings.csv_data_output)
        try:
            self.camera_csv_loggers[area.name] = CameraCSVLogger(
                path, area=area.name, camera_id=camera_id
            )
        except (ValueError, OSError) as exc:
            self.logger.error(
                "Camera detections are not logged, but the layer is served",
                path=str(path),
                area=area.name,
                error=str(exc),
            )
            return
        self.logger.info(
            "Camera detection log enabled",
            path=str(path),
            area=area.name,
        )

    def _on_camera_detection(self, record: dict) -> None:
        """One detection, logged with the lighthouse's answer for the same floor.

        Runs on the camera's detector thread. `list(dict.values())` is atomic
        under the GIL and the model fields are reassigned whole, so the robot
        table is read without a lock.
        """
        logger = self.camera_csv_loggers.get(record.get("area", ""))
        if logger is None:
            return
        try:
            logger.log(record, self._lh2_in_area(record))
        except Exception as exc:  # pylint:disable=broad-except
            self.logger.warning(
                "Camera detection row not written",
                area=record.get("area"),
                error=str(exc),
            )

    def _lh2_in_area(self, record: dict) -> Optional[dict]:
        """The lighthouse pose of the robot the camera is looking at.

        Rectangle membership, not tracking: with more than one robot in the
        area the nearest to the detected pose is taken and `in_area` says how
        many there were, so a row that cannot mean a one-to-one comparison
        can be filtered out. `packet_age_s` ages the last packet of any kind
        from that robot, not the fix it carries.
        """
        area = next(
            (c.area for c in self.cameras if c.area.name == record.get("area")), None
        )
        if area is None:
            return None
        standing = [
            dotbot
            for dotbot in list(self.dotbots.values())
            if dotbot.lh2_position is not None
            and area.x <= dotbot.lh2_position.x <= area.x_max
            and area.y <= dotbot.lh2_position.y <= area.y_max
        ]
        if not standing:
            return {"in_area": 0}
        pose = record.get("pose") or {}
        target = pose.get("centre_mm") or area.centre
        nearest = min(
            standing,
            key=lambda d: (d.lh2_position.x - target[0]) ** 2
            + (d.lh2_position.y - target[1]) ** 2,
        )
        return {
            "address": nearest.address,
            "x": nearest.lh2_position.x,
            "y": nearest.lh2_position.y,
            "direction": nearest.direction,
            "packet_age_s": round(time.time() - nearest.last_seen, 3),
            "in_area": len(standing),
        }

    async def _camera_detections_push(self):
        """Coroutine that pushes every new camera detection to the console."""
        interval = 1.0 / WARP_FPS_MAX
        while 1:
            await asyncio.sleep(interval)
            await self._push_camera_detections()

    async def _push_camera_detections(self):
        """One notification per camera that has detected on a newer warp.

        A frame counts as pushed only once it has actually gone out, so a
        console that connects after the camera has stopped delivering is
        still told what the last frame showed.
        """
        if not self.websockets:
            return
        for camera in self.cameras:
            if not camera.live:
                continue
            record = camera.held_detection()
            if record is None:
                continue
            sequence = record["sequence"]
            if self._camera_pushed.get(camera.area.name) == sequence:
                continue
            self._camera_pushed[camera.area.name] = sequence
            await self.notify_clients(
                DotBotNotificationModel(
                    cmd=DotBotNotificationCommand.CAMERA_DETECTION,
                    camera_detection=DotBotCameraDetectionModel(**record),
                )
            )

    def _update_dotbot_twin(
        self,
        address: str,
        pwm_left: int,
        pwm_right: int,
        controller_mode: ControlModeType = ControlModeType.MANUAL,
        init_pos_x: int = 0,
        init_pos_y: int = 0,
        init_direction: int = 0,
        init_encoder_left: int = 0,
        init_encoder_right: int = 0,
    ) -> DotBotSimulator:
        """Create (if needed) and advance the kinematic twin for *address*.

        The init_* parameters are only used on first contact to seed the twin's
        initial state; subsequent calls ignore them and let the twin evolve freely.
        """
        twin = self._dotbot_twins.get(address)
        now = time.time()
        if twin is None:
            twin = DotBotSimulator(
                SimulatedDotBotSettings(
                    address=address, pos_x=init_pos_x, pos_y=init_pos_y
                ),
                queue.Queue(),
            )
            twin.direction = init_direction
            twin.encoder_left_acc = init_encoder_left
            twin.encoder_right_acc = init_encoder_right
            self._dotbot_twins[address] = twin
            self._dotbot_twin_timestamps[address] = now
        twin.pwm_left = pwm_left
        twin.pwm_right = pwm_right
        twin.controller_mode = controller_mode
        dt = now - self._dotbot_twin_timestamps[address]
        self._dotbot_twin_timestamps[address] = now
        twin.diff_drive_model_update(dt)
        twin._last_encoder_left = int(twin.encoder_left_acc)
        twin._last_encoder_right = int(twin.encoder_right_acc)
        twin.encoder_left_acc = 0.0
        twin.encoder_right_acc = 0.0
        return twin

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
        ui_path = default_ui_path()
        if ui_path is None:
            self.logger.warning("No web UI is built, not opening a browser")
            return
        url = f"http://localhost:{self.settings.controller_http_port}{ui_path}"
        self.logger.debug("Using frontend URL", url=url)
        if not self.settings.headless:
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
        source = addr_to_hex(int(frame.header.source))
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
            logger.info("New DotBot")
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
            dict_adv = dataclasses.asdict(frame.packet.payload)
            dict_adv.pop("metadata", None)
            logger.info(
                "Advertisement received", cal_hex=hex(dotbot.calibrated), **dict_adv
            )
            # Send calibration to dotbot if it's not calibrated and the localization system has calibration
            need_update = False
            is_fully_calibrated = all(
                dotbot.calibrated >> station.index & 0x01
                for station in self.lh2_calibration
            )
            if is_fully_calibrated is False and self.lh2_calibration:
                # Send calibration to new dotbot if the localization system is calibrated
                self.logger.info("Send calibration data", payload=self.lh2_calibration)
                self.dotbots.update({dotbot.address: dotbot})
                for station in self.lh2_calibration:
                    matrix_bytes = homography_as_float32(station.homography)
                    self.logger.info(
                        "Sending calibration homography",
                        index=station.index,
                        matrix=matrix_bytes,
                    )
                    payload = PayloadLh2CalibrationHomography(
                        index=station.index,
                        homography_matrix=matrix_bytes,
                    )
                    self.send_payload(int(source, 16), payload=payload)
            elif is_fully_calibrated is True:
                if frame.packet.payload.direction != 0xFFFF:
                    dotbot.direction = frame.packet.payload.direction
                new_position = DotBotLH2Position(
                    x=frame.packet.payload.pos_x,
                    y=frame.packet.payload.pos_y,
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
                    twin = self._update_dotbot_twin(
                        address=dotbot.address,
                        pwm_left=frame.packet.payload.pwm_left,
                        pwm_right=frame.packet.payload.pwm_right,
                        controller_mode=ControlModeType(frame.packet.payload.mode),
                        init_pos_x=new_position.x,
                        init_pos_y=new_position.y,
                        init_direction=dotbot.direction,
                        init_encoder_left=frame.packet.payload.encoder_left,
                        init_encoder_right=frame.packet.payload.encoder_right,
                    )
                    if self.csv_data_logger is not None:
                        real_log = CSVLog(
                            pos_x=dotbot.lh2_position.x,
                            pos_y=dotbot.lh2_position.y,
                            direction=dotbot.direction,
                            pwm_left=frame.packet.payload.pwm_left,
                            pwm_right=frame.packet.payload.pwm_right,
                            encoder_left=frame.packet.payload.encoder_left,
                            encoder_right=frame.packet.payload.encoder_right,
                        )
                        sim_log = CSVLog(
                            pos_x=int(twin.pos_x),
                            pos_y=int(twin.pos_y),
                            direction=int(twin.direction),
                            pwm_left=int(twin.pwm_left),
                            pwm_right=int(twin.pwm_right),
                            encoder_left=twin._last_encoder_left,
                            encoder_right=twin._last_encoder_right,
                        )
                        self.csv_data_logger.log(
                            real_log=real_log,
                            sim_log=sim_log,
                            control_mode=ControlModeType(
                                frame.packet.payload.mode
                            ).value,
                            waypoint_index=frame.packet.payload.waypoint_idx,
                            waypoint_x=frame.packet.payload.waypoint_x,
                            waypoint_y=frame.packet.payload.waypoint_y,
                            battery_level=dotbot.battery,
                            sim_battery_voltage=twin.battery_voltage / 1000.0,
                            address=dotbot.address,
                        )
                need_update = True

            if dotbot.battery != frame.packet.payload.battery / 1000.0:
                dotbot.battery = frame.packet.payload.battery / 1000.0  # mV to V
                need_update = True

            if dotbot.mode != ControlModeType(frame.packet.payload.mode):
                dotbot.mode = ControlModeType(frame.packet.payload.mode)
                need_update = True

            self.logger.debug(
                "Advertisement Data",
                direction=frame.packet.payload.direction,
                X=frame.packet.payload.pos_x,
                Y=frame.packet.payload.pos_x,
                battery=frame.packet.payload.battery,
            )
            if (
                need_update is True
                and notification_cmd != DotBotNotificationCommand.NEW_DOTBOT
            ):
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
            if notification_cmd != DotBotNotificationCommand.NEW_DOTBOT:
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

    def _swarmit_client(self, device: str = ""):
        """A swarmit client on the same connection the controller runs on.

        There is no fleet behind a simulator adapter, so a capture would
        stall on its first request; the simulated client answers it instead,
        which is what makes calibration mode walkable without hardware.
        """
        if self.settings.adapter in ("dotbot-simulator", "sailbot-simulator"):
            from dotbot.calibration.simulated import SimulatedCaptureClient

            return SimulatedCaptureClient(device, self._outstanding_point)
        return build_swarmit_client(
            conn_string(self.settings), self.settings.network_id
        )

    def _outstanding_point(self):
        """The frame coordinates the session is capturing, for the simulator."""
        session = self.calibration_session.session
        point = session.outstanding if session else None
        return None if point is None else point.mm

    async def _notify_calibration_session(self, state):
        """One notification per calibration-session state change."""
        await self.notify_clients(
            DotBotNotificationModel(
                cmd=DotBotNotificationCommand.CALIBRATION_SESSION_UPDATE,
                calibration_session=(
                    DotBotCalibrationSessionModel(**state) if state else None
                ),
            )
        )

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
        dest_str = addr_to_hex(destination)
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
        host = self.settings.controller_http_host
        if host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "Serving the API beyond loopback; it has no authentication, "
                "and /swarmit/* and /mrta/* reach their servers from here too",
                host=host,
            )
        config = uvicorn.Config(
            api,
            host=host,
            port=self.settings.controller_http_port,
            log_level="critical",
            # The status WebSocket stays open for as long as a browser tab is,
            # so a graceful shutdown that waits for connections never returns.
            timeout_graceful_shutdown=0,
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
                username=self.settings.mqtt_username,
                password=self.settings.mqtt_password,
            )
        elif self.settings.adapter == "dotbot-simulator":
            self.adapter = DotBotSimulatorAdapter(
                self.settings.simulator_init_state,
                self.site,
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
            if self.cameras:
                tasks.append(
                    asyncio.create_task(
                        name="Camera detections push",
                        coro=self._camera_detections_push(),
                    )
                )
            await asyncio.gather(*tasks)
        except (
            ConnectionError,
            SerialInterfaceException,
            serial.serialutil.SerialException,
        ) as exc:
            self.logger.error(f"Error: {exc}")
        except SystemExit:
            pass
        finally:
            if self.csv_data_logger is not None:
                self.csv_data_logger.close()
            # The detector threads write rows, so they stop before the file
            # they write to closes.
            for camera in self.cameras:
                camera.stop()
            for camera_logger in self.camera_csv_loggers.values():
                camera_logger.close()
            self.adapter.close()
            self.logger.info("Stopping controller")
            for task in tasks:
                self.logger.info(f"Cancelling task '{task.get_name()}'")
                task.cancel()
            self.logger.info("Controller stopped")
