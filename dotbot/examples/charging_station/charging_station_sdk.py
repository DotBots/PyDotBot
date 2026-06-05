"""charging_station_sdk.py - the full charging-station scenario on the Swarm SDK.

The fleet forms a single-file queue, then services the charger one bot at a
time: the queue head drives in, dwells while it "charges" (red -> amber ->
green), then peels off to the next free parking slot while the rest of the
queue shifts forward by one. Repeat until every bot has charged and parked.

This is the SDK rewrite of charging_station.py. The ORCA collision-avoidance
math (dotbot.examples.common.orca) is unchanged domain code; everything the
old version hand-rolled - REST polling, the ws client, the waypoint pydantic
towers, the manual reverse-out-of-the-charger maneuver - collapses into the
Swarm: every motion phase is one `converge(...)` that streams a fresh ORCA step
per `swarm.tick()`, and a charged bot reaches its parking slot as just another
goal in the next convergence (so it threads out past the incoming bot under the
same collision avoidance, no scripted disengage needed).

Run a controller in simulator mode, then run this script:

    dotbot run controller --conn simulator --headless \\
        --simulator-init-state \\
        dotbot/examples/charging_station/charging_station_init_state.toml

    python -m dotbot.examples.charging_station.charging_station_sdk
"""

import asyncio
import math

from dotbot.examples.common.orca import (
    Agent,
    OrcaParams,
    compute_orca_velocity_for_agent,
)
from dotbot.examples.common.vec2 import Vec2
from dotbot.sdk import Bot, Position, Swarm

THRESHOLD = 100  # mm, proximity to consider a goal reached
DT = 0.2  # control-loop period (s) -> 5 Hz
BOT_RADIUS = 60  # mm, used for collision avoidance
MAX_SPEED = 300  # mm/s
CONVERGE_TIMEOUT = 90.0  # s, give up on a phase that never settles

# World-frame layout (mm). The queue is a horizontal line; the head peels off
# downward to the charger, then out to the parking column on the right.
CHARGER = Position(500, 500)
QUEUE_HEAD = Position(500, 1500)
QUEUE_SPACING = 300  # between consecutive bots in the queue (along +x)
PARK_ORIGIN = Position(1700, 500)
PARK_SPACING = 300  # between parked bots (along +y)

CHARGE_SECONDS = 2.0  # dwell at the charger while "charging"
CHARGING_COLOR = (255, 128, 0)  # amber: plugged in and charging
CHARGED_COLOR = "green"  # done charging


def _online(swarm: Swarm) -> list[Bot]:
    """Bots that are active and have a position fix - the only ones we can plan
    for."""
    return [b for b in swarm if b.is_online and b.position is not None]


async def _await_fleet(swarm: Swarm, *, timeout: float = 10.0) -> list[Bot]:
    """Wait until the fleet has reported position fixes, then return it. Bounded
    so the script exits cleanly if no bots ever show up."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    bots = _online(swarm)
    while not bots and loop.time() < deadline:
        await asyncio.sleep(0.2)
        bots = _online(swarm)
    return bots


def _direction_to_rad(direction) -> float:
    rad = ((direction or 0) + 90) * math.pi / 180.0
    return math.atan2(math.sin(rad), math.cos(rad))


def _preferred_vel(bot: Bot, goal: Position | None) -> Vec2:
    """Velocity the bot would take toward its goal absent neighbours; zero once
    within THRESHOLD (the loop's stop condition)."""
    if goal is None or bot.position is None:
        return Vec2(x=0, y=0)
    dx = goal.x - bot.position.x
    dy = goal.y - bot.position.y
    if math.hypot(dx, dy) < THRESHOLD:
        return Vec2(x=0, y=0)
    direction = _direction_to_rad(bot.direction)
    angle_to_goal = math.atan2(dy, dx)
    delta = math.atan2(
        math.sin(angle_to_goal - direction), math.cos(angle_to_goal - direction)
    )
    final = direction + delta
    return Vec2(x=math.cos(final) * MAX_SPEED, y=math.sin(final) * MAX_SPEED)


def _order_by_distance(bots: list[Bot], ref: Position) -> list[Bot]:
    """Order bots by distance to a reference point (nearest first), address as a
    stable tiebreak."""
    return sorted(bots, key=lambda b: (b.position.distance_to(ref), b.address))


def _queue_goals(ordered: list[Bot]) -> dict[str, Position]:
    """Assign the i-th bot to the i-th slot of the queue line."""
    return {
        b.address: QUEUE_HEAD + (i * QUEUE_SPACING, 0) for i, b in enumerate(ordered)
    }


async def converge(
    swarm: Swarm, goals: dict[str, Position], params: OrcaParams
) -> bool:
    """Stream ORCA steps until every goal-holding bot is online and within
    THRESHOLD of its goal. Returns True when the formation settles, or False if
    CONVERGE_TIMEOUT elapses first (a bot got stuck, never arrived, or dropped
    out). Bots without a goal hold station and are still avoided as neighbours."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + CONVERGE_TIMEOUT
    async for _ in swarm.tick(rate_hz=1 / DT):
        bots = _online(swarm)
        by_address = {b.address: b for b in bots}
        # Settled only when EVERY goal-holder is present and has reached its goal
        # by position - not off a snapshot of whoever is online this tick. A
        # goal-holder that drops out (or an empty fleet) must never look "done".
        settled = bool(goals) and all(
            addr in by_address
            and by_address[addr].position is not None
            and by_address[addr].position.distance_to(goal) <= THRESHOLD
            for addr, goal in goals.items()
        )
        if settled:
            return True
        if loop.time() > deadline:
            return False
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
        for agent in agents:
            neighbors = [n for n in agents if n.id != agent.id]
            velocity = compute_orca_velocity_for_agent(agent, neighbors, params)
            step = Vec2(x=velocity.x, y=velocity.y)
            goal = goals.get(agent.id)
            if goal is not None:  # clamp the step so it never overshoots the goal
                dist = math.hypot(goal.x - agent.position.x, goal.y - agent.position.y)
                length = math.hypot(step.x, step.y)
                if length > dist and length > 0:
                    step = Vec2(x=step.x * dist / length, y=step.y * dist / length)
            by_address[agent.id].goto(
                agent.position.x + step.x,
                agent.position.y + step.y,
                threshold=int(THRESHOLD * 0.9),
            )
    return False  # swarm.tick() never ends; here only to satisfy the type


async def _charge(bot: Bot) -> None:
    """Dwell at the charger: amber while charging, green when full."""
    bot.set_color(CHARGING_COLOR)
    await asyncio.sleep(CHARGE_SECONDS)
    bot.set_color(CHARGED_COLOR)
    await asyncio.sleep(CHARGE_SECONDS / 2)


async def charging_station(swarm: Swarm) -> None:
    bots = await _await_fleet(swarm)
    if not bots:
        print("no active bots")
        return
    total = len(bots)
    print(f"{total} bots online; forming the charging queue with ORCA ...")
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)
    swarm.all.set_color("red")

    # Phase 1: bring the whole fleet into the queue.
    await converge(swarm, _queue_goals(_order_by_distance(bots, QUEUE_HEAD)), params)
    print("queue formed; servicing the charger one bot at a time ...")

    # Phase 2: charge + park the queue head, shift the rest forward, repeat.
    # `park_goals` are bots that have charged and are heading to / sitting in
    # their parking slot; they stay in every convergence so they hold position
    # and the queue flows around them.
    park_goals: dict[str, Position] = {}
    while True:
        remaining = _order_by_distance(
            [b for b in _online(swarm) if b.address not in park_goals], QUEUE_HEAD
        )
        if not remaining:
            break
        head, rest = remaining[0], remaining[1:]

        goals = {head.address: CHARGER, **_queue_goals(rest), **park_goals}
        await converge(swarm, goals, params)  # head->charger, rest shift, parkers hold

        # Only treat the head as charged once it has actually reached the
        # charger: converge() can time out, or the head can drop offline, and a
        # bot nowhere near the charger must not be recorded as charged + parked.
        head = next((b for b in _online(swarm) if b.address == head.address), None)
        if (
            head is None
            or head.position is None
            or head.position.distance_to(CHARGER) > THRESHOLD
        ):
            print("   warning: queue head never reached the charger; stopping")
            break

        print(f"   charging {head.address} ({len(park_goals) + 1}/{total})")
        await _charge(head)

        # Hand the charged bot a parking slot; it drives there during the next
        # convergence, threading past the incoming bot under ORCA.
        park_goals[head.address] = PARK_ORIGIN + (0, len(park_goals) * PARK_SPACING)

    # Final convergence so the last-charged bot reaches its slot.
    await converge(swarm, park_goals, params)
    swarm.all.set_color(CHARGED_COLOR)
    await asyncio.sleep(1.0)  # let the colour commands flush before we exit
    print(f"done - all {len(park_goals)} bots charged and parked")


if __name__ == "__main__":
    Swarm.run(charging_station)
