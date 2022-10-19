"""Module for the web server application."""

import asyncio
import os
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bot_controller.models import DotBotModel


STATIC_FILES_DIR = os.path.join(os.path.dirname(__file__), "html")

print(STATIC_FILES_DIR)


app = FastAPI(
    debug=1,
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
    path="/controller/dotbots",
    response_model=List[DotBotModel],
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots():
    """Dotbots HTTP GET handler."""
    return list(app.controller.dotbots.values())


@app.put(
    path="/controller/dotbots/{address}",
    summary="Return the list of available dotbots",
    tags=["dotbots"],
)
async def dotbots_current(address):
    """Set the current active DotBot."""
    app.controller.header.dotbot_address = int(address, 16)
    for dotbot in app.controller.dotbots.values():
        dotbot.active = False
    if address in app.controller.dotbots:
        app.controller.dotbots[address].active = True


async def web(controller):
    """Starts the web server application."""
    app.controller = controller
    config = uvicorn.Config(app, port=8000, log_level="debug")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except asyncio.exceptions.CancelledError:
        print("Web server cancelled")
    else:
        raise SystemExit()
