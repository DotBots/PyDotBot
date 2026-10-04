"""Queue robots on the border between the field and staging, charge them one
at a time at a charger, then park them along the field's opposite edge. Every
position comes from the controller's site: the charger is the site's first
`charger` object, else a point on staging's far edge."""

import asyncio
import math
import os
from dataclasses import dataclass
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
from dotbot.site import Site
from dotbot.websocket import DotBotWsClient

THRESHOLD = 100  # Acceptable distance error to consider a waypoint reached
DT = 0.2  # Control loop period (seconds)

# TODO: Measure these values for real dotbots
BOT_RADIUS = 60  # Physical radius of a DotBot (unit), used for collision avoidance
MAX_SPEED = 300  # Maximum allowed linear speed of a bot (mm/s)

QUEUE_HEAD_INSET = 500  # From staging's left edge to the queue head and charger
CHARGER_INSET = 100  # From staging's far edge to the charger
QUEUE_SPACING = 300  # Between consecutive bots in the queue, along x
PARK_INSET = 300  # From the field's edges to the first parking slot
PARK_SPACING = 300  # Between parked bots, along x
DISENGAGE_DISTANCE = 400  # How far a charged bot reverses off the charger


@dataclass(frozen=True)
class ChargingLayout:
    """Where the queue, the charger and the parking row are, in frame mm.

    `away` is the sign of y a bot reverses along to leave the charger.
    """

    charger_x: int
    charger_y: int
    queue_head_x: int
    queue_head_y: int
    park_x: int
    park_y: int
    away: int


def layout_from_site(site: Site) -> ChargingLayout:
    """The layout for a site with a field and a staging area above or below it.

    A site with a `charger` object puts the charger there, and the queue's
    head in line with it.
    """
    field, staging = site.field, site.staging
    if field is None or staging is None:
        raise ValueError(
            f"site {site.name!r} needs a field and a staging area; "
            "`dotbot config init` writes a site with both"
        )
    below = staging.centre[1] >= field.centre[1]
    chargers = site.objects_of("charger")
    if chargers:
        charger = chargers[0]
        head_x = charger.x
    else:
        charger = None
        head_x = staging.x + min(QUEUE_HEAD_INSET, staging.w // 4)
    if below:
        return ChargingLayout(
            charger_x=head_x,
            charger_y=charger.y if charger else staging.y_max - CHARGER_INSET,
            queue_head_x=head_x,
            queue_head_y=staging.y,
            park_x=field.x + PARK_INSET,
            park_y=field.y + PARK_INSET,
            away=-1,
        )
    return ChargingLayout(
        charger_x=head_x,
        charger_y=charger.y if charger else staging.y + CHARGER_INSET,
        queue_head_x=head_x,
        queue_head_y=staging.y_max,
        park_x=field.x + PARK_INSET,
        park_y=field.y_max - PARK_INSET,
        away=1,
    )


async def queue_robots(
    client: RestClient,
    ws: DotBotWsClient,
    dotbots: List[DotBotModel],
    params: OrcaParams,
    layout: ChargingLayout,
) -> None:
    sorted_bots = order_bots(dotbots, layout.queue_head_x, layout.queue_head_y)
    goals = assign_queue_goals(
        sorted_bots, layout.queue_head_x, layout.queue_head_y, QUEUE_SPACING
    )
    await send_to_goal(client, ws, goals, params)


async def fetch_active_dotbots(client: RestClient) -> List[DotBotModel]:
    return await client.fetch_dotbots(
        query=DotBotQueryModel(status=DotBotStatus.ACTIVE)
    )


async def charge_robots(
    client: RestClient,
    ws: DotBotWsClient,
    params: OrcaParams,
    layout: ChargingLayout,
) -> None:
    dotbots = await fetch_active_dotbots(client)
    remaining = order_bots(dotbots, layout.queue_head_x, layout.queue_head_y)
    total_count = len(dotbots)
    # The head of the remaining should park
    # Except on the first loop, where it should just queue.
    park_dotbot: DotBotModel | None = None
    parked_count = total_count - len(remaining)

    while remaining or park_dotbot is not None:
        dotbots = await fetch_active_dotbots(client)

        dotbots = [b for b in dotbots if b.address in {r.address for r in remaining}]
        remaining = order_bots(dotbots, layout.queue_head_x, layout.queue_head_y)

        # Assign charging + shift goals
        goals = assign_charge_goals(remaining, layout)

        if park_dotbot is not None:
            goals[park_dotbot.address] = {
                "x": layout.park_x + parked_count * PARK_SPACING,
                "y": layout.park_y,
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
        await disengage_from_charger(client, head.address, layout.away)

        parked_count = total_count - len(remaining)

        # send it to park
        park_dotbot = remaining[0]
        # Remove head from queue
        remaining = remaining[1:]


async def disengage_from_charger(client: RestClient, dotbot_address: str, away: int):
    """Reverse `DISENGAGE_DISTANCE` along `away` (a sign of y), then nudge forward."""
    bots = await client.fetch_dotbots(query=DotBotQueryModel(address=dotbot_address))
    if not bots:
        return
    dotbot = bots[0]
    initial_y = dotbot.lh2_position.y

    def travelled(bot: DotBotModel) -> float:
        return (bot.lh2_position.y - initial_y) * away

    while True:
        bots = await client.fetch_dotbots(
            query=DotBotQueryModel(address=dotbot_address)
        )
        if not bots or travelled(bots[0]) >= DISENGAGE_DISTANCE:
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
        if not bots or travelled(bots[0]) <= DISENGAGE_DISTANCE - 10:
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
                        x=agent.position.x + step.x, y=agent.position.y + step.y
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
    ordered: List[DotBotModel], layout: ChargingLayout
) -> Dict[str, dict]:
    if len(ordered) == 0:
        return {}

    goals = {}
    # Send the first one to the charger
    head = ordered[0]
    goals[head.address] = {
        "x": layout.charger_x,
        "y": layout.charger_y,
    }

    # Remaining bots shift left in the queue
    for i, bot in enumerate(ordered[1:]):
        goals[bot.address] = {
            "x": layout.queue_head_x + i * QUEUE_SPACING,
            "y": layout.queue_head_y,
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
        try:
            layout = layout_from_site(await client.fetch_site())
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
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
            await queue_robots(client, ws, dotbots, params, layout)

            # Phase 2: charging loop
            await charge_robots(client, ws, params, layout)
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
