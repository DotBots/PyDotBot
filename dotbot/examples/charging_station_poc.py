import asyncio
import math
import os
from typing import Dict, List

from dotbot.examples.orca import (
    Agent,
    OrcaParams,
    compute_orca_velocity_for_agent,
)
from dotbot.examples.vec2 import Vec2
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient

THRESHOLD = 30  # Acceptable distance error to consider a waypoint reached
DT = 0.05  # Control loop period (seconds)

# TODO: Measure these values for real dotbots
BOT_RADIUS = 0.03  # Physical radius of a DotBot (unit), used for collision avoidance
MAX_SPEED = 0.75  # Maximum allowed linear speed of a bot

(QUEUE_HEAD_X, QUEUE_HEAD_Y) = (
    0.1,
    0.8,
)  # World-frame (X, Y) position of the charging queue head
QUEUE_SPACING = (
    0.1  # Spacing between consecutive bots in the charging queue (along X axis)
)

(PARK_X, PARK_Y) = (0.8, 0.1)  # World-frame (X, Y) position of the parking area origin
PARK_SPACING = 0.1  # Spacing between parked bots (along Y axis)


async def run_charging_station_poc(
    params: OrcaParams,
    client: RestClient,
) -> None:
    dotbots = await client.fetch_active_dotbots()

    # Cosmetic: all bots are red
    for dotbot in dotbots:
        await client.send_rgb_led_command(
            address=dotbot.address,
            command=DotBotRgbLedCommandModel(red=255, green=0, blue=0),
        )

        # await set_dotbot_rgb_led(
        #     client,
        #     address=dotbot.address,
        #     application=dotbot.application,
        #     red=255,
        #     green=0,
        #     blue=0,
        # )

    # Phase 1: initial queue
    sorted_bots = order_bots(dotbots, QUEUE_HEAD_X, QUEUE_HEAD_Y)
    goals = assign_queue_goals(sorted_bots, QUEUE_HEAD_X, QUEUE_HEAD_Y, QUEUE_SPACING)

    await send_to_goal(client, goals, params)

    # Phase 2: charging loop
    remaining = sorted_bots
    total_count = len(dotbots)
    # The head of the remaining should park
    # Except on the first loop, where it should just queue.
    park_dotbot: DotBotModel | None = None
    parked_count = total_count - len(remaining)

    while remaining or park_dotbot is not None:
        dotbots = await client.fetch_active_dotbots()

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
        await send_to_goal(client, goals, params)

        if len(remaining) == 0:
            break

        head = remaining[0]

        # Cosmetic: wait for charging...
        colors = [
            (255, 255, 0),  # yellow
            (0, 255, 0),  # green
        ]
        await asyncio.sleep(20 * DT)

        for r, g, b in colors:
            await client.send_rgb_led_command(
                address=head.address,
                command=DotBotRgbLedCommandModel(red=r, green=g, blue=b),
            )

            await asyncio.sleep(20 * DT)

        # Reverse slightly to disengage the robot from the charging station
        await disengage_from_charger(client, head)

        parked_count = total_count - len(remaining)

        # send it to park
        park_dotbot = remaining[0]
        # Remove head from queue
        remaining = remaining[1:]

    return None


async def disengage_from_charger(client: RestClient, head: DotBotModel):
    for _ in range(25):
        await client.send_move_raw_command(
            address=head.address,
            application=head.application,
            command=DotBotMoveRawCommandModel(
                left_x=0, left_y=-100, right_x=0, right_y=-100
            ),
        )
        await asyncio.sleep(DT)


async def send_to_goal(
    client: RestClient,
    goals: Dict[str, dict],
    params: OrcaParams,
) -> None:
    #  Queue
    while True:
        dotbots = await client.fetch_active_dotbots()
        agents: List[Agent] = []

        for bot in dotbots:
            agents.append(
                Agent(
                    id=bot.address,
                    position=Vec2(x=bot.lh2_position.x, y=bot.lh2_position.y),
                    velocity=Vec2(x=0, y=0),
                    radius=BOT_RADIUS,
                    direction=bot.direction,
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
            await client.send_waypoint_command(
                address=agent.id,
                application=ApplicationType.DotBot,
                command=waypoints,
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
        x=math.cos(final_angle) * MAX_SPEED, y=math.sin(final_angle) * MAX_SPEED
    )
    return result


def direction_to_rad(direction: float) -> float:
    rad = (direction + 90) * math.pi / 180.0
    return math.atan2(math.sin(rad), math.cos(rad))  # normalize to [-π, π]


async def compute_orca_velocity(
    agent: Agent,
    neighbors: List[Agent],
    params: OrcaParams,
) -> Vec2:
    return compute_orca_velocity_for_agent(agent, neighbors, params)


async def main() -> None:
    params = OrcaParams(time_horizon=DT)
    url = os.getenv("DOTBOT_CONTROLLER_URL", "localhost")
    port = os.getenv("DOTBOT_CONTROLLER_PORT", "8000")
    use_https = os.getenv("DOTBOT_CONTROLLER_USE_HTTPS", False)
    client = RestClient(url, port, use_https)

    await run_charging_station_poc(params, client)


if __name__ == "__main__":
    asyncio.run(main())
