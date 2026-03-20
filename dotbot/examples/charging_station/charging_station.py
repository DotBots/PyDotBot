import asyncio
import math
import os
from typing import Dict, List

from dotbot.examples.common.orca import (
    Agent,
    OrcaParams,
    compute_orca_velocity_for_agent,
)
from dotbot.examples.common.vec2 import Vec2
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
    WSRgbLed,
    WSWaypoints,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient, rest_client
from dotbot.websocket import DotBotWsClient

THRESHOLD = 100  # Acceptable distance error to consider a waypoint reached
DT = 0.2  # Control loop period (seconds)

# TODO: Measure these values for real dotbots
BOT_RADIUS = 60  # Physical radius of a DotBot (unit), used for collision avoidance
MAX_SPEED = 300  # Maximum allowed linear speed of a bot (mm/s)

(CHARGER_X, CHARGER_Y) = (
    500,
    500,
)

(QUEUE_HEAD_X, QUEUE_HEAD_Y) = (
    500,
    1500,
)  # World-frame (X, Y) position of the charging queue head
QUEUE_SPACING = (
    300  # Spacing between consecutive bots in the charging queue (along X axis)
)

(PARK_X, PARK_Y) = (1500, 500)  # World-frame (X, Y) position of the parking area origin
PARK_SPACING = 300  # Spacing between parked bots (along Y axis)


async def queue_robots(
    client: RestClient,
    ws: DotBotWsClient,
    dotbots: List[DotBotModel],
    params: OrcaParams,
) -> None:
    sorted_bots = order_bots(dotbots, QUEUE_HEAD_X, QUEUE_HEAD_Y)
    goals = assign_queue_goals(sorted_bots, QUEUE_HEAD_X, QUEUE_HEAD_Y, QUEUE_SPACING)
    await send_to_goal(client, ws, goals, params)


async def fetch_active_dotbots(client: RestClient) -> List[DotBotModel]:
    return await client.fetch_dotbots(
        query=DotBotQueryModel(status=DotBotStatus.ACTIVE)
    )


async def charge_robots(
    client: RestClient,
    ws: DotBotWsClient,
    params: OrcaParams,
) -> None:
    dotbots = await fetch_active_dotbots(client)
    remaining = order_bots(dotbots, QUEUE_HEAD_X, QUEUE_HEAD_Y)
    total_count = len(dotbots)
    # The head of the remaining should park
    # Except on the first loop, where it should just queue.
    park_dotbot: DotBotModel | None = None
    parked_count = total_count - len(remaining)

    while remaining or park_dotbot is not None:
        dotbots = await fetch_active_dotbots(client)

        dotbots = [b for b in dotbots if b.address in {r.address for r in remaining}]
        remaining = order_bots(dotbots, QUEUE_HEAD_X, QUEUE_HEAD_Y)

        # Assign charging + shift goals
        goals = assign_charge_goals(
            remaining, QUEUE_HEAD_X, QUEUE_HEAD_Y, QUEUE_SPACING
        )

        if park_dotbot is not None:
            goals[park_dotbot.address] = {
                "x": PARK_X,
                "y": PARK_Y + parked_count * PARK_SPACING,
            }
        await send_to_goal(client, ws, goals, params)

        if len(remaining) == 0:
            break

        head = remaining[0]

        # Cosmetic: wait for charging...
        colors = [
            (255, 128, 0),  # yellow
            (0, 255, 0),  # green
        ]
        await asyncio.sleep(10 * DT)

        for r, g, b in colors:
            await client.send_rgb_led_command(
                address=head.address,
                command=DotBotRgbLedCommandModel(red=r, green=g, blue=b),
            )

            await asyncio.sleep(10 * DT)

        # Reverse slightly to disengage the robot from the charging station
        await disengage_from_charger(client, head.address)

        parked_count = total_count - len(remaining)

        # send it to park
        park_dotbot = remaining[0]
        # Remove head from queue
        remaining = remaining[1:]


async def disengage_from_charger(client: RestClient, dotbot_address: str):
    bots = await client.fetch_dotbots(query=DotBotQueryModel(address=dotbot_address))
    if not bots:
        return
    dotbot = bots[0]
    initial_y = dotbot.lh2_position.y

    # reverse until 300 units below initial position
    y_after_reverse = initial_y + 300
    # forward a bit to recover direction
    y_after_forward = y_after_reverse - 10

    while True:
        bots = await client.fetch_dotbots(
            query=DotBotQueryModel(address=dotbot_address)
        )
        if not bots or bots[0].lh2_position.y >= y_after_reverse:
            break
        await client.send_move_raw_command(
            address=dotbot_address,
            application=dotbot.application,
            command=DotBotMoveRawCommandModel(
                left_x=0, left_y=-80, right_x=0, right_y=-80
            ),
        )
        await asyncio.sleep(0.1)

    while True:
        bots = await client.fetch_dotbots(
            query=DotBotQueryModel(address=dotbot_address)
        )
        if not bots or bots[0].lh2_position.y <= y_after_forward:
            break
        await client.send_move_raw_command(
            address=dotbot_address,
            application=dotbot.application,
            command=DotBotMoveRawCommandModel(
                left_x=0, left_y=80, right_x=0, right_y=80
            ),
        )
        await asyncio.sleep(0.1)


async def send_to_goal(
    client: RestClient,
    ws: DotBotWsClient,
    goals: Dict[str, dict],
    params: OrcaParams,
) -> None:
    while True:
        dotbots = await fetch_active_dotbots(client)
        agents: List[Agent] = []

        for bot in dotbots:
            agents.append(
                Agent(
                    id=bot.address,
                    position=Vec2(x=bot.lh2_position.x, y=bot.lh2_position.y),
                    velocity=Vec2(x=0, y=0),
                    radius=BOT_RADIUS,
                    max_speed=MAX_SPEED,
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
            step = Vec2(x=orca_vel.x, y=orca_vel.y)

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
                threshold=THRESHOLD * 0.9,
                waypoints=[
                    DotBotLH2Position(
                        x=agent.position.x + step.x, y=agent.position.y + step.y, z=0
                    )
                ],
            )
            await ws.send(
                WSWaypoints(
                    cmd="waypoints",
                    address=agent.id,
                    application=ApplicationType.DotBot,
                    data=waypoints,
                )
            )

        await asyncio.sleep(DT)
    return None


def order_bots(
    dotbots: List[DotBotModel], base_x: int, base_y: int
) -> List[DotBotModel]:
    def key(bot: DotBotModel):
        dx = bot.lh2_position.x - base_x
        dy = bot.lh2_position.y - base_y
        return (dx * dx + dy * dy, bot.address)

    return sorted(dotbots, key=key)


def assign_queue_goals(
    ordered: List[DotBotModel],
    head_x: int,
    head_y: int,
    spacing: int,
) -> Dict[str, dict]:
    goals = {}
    for i, bot in enumerate(ordered):
        goals[bot.address] = {
            "x": head_x + i * spacing,
            "y": head_y,
        }
    return goals


def assign_charge_goals(
    ordered: List[DotBotModel],
    base_x: int,
    base_y: int,
    spacing: int,
) -> Dict[str, dict]:
    if len(ordered) == 0:
        return {}

    goals = {}
    # Send the first one to the charger
    head = ordered[0]
    goals[head.address] = {
        "x": CHARGER_X,
        "y": CHARGER_Y,
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

    # If close to goal, stop
    if dist < THRESHOLD:
        return Vec2(x=0, y=0)

    # Right-hand rule bias
    bias_angle = 0.0
    # Convert bot direction into radians
    direction = direction_to_rad(dotbot.direction)

    # Angle to goal
    angle_to_goal = math.atan2(dy, dx) + bias_angle

    delta = angle_to_goal - direction
    # Wrap to [-π, +π]
    delta = math.atan2(math.sin(delta), math.cos(delta))

    # Final allowed direction
    final_angle = direction + delta
    result = Vec2(
        x=math.cos(final_angle) * MAX_SPEED, y=math.sin(final_angle) * MAX_SPEED
    )
    return result


def direction_to_rad(direction: float) -> float:
    rad = (direction + 90) * math.pi / 180.0
    return math.atan2(math.sin(rad), math.cos(rad))  # normalize to [-π, +π]


async def compute_orca_velocity(
    agent: Agent,
    neighbors: List[Agent],
    params: OrcaParams,
) -> Vec2:
    return compute_orca_velocity_for_agent(agent, neighbors, params)


async def main() -> None:
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)
    url = os.getenv("DOTBOT_CONTROLLER_URL", "localhost")
    port = os.getenv("DOTBOT_CONTROLLER_PORT", "8000")
    use_https = os.getenv("DOTBOT_CONTROLLER_USE_HTTPS", False)
    async with rest_client(url, port, use_https) as client:
        dotbots = await fetch_active_dotbots(client)

        ws = DotBotWsClient(url, port)
        await ws.connect()
        try:
            # Cosmetic: all bots are red
            for dotbot in dotbots:
                await ws.send(
                    WSRgbLed(
                        cmd="rgb_led",
                        address=dotbot.address,
                        application=ApplicationType.DotBot,
                        data=DotBotRgbLedCommandModel(
                            red=255,
                            green=0,
                            blue=0,
                        ),
                    )
                )

            # Phase 1: initial queue
            await queue_robots(client, ws, dotbots, params)

            # Phase 2: charging loop
            await charge_robots(client, ws, params)
        except (asyncio.CancelledError, KeyboardInterrupt):
            active_dotbots = await fetch_active_dotbots(client)
            for dotbot in active_dotbots:
                await ws.send(
                    WSWaypoints(
                        cmd="waypoints",
                        address=dotbot.address,
                        application=dotbot.application,
                        data=DotBotWaypoints(
                            threshold=0,
                            waypoints=[],
                        ),
                    )
                )
        finally:
            await ws.close()

    return None


if __name__ == "__main__":
    asyncio.run(main())
