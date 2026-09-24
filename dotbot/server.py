# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import base64
import os
from typing import Annotated, Dict, List, Optional

import httpx
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from dotbot import pydotbot_version
from dotbot.build import build_info
from dotbot.camera.service import STREAM_MEDIA_TYPE
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotAreaModel,
    DotBotBackgroundMapModel,
    DotBotBuildModel,
    DotBotCalibrationCaptureModel,
    DotBotCalibrationPreviewModel,
    DotBotCalibrationPushedModel,
    DotBotCalibrationPushModel,
    DotBotCalibrationSavedModel,
    DotBotCalibrationSaveModel,
    DotBotCalibrationSessionModel,
    DotBotCalibrationStartModel,
    DotBotCameraDetectionModel,
    DotBotCameraModel,
    DotBotConnectionModel,
    DotBotLH2Position,
    DotBotMaxSpeedCommandModel,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotPoseModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotSiteModel,
    DotBotWaypoints,
    DotBotWheelVelocityCommandModel,
    WSMessage,
    WSMoveRaw,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.protocol import (
    WAYPOINT_NO_HEADING,
    ApplicationType,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadCommandWheelVelocity,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLH2Waypoints,
    PayloadWaypointHeading,
)
from dotbot.swarm_client import conn_string

PYDOTBOT_FRONTEND_BASE_URL = os.getenv(
    "PYDOTBOT_FRONTEND_BASE_URL", "https://dotbots.github.io/PyDotBot"
)

ws_adapter = TypeAdapter(WSMessage)


class ReverseProxyMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/pin"):
            headers = {k: v for k, v in request.headers.items()}
            url = f"http://localhost:8080{request.url.path}"

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        url,
                        headers=headers,
                    )
                except httpx.ConnectError as exc:
                    LOGGER.warning(exc)
                    return Response(status_code=502, content=b"Proxy connection failed")

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response.headers,
                )

        response = await call_next(request)
        return response


api = FastAPI(
    debug=0,
    title="DotBot controller API",
    description="This is the DotBot controller API",
    version=pydotbot_version(),
    docs_url="/api",
    redoc_url=None,
)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api.add_middleware(ReverseProxyMiddleware)


@api.put(
    path="/controller/dotbots/{address}/{application}/move_raw",
    summary="Move the dotbot",
    tags=["dotbots"],
)
async def dotbots_move_raw(
    address: str, application: int, command: DotBotMoveRawCommandModel
):
    """Set the current active DotBot."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")

    _dotbots_move_raw(address=address, command=command)


def _dotbots_move_raw(address: str, command: DotBotMoveRawCommandModel):
    payload = PayloadCommandMoveRaw(
        left_x=command.left_x,
        left_y=command.left_y,
        right_x=command.right_x,
        right_y=command.right_y,
    )
    api.controller.send_payload(int(address, 16), payload)
    api.controller.dotbots[address].move_raw = command


@api.put(
    path="/controller/dotbots/{address}/{application}/wheel_velocity",
    summary="Set the speed of each wheel, in mm/s",
    tags=["dotbots"],
)
async def dotbots_wheel_velocity(
    address: str, application: int, command: DotBotWheelVelocityCommandModel
):
    """Hand the DotBot's wheel speeds to its onboard wheel loop.

    Only the dotbot-next firmware app acts on this command; other apps accept
    the frame and ignore it. dotbot-next stops the wheels about 500 ms after
    the last command, so a caller must resend faster than 2 Hz.
    """
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    api.controller.send_payload(
        int(address, 16),
        PayloadCommandWheelVelocity(
            left_mm_s=command.left_mm_s, right_mm_s=command.right_mm_s
        ),
    )


@api.put(
    path="/controller/dotbots/{address}/{application}/max_speed",
    summary="Set the cruise speed limit of waypoint moves, in mm/s",
    tags=["dotbots"],
)
async def dotbots_max_speed(
    address: str, application: int, command: DotBotMaxSpeedCommandModel
):
    """Set the fastest a DotBot drives between waypoints, until the next
    change or a reset; 0 restores the firmware's default.

    Only the dotbot-next firmware app acts on this command, and clamps the
    value to 20 to 700 mm/s.
    """
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    api.controller.send_max_speed(address, command.max_speed_mm_s)


@api.put(
    path="/controller/dotbots/{address}/{application}/rgb_led",
    summary="Set the dotbot RGB LED color",
    tags=["dotbots"],
)
async def dotbots_rgb_led(
    address: str, application: int, command: DotBotRgbLedCommandModel
):
    """Set the current active DotBot."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    await _dotbots_rgb_led(address=address, command=command)


async def _dotbots_rgb_led(address: str, command: DotBotRgbLedCommandModel):
    payload = PayloadCommandRgbLed(
        red=command.red, green=command.green, blue=command.blue
    )
    api.controller.send_payload(int(address, 16), payload)
    api.controller.dotbots[address].rgb_led = command
    notification = DotBotNotificationModel(
        cmd=DotBotNotificationCommand.UPDATE,
        data=DotBotNotificationUpdate(address=address, rgb_led=command),
    )
    await api.controller.notify_clients(notification)


@api.put(
    path="/controller/dotbots/{address}/{application}/waypoints",
    summary="Set the dotbot control mode",
    tags=["dotbots"],
)
async def dotbots_waypoints(
    address: str,
    application: int,
    waypoints: DotBotWaypoints,
):
    """Set the waypoints of a DotBot."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")

    await _dotbots_waypoints(
        address=address, application=application, waypoints=waypoints
    )


def _axle_position(dotbot: DotBotModel) -> Optional[DotBotLH2Position]:
    """Where the robot's centre is: its own estimate, else the body pose
    expanded from its fix."""
    if dotbot.axle_position is not None:
        return dotbot.axle_position
    if dotbot.pose is not None:
        return dotbot.pose.axle
    return dotbot.lh2_position


def _heading_cdeg(waypoint) -> int:
    """A waypoint's heading on the wire: centidegrees in [-18000, 18000)."""
    heading = getattr(waypoint, "heading_deg", None)
    if heading is None:
        return WAYPOINT_NO_HEADING
    cdeg = round(heading * 100) % 36000
    return cdeg - 36000 if cdeg >= 18000 else cdeg


async def _dotbots_waypoints(
    address: str,
    application: int,
    waypoints: DotBotWaypoints,
):
    waypoints_list = waypoints.waypoints
    if application == ApplicationType.SailBot.value:
        if api.controller.dotbots[address].gps_position is not None:
            waypoints_list = [
                api.controller.dotbots[address].gps_position
            ] + waypoints.waypoints
        payload = PayloadGPSWaypoints(
            threshold=waypoints.threshold,
            count=len(waypoints.waypoints),
            waypoints=[
                PayloadGPSPosition(
                    latitude=int(waypoint.latitude * 1e6),
                    longitude=int(waypoint.longitude * 1e6),
                )
                for waypoint in waypoints.waypoints
            ],
        )
        update_data = DotBotNotificationUpdate(
            address=address,
            gps_waypoints=waypoints_list,
            waypoints_threshold=waypoints.threshold,
        )
    else:  # DotBot application
        start = _axle_position(api.controller.dotbots[address])
        if start is not None:
            waypoints_list = [start] + waypoints.waypoints
        payload = PayloadLH2Waypoints(
            threshold=waypoints.threshold,
            count=len(waypoints.waypoints),
            waypoints=[
                PayloadLH2Location(
                    pos_x=int(waypoint.x),
                    pos_y=int(waypoint.y),
                )
                for waypoint in waypoints.waypoints
            ],
            heading_tol_deg=waypoints.heading_tolerance or 0,
            pass_mm=waypoints.intermediate_threshold or 0,
            headings=[
                PayloadWaypointHeading(heading_cdeg=_heading_cdeg(waypoint))
                for waypoint in waypoints.waypoints
            ],
        )
        update_data = DotBotNotificationUpdate(
            address=address,
            lh2_waypoints=waypoints_list,
            waypoints_threshold=waypoints.threshold,
        )
    api.controller.dotbots[address].waypoints = waypoints_list
    api.controller.dotbots[address].waypoints_threshold = waypoints.threshold
    if isinstance(payload, PayloadLH2Waypoints):
        api.controller.send_waypoints(address, payload)
    else:
        api.controller.send_payload(int(address, 16), payload)
    notification = DotBotNotificationModel(
        cmd=DotBotNotificationCommand.UPDATE, data=update_data
    )
    await api.controller.notify_clients(notification)


@api.delete(
    path="/controller/dotbots/{address}/positions",
    summary="Clear the history of positions of a DotBot",
    tags=["dotbots"],
)
async def dotbot_positions_history_clear(address: str):
    """Clear the history of positions of a dotbot."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    api.controller.dotbots[address].position_history = []
    await api.controller.notify_clients(
        DotBotNotificationModel(
            cmd=DotBotNotificationCommand.UPDATE,
            data=DotBotNotificationUpdate(address=address, position_history=[]),
        )
    )


@api.get(
    path="/controller/dotbots/{address}",
    response_model=DotBotModel,
    response_model_exclude_none=True,
    summary="Return information about a dotbot given its address",
    tags=["dotbots"],
)
async def dotbot(address: str, max_positions: int = MAX_POSITION_HISTORY_SIZE):
    """Dotbot HTTP GET handler."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    _dotbot = DotBotModel(**api.controller.dotbots[address].model_dump())
    _dotbot.position_history = _dotbot.position_history[:max_positions]
    return _dotbot


@api.get(
    path="/controller/dotbots",
    response_model=List[DotBotModel],
    response_model_exclude_none=True,
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots(query: Annotated[DotBotQueryModel, Query()]):
    """Dotbots HTTP GET handler."""
    return api.controller.get_dotbots(query)


@api.get(
    path="/controller/device_poses",
    response_model=Dict[str, DotBotPoseModel],
    summary="Return the headingless pose of each swarmit device type, at the origin",
    tags=["controller"],
)
async def device_poses():
    """Device poses HTTP GET handler."""
    return api.controller.device_poses()


@api.get(
    path="/controller/site",
    response_model=DotBotSiteModel,
    summary="Return the site the controller works in, with its areas",
    tags=["controller"],
)
async def site():
    """Active site HTTP GET handler."""
    current = api.controller.site
    return DotBotSiteModel(
        name=current.name,
        anchor=current.anchor,
        extent_mm=list(current.extent_mm) if current.extent_mm else None,
        areas=[
            DotBotAreaModel(**a.as_dict())
            for a in sorted(current.areas.values(), key=lambda a: a.name)
        ],
    )


@api.get(
    path="/controller/cameras",
    response_model=List[DotBotCameraModel],
    summary="Return the cameras the controller warps into the map",
    tags=["controller"],
)
async def cameras():
    """Cameras HTTP GET handler."""
    return [
        DotBotCameraModel(**camera.descriptor())
        for camera in api.controller.cameras
        if camera.live
    ]


@api.get(
    path="/controller/cameras/{area}/detection",
    response_model=Optional[DotBotCameraDetectionModel],
    summary="Return the latest detection of the camera covering one area",
    tags=["controller"],
)
async def camera_detection(area: str):
    """Camera detection HTTP GET handler; null before the first detection."""
    for camera in api.controller.cameras:
        if camera.live and camera.area.name == area:
            record = camera.held_detection()
            return None if record is None else DotBotCameraDetectionModel(**record)
    raise HTTPException(status_code=404, detail=f"No camera covers area {area!r}")


@api.get(
    path="/controller/cameras/{area}/stream",
    response_class=StreamingResponse,
    summary="Stream the camera covering one area, warped into its raster",
    tags=["controller"],
)
async def camera_stream(area: str):
    """Camera stream HTTP GET handler."""
    for camera in api.controller.cameras:
        if camera.live and camera.area.name == area:
            return StreamingResponse(camera.parts(), media_type=STREAM_MEDIA_TYPE)
    raise HTTPException(status_code=404, detail=f"No camera covers area {area!r}")


@api.post(
    path="/controller/calibration/session",
    response_model=DotBotCalibrationSessionModel,
    summary="Open a calibration session over a set of resolved points",
    tags=["calibration"],
)
async def calibration_session_start(request: DotBotCalibrationStartModel):
    """Calibration-session HTTP POST handler."""
    specs = (
        [request.points] if isinstance(request.points, str) else list(request.points)
    )
    return await _calibration(
        api.controller.calibration_session.start(
            specs, request.device, request.area, request.reads
        )
    )


@api.get(
    path="/controller/calibration/session/preview",
    response_model=DotBotCalibrationPreviewModel,
    summary="Resolve a set of points without opening a session over them",
    tags=["calibration"],
)
async def calibration_session_preview(points: Annotated[List[str], Query()]):
    """Calibration-preview HTTP GET handler."""
    try:
        return api.controller.calibration_session.preview(points)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.get(
    path="/controller/calibration/session/state",
    response_model=Optional[DotBotCalibrationSessionModel],
    summary="Return the calibration session, or null when there is none",
    tags=["calibration"],
)
async def calibration_session_state():
    """Calibration-session state HTTP GET handler."""
    return api.controller.calibration_session.state()


@api.post(
    path="/controller/calibration/session/capture",
    response_model=DotBotCalibrationSessionModel,
    summary="Capture the outstanding point from one robot",
    tags=["calibration"],
)
async def calibration_session_capture(request: DotBotCalibrationCaptureModel):
    """Calibration-capture HTTP POST handler."""
    return await _calibration(
        api.controller.calibration_session.capture(request.device)
    )


@api.post(
    path="/controller/calibration/session/redo",
    response_model=DotBotCalibrationSessionModel,
    summary="Discard the last captured point's reads and re-open it",
    tags=["calibration"],
)
async def calibration_session_redo():
    """Calibration-redo HTTP POST handler."""
    return await _calibration(api.controller.calibration_session.redo())


@api.post(
    path="/controller/calibration/session/save",
    response_model=DotBotCalibrationSavedModel,
    summary="Solve the session and write its schema 2 calibration file",
    tags=["calibration"],
)
async def calibration_session_save(request: DotBotCalibrationSaveModel):
    """Calibration-save HTTP POST handler."""
    return await _calibration(api.controller.calibration_session.save(request.tag))


@api.post(
    path="/controller/calibration/session/push",
    response_model=DotBotCalibrationPushedModel,
    summary="Send the saved calibration to the robots over the air",
    tags=["calibration"],
)
async def calibration_session_push(
    request: Optional[DotBotCalibrationPushModel] = None,
):
    """Calibration-push HTTP POST handler."""
    devices = request.devices if request else []
    return await _calibration(api.controller.calibration_session.push(devices=devices))


@api.delete(
    path="/controller/calibration/session",
    summary="Abandon the calibration session without writing anything",
    tags=["calibration"],
)
async def calibration_session_abandon():
    """Calibration-session HTTP DELETE handler."""
    return await api.controller.calibration_session.abandon()


async def _calibration(awaitable):
    """Turn a session's refusals into a status a client can render as a line."""
    from dotbot.calibration.session import SessionError

    try:
        return await awaitable
    except SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.get(
    path="/controller/connection",
    response_model=DotBotConnectionModel,
    summary="Return how the controller reaches the swarm",
    tags=["controller"],
)
async def connection():
    """Connection HTTP GET handler."""
    settings = api.controller.settings
    return DotBotConnectionModel(
        adapter=settings.adapter,
        connection=conn_string(settings),
        swarm_id=settings.network_id,
        gw_address=settings.gw_address,
    )


@api.get(
    path="/controller/build",
    response_model=DotBotBuildModel,
    response_model_exclude_none=True,
    summary="Return the build of pydotbot the controller runs",
    tags=["controller"],
)
async def build():
    """Build HTTP GET handler."""
    return DotBotBuildModel(**build_info())


@api.get(
    path="/controller/background_map",
    response_model=DotBotBackgroundMapModel,
    summary="Return the background map of the controller",
    tags=["controller"],
)
async def background_map():
    """Background map HTTP GET handler."""
    if not api.controller.settings.background_map:
        return DotBotBackgroundMapModel(data="")
    with open(api.controller.settings.background_map, "rb") as f:
        encoded_string = base64.b64encode(f.read()).decode("utf-8")
    return DotBotBackgroundMapModel(data=encoded_string)


@api.websocket("/controller/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket server endpoint."""
    await websocket.accept()
    api.controller.websockets.append(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in api.controller.websockets:
            api.controller.websockets.remove(websocket)


@api.websocket("/controller/ws/dotbots")
async def ws_dotbots(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_json()

            try:
                msg = ws_adapter.validate_python(raw)
            except ValidationError as e:
                await websocket.send_json(
                    {
                        "error": "invalid_message",
                        "details": e.errors(),
                    }
                )
                continue

            if msg.address not in api.controller.dotbots:
                # ignore messages where address doesn't exist
                continue

            if isinstance(msg, WSRgbLed):
                await _dotbots_rgb_led(
                    address=msg.address,
                    command=msg.data,
                )
            elif isinstance(msg, WSMoveRaw):
                _dotbots_move_raw(
                    address=msg.address,
                    command=msg.data,
                )
            elif isinstance(msg, WSWaypoints):
                await _dotbots_waypoints(
                    address=msg.address,
                    application=msg.application,
                    waypoints=msg.data,
                )

    except WebSocketDisconnect:
        LOGGER.debug("WebSocket client disconnected")


# Timeouts for the swarmit proxy: fail fast when the server is down, but
# never time out reads - /events and /flash/stream are long-lived SSE.
SWARMIT_PROXY_TIMEOUT = httpx.Timeout(5.0, read=None)


@api.api_route(
    path="/swarmit/{path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def swarmit_proxy(path: str, request: Request):
    """Forward /swarmit/* to the configured swarmit server (same-origin for
    the web console; the streaming body keeps SSE responses live)."""
    base = api.controller.settings.swarmit_url.rstrip("/")
    client = httpx.AsyncClient(timeout=SWARMIT_PROXY_TIMEOUT)
    upstream_request = client.build_request(
        method=request.method,
        url=f"{base}/{path}",
        params=request.query_params,
        headers={
            k: v
            for k, v in request.headers.items()
            if k.lower() in ("content-type", "accept")
        },
        content=await request.body(),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        LOGGER.debug("swarmit server unreachable", url=f"{base}/{path}", error=str(exc))
        return Response(status_code=502, content=b"swarmit server unreachable")

    async def cleanup():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() in ("content-type", "cache-control")
        },
        background=BackgroundTask(cleanup),
    )


# The MRTA mode server (dotbot-logistics) is optional and usually absent, so
# a plain short timeout: the console reads any failure - a 404 on a
# controller without this route, a 502 here, a timeout - as "MRTA N/A". No
# streaming: /mrta/status and /mrta/mode are small JSON.
MRTA_PROXY_TIMEOUT = httpx.Timeout(5.0)


@api.api_route(
    path="/mrta/{path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def mrta_proxy(path: str, request: Request):
    """Forward /mrta/* to the configured MRTA mode server (same-origin for
    the web console, exactly like ``/swarmit/*``). The /mrta prefix is dropped."""
    base = api.controller.settings.mrta_url.rstrip("/")
    async with httpx.AsyncClient(timeout=MRTA_PROXY_TIMEOUT) as client:
        try:
            upstream = await client.request(
                method=request.method,
                url=f"{base}/{path}",
                params=request.query_params,
                headers={
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() in ("content-type", "accept")
                },
                content=await request.body(),
            )
        except httpx.HTTPError as exc:
            LOGGER.debug(
                "MRTA server unreachable", url=f"{base}/{path}", error=str(exc)
            )
            return Response(status_code=502, content=b"MRTA mode server unreachable")
    return Response(
        status_code=upstream.status_code,
        content=upstream.content,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() in ("content-type", "cache-control")
        },
    )


# Mount static files after all routes are defined
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")
if os.path.isdir(FRONTEND_DIR):
    api.mount(
        "/PyDotBot", StaticFiles(directory=FRONTEND_DIR, html=True), name="PyDotBot"
    )
else:
    LOGGER.warning(
        "Frontend build not found at %s; the web UI will be unavailable. "
        "Install the published wheel (pip install --pre pydotbot) or build the "
        "frontend: cd dotbot/frontend && npm install && npm run build",
        FRONTEND_DIR,
    )

# The unified console (map-first PyDotBot + swarmit UI). This is the UI the
# controller opens; the classic frontend stays mounted at /PyDotBot, which is
# where the qrkey demo, the REST demo and the SailBot views live.
CONSOLE_DIR = os.path.join(os.path.dirname(__file__), "console-web", "dist")
if os.path.isdir(CONSOLE_DIR):
    api.mount("/console", StaticFiles(directory=CONSOLE_DIR, html=True), name="console")
else:
    LOGGER.warning(
        "Console build not found at %s; /console will be unavailable. "
        "Build it with: cd dotbot/console-web && npm install && npm run build",
        CONSOLE_DIR,
    )


def default_ui_path() -> str | None:
    """Path the controller opens on start, or None when no UI is built."""
    if os.path.isdir(CONSOLE_DIR):
        return "/console"
    if os.path.isdir(FRONTEND_DIR):
        return "/PyDotBot"
    return None
