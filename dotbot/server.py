# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import base64
import os
from typing import Annotated, List

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
from dotbot.logger import LOGGER
from dotbot.models import (
    MAX_POSITION_HISTORY_SIZE,
    DotBotBackgroundMapModel,
    DotBotConnectionModel,
    DotBotMapSizeModel,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotNotificationUpdate,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
    WSMessage,
    WSMoveRaw,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.protocol import (
    ApplicationType,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLH2Waypoints,
)

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
        if api.controller.dotbots[address].lh2_position is not None:
            waypoints_list = [
                api.controller.dotbots[address].lh2_position
            ] + waypoints.waypoints
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
        )
        update_data = DotBotNotificationUpdate(
            address=address,
            lh2_waypoints=waypoints_list,
            waypoints_threshold=waypoints.threshold,
        )
    api.controller.dotbots[address].waypoints = waypoints_list
    api.controller.dotbots[address].waypoints_threshold = waypoints.threshold
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
    path="/controller/map_size",
    response_model=DotBotMapSizeModel,
    response_model_exclude_none=True,
    summary="Return the map size of the controller",
    tags=["controller"],
)
async def map_size():
    """Map size HTTP GET handler."""
    return api.controller.map_size


@api.get(
    path="/controller/connection",
    response_model=DotBotConnectionModel,
    summary="Return how the controller reaches the swarm",
    tags=["controller"],
)
async def connection():
    """Connection HTTP GET handler."""
    settings = api.controller.settings
    if settings.adapter == "cloud":
        scheme = "mqtts" if settings.mqtt_use_tls else "mqtt"
        conn = f"{scheme}://{settings.mqtt_host}:{settings.mqtt_port}"
    elif settings.adapter in ("dotbot-simulator", "sailbot-simulator"):
        conn = "simulator"
    else:
        conn = settings.port
    return DotBotConnectionModel(
        adapter=settings.adapter,
        connection=conn,
        swarm_id=settings.network_id,
        gw_address=settings.gw_address,
    )


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
    LOGGER.info(
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
