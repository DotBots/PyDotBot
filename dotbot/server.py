# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for the web server application."""

import asyncio
import math
import os
from typing import Dict, List

import httpx
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from dotbot import pydotbot_version
from dotbot.logger import LOGGER
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
)
from dotbot.orca import Agent, OrcaParams, compute_orca_velocity_for_agent
from dotbot.protocol import (
    ApplicationType,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLH2Waypoints,
)
from dotbot.vec2 import Vec2

PYDOTBOT_FRONTEND_BASE_URL = os.getenv(
    "PYDOTBOT_FRONTEND_BASE_URL", "https://dotbots.github.io/PyDotBot"
)

THRESHOLD = 30  # acceptable distance from the waypoint


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


async def compute_orca_velocity(
    agent: Agent,
    neighbors: List[Agent],
    params: OrcaParams,
) -> Vec2:
    return compute_orca_velocity_for_agent(agent, neighbors, params)


@api.post(
    path="/controller/dotbots/run_algorithm",
)
async def run_algorithm(
    params: OrcaParams,
) -> Vec2:
    query = DotBotQueryModel(
        application=ApplicationType.DotBot, status=DotBotStatus.ACTIVE
    )
    dotbots: List[DotBotModel] = api.controller.get_dotbots(query)

    # Cosmetic: all bots are red
    for dotbot in dotbots:
        await dotbots_rgb_led(
            dotbot.address,
            dotbot.application,
            DotBotRgbLedCommandModel(red=255, green=0, blue=0),
        )

    # Phase 1: initial queue
    sorted_bots = order_bots(dotbots)
    goals = assign_queue_goals(sorted_bots)

    await send_to_goal(query, goals, params)

    # Phase 2: charging loop
    remaining = sorted_bots.copy()
    while remaining:
        dotbots = api.controller.get_dotbots(query)
        total_count = len(dotbots)
        dotbots = [b for b in dotbots if b.address in {r.address for r in remaining}]
        remaining = order_bots(dotbots)

        # Assign charging + shift goals
        goals = assign_charge_goals(remaining)
        await send_to_goal(query, goals, params)

        # Head just finished charging
        head = remaining[0]

        dt = 0.1
        # Cosmetic: wait for charging...
        colors = [
            (255, 255, 0),  # yellow
            (0, 255, 0),  # green
        ]
        await asyncio.sleep(20 * dt)

        for r, g, b in colors:
            await dotbots_rgb_led(
                head.address,
                head.application,
                DotBotRgbLedCommandModel(red=r, green=g, blue=b),
            )
            await asyncio.sleep(20 * dt)

        # Just back a bit
        for _ in range(25):
            await dotbots_move_raw(
                head.address,
                head.application,
                DotBotMoveRawCommandModel(
                    left_x=0, right_x=0, left_y=-90, right_y=-100
                ),
            )
            await asyncio.sleep(dt)

        PARK_X = 0.8
        PARK_Y = 0.2
        PARK_SPACING = 0.15

        parked_count = total_count - len(remaining)

        # Send head to parking
        await send_to_goal(
            query,
            {head.address: {"x": PARK_X, "y": PARK_Y + parked_count * PARK_SPACING}},
            params,
        )

        # Remove head from queue
        remaining = remaining[1:]

    return Vec2(x=0, y=0)


async def send_to_goal(
    query: DotBotQueryModel, goals: Dict[str, dict], params: OrcaParams
) -> None:
    dt = 0.20
    bot_radius = 0.02
    #  Queue
    while True:
        dotbots: List[DotBotModel] = api.controller.get_dotbots(query)
        agents: List[Agent] = []

        for bot in dotbots:
            agents.append(
                Agent(
                    id=bot.address,
                    position=Vec2(x=bot.lh2_position.x, y=bot.lh2_position.y),
                    velocity=Vec2(x=0, y=0),
                    radius=bot_radius,
                    direction=bot.direction,
                    max_speed=1.0,  # Must match the maxSpeed used in preferred_vel calculation
                    preferred_velocity=preferred_vel(
                        dotbot=bot, goal=goals.get(bot.address)
                    ),
                )
            )

        queue_ready = all(
            a.preferred_velocity.x == 0 and a.preferred_velocity.y == 0 for a in agents
        )
        if queue_ready:
            break
        for agent in agents:
            neighbors = [neighbor for neighbor in agents if neighbor.id != agent.id]

            orca_vel = await compute_orca_velocity(
                agent, neighbors=neighbors, params=params
            )
            STEP_SCALE = 0.1
            step = Vec2(x=orca_vel.x * STEP_SCALE, y=orca_vel.y * STEP_SCALE)

            # ---- CLAMP STEP TO GOAL DISTANCE ----
            goal = goals.get(agent.id)
            if goal is not None:
                dx = goal["x"] - agent.position.x
                dy = goal["y"] - agent.position.y
                dist_to_goal = math.hypot(dx, dy)

                step_len = math.hypot(step.x, step.y)
                if step_len > dist_to_goal and step_len > 0:
                    scale = dist_to_goal / step_len
                    step = Vec2(x=step.x * scale, y=step.y * scale)
            # ------------------------------------

            waypoints = DotBotWaypoints(
                threshold=THRESHOLD,
                waypoints=[
                    DotBotLH2Position(
                        x=agent.position.x + step.x, y=agent.position.y + step.y, z=0
                    )
                ],
            )
            # POST waypoint
            await dotbots_waypoints(
                address=agent.id, application=0, waypoints=waypoints
            )
        await asyncio.sleep(dt)
    return None


def order_bots(dotbots: List[DotBotModel]) -> List[DotBotModel]:
    BASE_X, BASE_Y = 0.2, 0.8

    def key(bot):
        dx = bot.lh2_position.x - BASE_X
        dy = bot.lh2_position.y - BASE_Y
        return dx * dx + dy * dy

    return sorted(dotbots, key=key)


def assign_queue_goals(
    ordered: List[DotBotModel],
    base_x=0.35,
    base_y=0.8,
    spacing=0.2,
) -> Dict[str, dict]:
    goals = {}
    for i, bot in enumerate(ordered):
        goals[bot.address] = {
            "x": base_x + i * spacing,
            "y": base_y,
        }
    return goals


def assign_charge_goals(
    ordered: List[DotBotModel],
    base_x=0.35,
    base_y=0.8,
    spacing=0.2,
) -> Dict[str, dict]:
    goals = {}
    # Send the first one to the charger
    head = ordered[0]
    goals[head.address] = {
        "x": 0.2,
        "y": 0.2,
    }

    # Remaining bots shift left in the queue
    for i, bot in enumerate(ordered[1:]):
        goals[bot.address] = {
            "x": base_x + i * spacing,
            "y": base_y,
        }
    return goals


def preferred_vel(dotbot: DotBotModel, goal: Vec2 | None) -> Vec2:
    if goal is None:
        return Vec2(x=0, y=0)

    dx = goal["x"] - dotbot.lh2_position.x
    dy = goal["y"] - dotbot.lh2_position.y
    dist = math.sqrt(dx * dx + dy * dy)

    dist1000 = dist * 1000
    # If close to goal, stop
    if dist1000 < THRESHOLD:
        return Vec2(x=0, y=0)
    max_speed = 0.75
    # max_speed = 0.75 if dist1000 >= THRESHOLD else 0.75 * (dist / 0.1)

    # Right-hand rule bias
    bias_angle = 0.0
    # Bot can only walk on a cone [-60, 60] in front of himself
    max_deviation = math.radians(60)

    # Convert bot direction into radians
    direction = direction_to_rad(dotbot.direction)

    # Angle to goal
    angle_to_goal = math.atan2(dy, dx) + bias_angle

    delta = angle_to_goal - direction
    # Wrap to [-π, +π]
    delta = math.atan2(math.sin(delta), math.cos(delta))

    # Clamp delta to [-MAX, +MAX]
    if delta > max_deviation:
        delta = max_deviation
    if delta < -max_deviation:
        delta = -max_deviation

    # Final allowed direction
    final_angle = direction + delta
    result = Vec2(
        x=math.cos(final_angle) * max_speed, y=math.sin(final_angle) * max_speed
    )
    return result


def direction_to_rad(direction: float) -> float:
    rad = (direction + 90) * math.pi / 180.0
    return math.atan2(math.sin(rad), math.cos(rad))  # normalize to [-π, π]


# Mount static files after all routes are defined
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "build")
api.mount("/PyDotBot", StaticFiles(directory=FRONTEND_DIR, html=True), name="PyDotBot")
