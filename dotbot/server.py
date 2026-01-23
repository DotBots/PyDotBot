# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import os
from typing import List

import httpx
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from dotbot import pydotbot_version
from dotbot.logger import LOGGER
from dotbot.models import (
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
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

    _dotbots_rgb_led(address=address, command=command)


def _dotbots_rgb_led(address: str, command: DotBotRgbLedCommandModel):
    payload = PayloadCommandRgbLed(
        red=command.red, green=command.green, blue=command.blue
    )
    api.controller.send_payload(int(address, 16), payload)
    api.controller.dotbots[address].rgb_led = command


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
                    pos_x=int(waypoint.x * 1e6),
                    pos_y=int(waypoint.y * 1e6),
                    pos_z=int(waypoint.z * 1e6),
                )
                for waypoint in waypoints.waypoints
            ],
        )
    api.controller.dotbots[address].waypoints = waypoints_list
    api.controller.dotbots[address].waypoints_threshold = waypoints.threshold
    api.controller.send_payload(int(address, 16), payload)
    await api.controller.notify_clients(
        DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD)
    )


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


@api.get(
    path="/controller/dotbots/{address}",
    response_model=DotBotModel,
    response_model_exclude_none=True,
    summary="Return information about a dotbot given its address",
    tags=["dotbots"],
)
async def dotbot(address: str, query: DotBotQueryModel = Depends()):
    """Dotbot HTTP GET handler."""
    if address not in api.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    _dotbot = DotBotModel(**api.controller.dotbots[address].model_dump())
    _dotbot.position_history = _dotbot.position_history[: query.max_positions]
    return _dotbot


@api.get(
    path="/controller/dotbots",
    response_model=List[DotBotModel],
    response_model_exclude_none=True,
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots(query: DotBotQueryModel = Depends()):
    """Dotbots HTTP GET handler."""
    return api.controller.get_dotbots(query)


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
                _dotbots_rgb_led(
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


# Mount static files after all routes are defined
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")
api.mount("/PyDotBot", StaticFiles(directory=FRONTEND_DIR, html=True), name="PyDotBot")
