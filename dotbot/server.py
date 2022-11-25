"""Module for the web server application."""

import asyncio
import os
from binascii import hexlify
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dotbot.models import (
    DotBotCalibrationStateModel,
    DotBotModel,
    DotBotAddressModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
)
from dotbot.protocol import (
    PROTOCOL_VERSION,
    ProtocolHeader,
    ProtocolPayload,
    PayloadType,
    CommandMoveRaw,
    CommandRgbLed,
)


STATIC_FILES_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")


app = FastAPI(
    debug=0,
    title="DotBot controller API",
    description="This is the DotBot controller API",
    version="1.0.0",
    docs_url="/api",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/dotbots", StaticFiles(directory=STATIC_FILES_DIR, html=True), name="dotbots"
)


@app.get(
    path="/controller/dotbot_address",
    response_model=DotBotAddressModel,
    summary="Return the controller active dotbot address",
    tags=["controller"],
)
async def controller_dotbot_address():
    """Returns the active dotbot address."""
    return DotBotAddressModel(
        address=hexlify(
            int(app.controller.header.destination).to_bytes(8, "big")
        ).decode()
    )


@app.put(
    path="/controller/dotbot_address",
    summary="Sets the controller active dotbot address",
    tags=["controller"],
)
async def controller_dotbot_address_update(data: DotBotAddressModel):
    """Updates the active dotbot address."""
    app.controller.header.destination = int(data.address, 16)


@app.put(
    path="/controller/dotbots/{address}/move_raw",
    summary="Move the dotbot",
    tags=["dotbots"],
)
async def dotbots_move_raw(address: str, command: DotBotMoveRawCommandModel):
    """Set the current active DotBot."""
    if address not in app.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")

    header = ProtocolHeader(
        int(address, 16),
        int(app.controller.settings.gw_address, 16),
        int(app.controller.settings.swarm_id, 16),
        PROTOCOL_VERSION,
    )
    payload = ProtocolPayload(
        header,
        PayloadType.CMD_MOVE_RAW,
        CommandMoveRaw(
            command.left_x, command.left_y, command.right_x, command.right_y
        ),
    )
    app.controller.send_payload(payload)
    app.controller.dotbots[address].move_raw = command


@app.put(
    path="/controller/dotbots/{address}/rgb_led",
    summary="Set the dotbot RGB LED color",
    tags=["dotbots"],
)
async def dotbots_rgb_led(address: str, command: DotBotRgbLedCommandModel):
    """Set the current active DotBot."""
    if address not in app.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")

    header = ProtocolHeader(
        int(address, 16),
        int(app.controller.settings.gw_address, 16),
        int(app.controller.settings.swarm_id, 16),
        PROTOCOL_VERSION,
    )
    payload = ProtocolPayload(
        header,
        PayloadType.CMD_RGB_LED,
        CommandRgbLed(command.red, command.green, command.blue),
    )
    app.controller.send_payload(payload)
    app.controller.dotbots[address].rgb_led = command


@app.get(
    path="/controller/dotbots/{address}",
    response_model=DotBotModel,
    response_model_exclude_none=True,
    summary="Return information about a dotbot given its address",
    tags=["dotbots"],
)
async def dotbot(address: str):
    """Dotbot HTTP GET handler."""
    if address not in app.controller.dotbots:
        raise HTTPException(status_code=404, detail="No matching dotbot found")
    return app.controller.dotbots[address]


@app.get(
    path="/controller/dotbots",
    response_model=List[DotBotModel],
    response_model_exclude_none=True,
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots():
    """Dotbots HTTP GET handler."""
    return sorted(
        list(app.controller.dotbots.values()), key=lambda dotbot: dotbot.address
    )


@app.post(
    path="/controller/lh2/calibration/{point_idx}",
    summary="Trigger the acquisition of one LH2 point",
    tags=["dotbots"],
)
async def controller_add_lh2_calibration_point(point_idx: int):
    """LH2 calibration, add single calibration point."""
    app.controller.lh2_manager.add_calibration_point(point_idx)


@app.put(
    path="/controller/lh2/calibration",
    summary="Trigger a computation of the LH2 calibration",
    tags=["dotbots"],
)
async def controller_apply_lh2_calibration():
    """Apply LH2 calibration."""
    app.controller.lh2_manager.compute_calibration()


@app.get(
    path="/controller/lh2/calibration",
    response_model=DotBotCalibrationStateModel,
    response_model_exclude_none=True,
    summary="Return the LH2 calibration state",
    tags=["dotbots"],
)
async def controller_get_lh2_calibration():
    """LH2 calibration GET handler."""
    return app.controller.lh2_manager.state_model


@app.websocket("/controller/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket server endpoint."""
    await websocket.accept()
    app.controller.websockets.append(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in app.controller.websockets:
            app.controller.websockets.remove(websocket)


async def web(controller):
    """Starts the web server application."""
    app.controller = controller
    config = uvicorn.Config(app, port=8000, log_level="warning")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except asyncio.exceptions.CancelledError:
        print("Web server cancelled")
    else:
        raise SystemExit()
