# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import base64
import os
from typing import Annotated, Callable, Dict, List, Optional

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
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from dotbot import pydotbot_version
from dotbot.build import build_info
from dotbot.camera.service import STREAM_MEDIA_TYPE
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_TRAIL_SIZE,
    DotBotBackgroundMapModel,
    DotBotBodyModel,
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
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotLH2Waypoint,
    DotBotMaxSpeedCommandModel,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotSiteModel,
    DotBotWaypointBatches,
    DotBotWaypoints,
    DotBotWaypointsSent,
    DotBotWheelVelocityCommandModel,
    WSMessage,
    WSMoveRaw,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.poses import robot_models as robot_model_shapes
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
from dotbot.stream import StreamOptions, encode, robot_object
from dotbot.swarm_client import conn_string
from dotbot.ws_clients import TransportScope

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
    expose_headers=["X-Controller-Seq", "X-Controller-Run"],
)
api.add_middleware(ReverseProxyMiddleware)
# Last, so it is the outermost: see TransportScope.
api.add_middleware(TransportScope)


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
    api.controller.update_dotbot(address, move_raw=command)


@api.put(
    path="/controller/dotbots/{address}/{application}/wheel_velocity",
    summary="Set the speed of each wheel, in mm/s",
    tags=["dotbots"],
)
async def dotbots_wheel_velocity(
    address: str, application: int, command: DotBotWheelVelocityCommandModel
):
    """Hand the DotBot's wheel speeds to its onboard wheel loop.

    Only the sandbox dotbot firmware app acts on this command; other apps
    accept the frame and ignore it. It stops the wheels about 500 ms after
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

    Only the sandbox dotbot firmware app acts on this command, and clamps
    the value to 20 to 700 mm/s.
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
    api.controller.update_dotbot(address, rgb_led=command)


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
    _check_waypoints(address, application, waypoints.waypoints)
    if not await _dotbots_waypoints(
        address=address, application=application, waypoints=waypoints
    ):
        raise HTTPException(
            status_code=500,
            detail=f"{address}: waypoints not sent, see the controller log",
        )


# PayloadLH2Location carries each coordinate as an unsigned 32-bit mm count
WAYPOINT_MAX_MM = 0xFFFFFFFF


def _check_waypoints(address: str, application: int, waypoints) -> None:
    """Raises 422 unless every point is of the kind `application` drives
    to (latitude/longitude for a SailBot, x/y for a DotBot) and every x/y
    point lies inside the site, or on the wire's range without a site extent."""
    kind = (
        DotBotGPSPosition
        if application == ApplicationType.SailBot.value
        else DotBotLH2Waypoint
    )
    if not all(isinstance(waypoint, kind) for waypoint in waypoints):
        wanted = "latitude/longitude" if kind is DotBotGPSPosition else "x/y"
        raise HTTPException(
            status_code=422, detail=f"{address}: waypoints must be {wanted} points"
        )
    if kind is not DotBotLH2Waypoint:
        return
    site = api.controller.settings.site
    extent = site.extent_mm if site is not None else None
    width, height = extent or (WAYPOINT_MAX_MM, WAYPOINT_MAX_MM)
    for waypoint in waypoints:
        if 0 <= waypoint.x <= width and 0 <= waypoint.y <= height:
            continue
        where = f"{address}: waypoint ({waypoint.x:g}, {waypoint.y:g}) mm"
        if extent is not None:
            detail = (
                f"{where} is outside site '{site.name}', "
                f"0 to {width} x 0 to {height} mm"
            )
        else:
            detail = f"{where} cannot be sent: x and y must be 0 to {width} mm"
        raise HTTPException(status_code=422, detail=detail)


def _split_known(addresses: List[str], strict: bool) -> List[str]:
    """The addresses the controller knows, in request order.

    Raises 404 when `strict` and any address is unknown, or when addresses
    were named and none of them is known.
    """
    known = [a for a in addresses if a in api.controller.dotbots]
    unknown = [a for a in addresses if a not in api.controller.dotbots]
    if unknown and (strict or not known):
        raise HTTPException(
            status_code=404, detail=f"No matching dotbot found: {', '.join(unknown)}"
        )
    return known


@api.put(
    path="/controller/dotbots/waypoints",
    summary="Set the waypoints of several DotBots at once",
    tags=["dotbots"],
)
async def dotbots_waypoint_batches(
    batches: DotBotWaypointBatches,
    strict: bool = False,
) -> DotBotWaypointsSent:
    """Give each DotBot its own batch, keyed by address, under one set of
    settings: the same as one PUT per robot on its own waypoints route.

    ::

        {"threshold": 60,
         "dotbots": {"badcafe111111111": [{"x": 400, "y": 1600}],
                     "deadbeef22222222": [{"x": 1600, "y": 400}]}}

    Every known DotBot gets its batch and unknown addresses are listed in
    ``unknown``. With ``?strict=true`` an unknown address refuses the whole
    request, before anything is sent. When no address is known: 404. A batch
    whose points are not of the kind its robot drives to (x/y for a DotBot,
    latitude/longitude for a SailBot) refuses the whole request: 422.
    """
    addresses = list(batches.dotbots)
    known = _split_known(addresses, strict)
    for address in known:
        _check_waypoints(
            address,
            api.controller.dotbots[address].application.value,
            batches.dotbots[address],
        )
    return await _send_each(addresses, known, batches.batch)


@api.delete(
    path="/controller/dotbots/waypoints",
    summary="Clear the waypoints of several DotBots, or of all of them",
    tags=["dotbots"],
)
async def dotbots_waypoints_clear(
    address: Annotated[Optional[List[str]], Query()] = None,
    strict: bool = False,
) -> DotBotWaypointsSent:
    """Stop the DotBots named by `?address=` (repeat it for several), or every
    known DotBot without it, keeping only where each one stood.

    Unknown addresses are listed in `unknown` and the rest are stopped. With
    `?strict=true` an unknown address refuses the whole request, before
    anything is sent. When no named address is known: 404.
    """
    if address is None:
        addresses = list(api.controller.dotbots)
    else:
        addresses = list(dict.fromkeys(address))
    known = _split_known(addresses, strict)
    return await _send_each(
        addresses,
        known,
        lambda each: DotBotWaypoints(
            threshold=api.controller.dotbots[each].waypoints_threshold or 0,
            waypoints=[],
        ),
    )


async def _send_each(
    addresses: List[str],
    known: List[str],
    batch_of: Callable[[str], DotBotWaypoints],
) -> DotBotWaypointsSent:
    """Send each known robot its `batch_of(address)`, and report the outcome."""
    sent = [
        address
        for address in known
        if await _dotbots_waypoints(
            address=address,
            application=api.controller.dotbots[address].application.value,
            waypoints=batch_of(address),
        )
    ]
    return DotBotWaypointsSent(
        applied=sent,
        unknown=[a for a in addresses if a not in known],
        failed=[a for a in known if a not in sent],
    )


def _axle_position(dotbot: DotBotModel) -> Optional[DotBotLH2Position]:
    """Where the robot's centre is: its own estimate, else the body pose
    expanded from its fix."""
    if dotbot.axle_position is not None:
        return dotbot.axle_position
    if dotbot.pose is not None and dotbot.pose.heading_source != "none":
        return DotBotLH2Position(x=dotbot.pose.x, y=dotbot.pose.y)
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
) -> bool:
    """Send a validated batch; False when it was not sent, and the robot's
    waypoints are then left as they were."""
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
    if isinstance(payload, PayloadLH2Waypoints):
        sent = api.controller.send_waypoints(address, payload)
    else:
        sent = api.controller.send_payload(int(address, 16), payload)
    if not sent:
        return False
    api.controller.update_dotbot(
        address, waypoints=waypoints_list, waypoints_threshold=waypoints.threshold
    )
    return True


@api.delete(
    path="/controller/dotbots/{address}/positions",
    summary="Clear the trail of a DotBot",
    tags=["dotbots"],
)
async def dotbot_trail_clear(address: str):
    """Clear the trail of a dotbot."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    api.controller.clear_trail(address)


def _snapshot(body, resumable: bool = False) -> Response:
    """A REST response of `body`, JSON built from the stream's cached dumps.

    A `resumable` one carries the seq and run it reflects, which a stream
    client resumes from with `?since=&run=`.
    """
    headers = {}
    if resumable:
        headers = {
            "X-Controller-Seq": str(api.controller.seq),
            "X-Controller-Run": api.controller.run_id,
        }
    return Response(
        content=encode(body), media_type="application/json", headers=headers
    )


_QUERY_FILTERS = set(DotBotQueryModel.model_fields) - {"trail", "body"}


@api.get(
    path="/controller/dotbots/{address}",
    response_model=DotBotModel,
    response_model_exclude_none=True,
    summary="Return information about a dotbot given its address",
    tags=["dotbots"],
)
async def dotbot(
    address: str,
    trail: Annotated[int, Query(ge=0, le=MAX_TRAIL_SIZE)] = 0,
    body: bool = False,
):
    """Dotbot HTTP GET handler; `trail` is how many of its newest trail
    points to return, and `body` adds the body its pose places."""
    controller = api.controller
    if address not in controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    return _snapshot(
        robot_object(controller, address, trail, controller.seq, body=body)
    )


@api.get(
    path="/controller/dotbots",
    response_model=List[DotBotModel],
    response_model_exclude_none=True,
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots(query: Annotated[DotBotQueryModel, Query()]):
    """Dotbots HTTP GET handler. Only the unfiltered list carries
    `X-Controller-Seq` and `X-Controller-Run`."""
    controller = api.controller
    return _snapshot(
        [
            robot_object(
                controller, address, query.trail, controller.seq, body=query.body
            )
            for address in controller.matching(query)
        ],
        resumable=all(getattr(query, name) is None for name in _QUERY_FILTERS),
    )


@api.get(
    path="/controller/robot_models",
    response_model=Dict[str, DotBotBodyModel],
    summary="Return each robot model's body, axle at the origin, facing 0 degrees",
    tags=["controller"],
)
async def robot_models():
    """Robot models HTTP GET handler; the stream's `robot_models` event."""
    return robot_model_shapes()


@api.get(
    path="/controller/device_poses",
    response_model=Dict[str, DotBotBodyModel],
    summary="Return the headingless pose of each swarmit device type, at the origin",
    tags=["controller"],
)
async def device_poses():
    """Device poses HTTP GET handler."""
    return api.controller.device_poses()


@api.get(
    path="/controller/site",
    response_model=DotBotSiteModel,
    summary="Return the site the controller works in, its areas and calibrated span",
    tags=["controller"],
)
async def site():
    """Active site HTTP GET handler."""
    return DotBotSiteModel.from_site(api.controller.site, api.controller.calibration)


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
    points = request.points
    specs = ([points] if points else []) if isinstance(points, str) else list(points)
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


@api.websocket("/controller/ws/stream")
async def controller_stream(websocket: WebSocket):
    """The controller stream: `hello`, a `snapshot`, then `delta` and
    `event` frames, each answered with `{"ack": seq}`.

    Query: `hz` (1-20, default 10; 1 until the first ack), `trail` (points
    per robot, default 0), and `since` with `run` to resume from a seq.
    """
    hub = api.controller.stream
    options = StreamOptions.from_query(websocket.query_params)
    await websocket.accept()
    client = hub.client(websocket, options)
    try:
        await websocket.send_text(hub.hello(client))
        hub.add(client)
        while True:
            hub.receive(websocket, await websocket.receive_text())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.remove(websocket)


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
                try:
                    _check_waypoints(msg.address, msg.application, msg.data.waypoints)
                except HTTPException as exc:
                    await websocket.send_json(
                        {"error": "invalid_message", "details": exc.detail}
                    )
                    continue
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
    if api.controller.settings.swarmit_url is None:
        return Response(status_code=404, content=b"no swarmit server configured")
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


# The MRTA mode server (dotbot-logistics) is opt-in: with no `mrta_url` this
# route answers 404, as `/swarmit/*` does with no swarmit server; the console
# hides its MRTA control on that 404. /mrta/* is small JSON, so a short
# timeout and no streaming.
MRTA_PROXY_TIMEOUT = httpx.Timeout(5.0)


@api.api_route(
    path="/mrta/{path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def mrta_proxy(path: str, request: Request):
    """Forward /mrta/* to the configured MRTA mode server (same-origin for
    the web console, exactly like ``/swarmit/*``). The /mrta prefix is dropped."""
    if api.controller.settings.mrta_url is None:
        return Response(status_code=404, content=b"no MRTA server configured")
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


async def root():
    """Send a browser landing on the bare host to the console."""
    return RedirectResponse(url="/console/")


# The console is the web UI. Mounted after all routes so they take precedence.
CONSOLE_DIR = os.path.join(os.path.dirname(__file__), "console-web", "dist")


def mount_console(app: FastAPI, directory: str) -> bool:
    """Serve the console built in `directory` at /console, and redirect / to
    it; neither route exists without the build. False if it is missing."""
    if not os.path.isdir(directory):
        return False
    app.mount("/console", StaticFiles(directory=directory, html=True), name="console")
    app.add_api_route("/", root, include_in_schema=False)
    return True


if not mount_console(api, CONSOLE_DIR):
    LOGGER.warning(
        "Console build not found at %s; /console will be unavailable. "
        "Build it with: cd dotbot/console-web && npm install && npm run build",
        CONSOLE_DIR,
    )


def default_ui_path() -> str | None:
    """Path the controller opens on start, or None when no UI is built."""
    if os.path.isdir(CONSOLE_DIR):
        return "/console"
    return None
