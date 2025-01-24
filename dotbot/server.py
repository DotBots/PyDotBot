# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import os
from typing import List

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dotbot import pydotbot_version
from dotbot.models import (
    DotBotCalibrationStateModel,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
)
from dotbot.protocol import (
    ApplicationType,
    Frame,
    Header,
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

    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
    payload = PayloadCommandMoveRaw(
        left_x=command.left_x,
        left_y=command.left_y,
        right_x=command.right_x,
        right_y=command.right_y,
    )
    frame = Frame(header=header, payload=payload)
    api.controller.send_payload(frame)
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

    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
    payload = PayloadCommandRgbLed(
        red=command.red, green=command.green, blue=command.blue
    )
    frame = Frame(header=header, payload=payload)
    api.controller.send_payload(frame)
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

    header = Header(
        destination=int(address, 16),
        source=int(api.controller.settings.gw_address, 16),
    )
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
    frame = Frame(header, payload=payload)
    api.controller.send_payload(frame)
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


@api.post(
    path="/controller/lh2/calibration/{point_idx}",
    summary="Trigger the acquisition of one LH2 point",
    tags=["dotbots"],
)
async def controller_add_lh2_calibration_point(point_idx: int):
    """LH2 calibration, add single calibration point."""
    api.controller.lh2_manager.add_calibration_point(point_idx)


@api.put(
    path="/controller/lh2/calibration",
    summary="Trigger a computation of the LH2 calibration",
    tags=["dotbots"],
)
async def controller_apply_lh2_calibration():
    """Apply LH2 calibration."""
    api.controller.lh2_manager.compute_calibration()


@api.get(
    path="/controller/lh2/calibration",
    response_model=DotBotCalibrationStateModel,
    response_model_exclude_none=True,
    summary="Return the LH2 calibration state",
    tags=["dotbots"],
)
async def controller_get_lh2_calibration():
    """LH2 calibration GET handler."""
    return api.controller.lh2_manager.state_model


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


# Mount static files after all routes are defined
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")
api.mount("/PyDotBot", StaticFiles(directory=FRONTEND_DIR, html=True), name="PyDotBot")
