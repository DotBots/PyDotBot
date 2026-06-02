"""charging_station_sdk.py - the ORCA control loop on the Swarm SDK.

Migrates the heart of charging_station.py: the collision-avoiding control loop
that streams a fresh ORCA step to each bot every tick to bring the fleet into
the charging queue formation. The ORCA math (dotbot.examples.common.orca) is
unchanged domain code; the SDK absorbs the REST polling, the ws client, the
waypoint pydantic towers and the manual `sleep(DT)` loop - the loop body becomes
`async for _ in swarm.tick(...)` + `bot.goto(bot.position + step)`.

Run a simulator/controller on :8000, then:  python charging_station_sdk.py
"""

import asyncio
import math

from dotbot.examples.common.orca import (
    Agent,
    OrcaParams,
    compute_orca_velocity_for_agent,
)
from dotbot.examples.common.vec2 import Vec2
from dotbot.sdk import Swarm

THRESHOLD = 100  # mm, proximity to consider a goal reached
DT = 0.2  # control-loop period (s) -> 5 Hz
BOT_RADIUS = 60  # mm, used for collision avoidance
MAX_SPEED = 300  # mm/s
QUEUE_HEAD_X, QUEUE_HEAD_Y = 500, 1500
QUEUE_SPACING = 300


def _direction_to_rad(direction) -> float:
    rad = ((direction or 0) + 90) * math.pi / 180.0
    return math.atan2(math.sin(rad), math.cos(rad))


def _preferred_vel(bot, goal) -> Vec2:
    """Velocity the bot would take toward its goal absent neighbours; zero once
    within THRESHOLD (the loop's stop condition)."""
    if goal is None or bot.position is None:
        return Vec2(x=0, y=0)
    dx = goal["x"] - bot.position.x
    dy = goal["y"] - bot.position.y
    if math.hypot(dx, dy) < THRESHOLD:
        return Vec2(x=0, y=0)
    direction = _direction_to_rad(bot.direction)
    angle_to_goal = math.atan2(dy, dx)
    delta = math.atan2(
        math.sin(angle_to_goal - direction), math.cos(angle_to_goal - direction)
    )
    final = direction + delta
    return Vec2(x=math.cos(final) * MAX_SPEED, y=math.sin(final) * MAX_SPEED)


def _order_bots(bots):
    return sorted(
        bots,
        key=lambda b: (
            (b.position.x - QUEUE_HEAD_X) ** 2 + (b.position.y - QUEUE_HEAD_Y) ** 2,
            b.address,
        ),
    )


def _queue_goals(ordered):
    return {
        b.address: {"x": QUEUE_HEAD_X + i * QUEUE_SPACING, "y": QUEUE_HEAD_Y}
        for i, b in enumerate(ordered)
    }


async def converge(swarm: Swarm, goals: dict, params: OrcaParams) -> None:
    """Stream ORCA steps until every bot is within THRESHOLD of its goal."""
    async for _ in swarm.tick(rate_hz=1 / DT):
        bots = [b for b in swarm if b.is_online and b.position is not None]
        agents = [
            Agent(
                id=b.address,
                position=Vec2(x=b.position.x, y=b.position.y),
                velocity=Vec2(x=0, y=0),
                radius=BOT_RADIUS,
                max_speed=MAX_SPEED,
                preferred_velocity=_preferred_vel(b, goals.get(b.address)),
            )
            for b in bots
        ]
        if all(
            a.preferred_velocity.x == 0 and a.preferred_velocity.y == 0 for a in agents
        ):
            return
        by_address = {b.address: b for b in bots}
        for agent in agents:
            neighbors = [n for n in agents if n.id != agent.id]
            velocity = compute_orca_velocity_for_agent(agent, neighbors, params)
            step = Vec2(x=velocity.x, y=velocity.y)
            goal = goals.get(agent.id)
            if goal is not None:  # clamp the step so it never overshoots the goal
                dist = math.hypot(
                    goal["x"] - agent.position.x, goal["y"] - agent.position.y
                )
                length = math.hypot(step.x, step.y)
                if length > dist and length > 0:
                    step = Vec2(x=step.x * dist / length, y=step.y * dist / length)
            bot = by_address[agent.id]
            bot.goto(
                bot.position.x + step.x,
                bot.position.y + step.y,
                threshold=int(THRESHOLD * 0.9),
            )


async def charging_station(swarm: Swarm) -> None:
    await asyncio.sleep(1.0)
    bots = [b for b in swarm if b.is_online and b.position is not None]
    if not bots:
        print("no active bots")
        return
    print(f"{len(bots)} bots; forming the charging queue with ORCA ...")
    swarm.all.set_color("red")
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)
    await converge(swarm, _queue_goals(_order_bots(bots)), params)

    queue = _order_bots([b for b in swarm if b.is_online and b.position is not None])
    print("queue formed:")
    for bot in queue:
        print("   ", bot)

    # cosmetic slice of phase 2: the queue head 'charges' (green) then disengages
    head = queue[0]
    head.set_color("green")
    await asyncio.sleep(2.0)
    head.move_raw(left=(0, -80), right=(0, -80))  # reverse off the charger
    await asyncio.sleep(1.0)
    head.stop()
    print("done")


if __name__ == "__main__":
    Swarm.run(charging_station)
