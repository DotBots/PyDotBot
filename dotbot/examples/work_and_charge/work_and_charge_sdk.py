"""work_and_charge_sdk.py - the work-and-charge scenario on the Swarm SDK.

Each bot runs a per-bot supervisory controller (SCT, synthesized offline into
models/supervisor.yaml) that cycles it between a charge lane and a work lane:
drive to work (green) -> work -> energy low -> drive to charge (red) -> charge
-> energy high -> repeat, forever. The controller (controller.py) and the SCT
runtime (dotbot.examples.common.sct) are unchanged domain code.

This is the SDK rewrite of work_and_charge.py. Everything the old version
hand-rolled - the REST polling, the ws client, the waypoint/rgb pydantic
towers, the scipy KD-tree, the manual sleep loop - collapses into the Swarm:
the loop body is `async for _ in swarm.tick(...)`, and each bot streams one
fresh collision-avoided step per tick with `bot.goto(...)`.

Run a controller in simulator mode, then run this script:

    dotbot run controller --conn simulator --headless --bots 3 --layout grid
    python -m dotbot.examples.work_and_charge.work_and_charge_sdk
"""

import asyncio
import math
from pathlib import Path

from dotbot.examples.common.orca import (
    Agent,
    OrcaParams,
    compute_orca_velocity_for_agent,
)
from dotbot.examples.common.vec2 import Vec2
from dotbot.examples.work_and_charge.controller import THRESHOLD, Controller
from dotbot.swarm import Bot, Position, Swarm

DT = 0.2  # control-loop period (s) -> 5 Hz
BOT_RADIUS = 60  # mm, used for collision avoidance
MAX_SPEED = 200  # mm/s
ORCA_RANGE = 200  # mm, only avoid neighbours within this radius

# World-frame layout (mm): each bot shuttles along its own lane between the
# charge column (left) and the work column (right).
CHARGE_X = 500
WORK_X = 1500
LANE_BASE_Y = 500
LANE_SPACING = 500

# The supervisor FSM, resolved next to this example (not the cwd).
SCT_PATH = str(Path(__file__).resolve().parent / "models" / "supervisor.yaml")


def _online(swarm: Swarm) -> list[Bot]:
    return [b for b in swarm if b.is_online and b.position is not None]


async def _await_fleet(swarm: Swarm, *, timeout: float = 10.0) -> list[Bot]:
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
    """Steer toward the current goal at full speed. Unlike the charging-station
    converge, this never zeroes at the goal: the supervisor flips the goal
    (work <-> charge) the moment the bot is within threshold, so the fleet is
    perpetually in motion."""
    if goal is None or bot.position is None:
        return Vec2(x=0, y=0)
    dx = goal.x - bot.position.x
    dy = goal.y - bot.position.y
    if math.hypot(dx, dy) < 1.0:  # essentially on the goal; avoid a 0/0 heading
        return Vec2(x=0, y=0)
    direction = _direction_to_rad(bot.direction)
    angle_to_goal = math.atan2(dy, dx)
    delta = math.atan2(
        math.sin(angle_to_goal - direction), math.cos(angle_to_goal - direction)
    )
    final = direction + delta
    return Vec2(x=math.cos(final) * MAX_SPEED, y=math.sin(final) * MAX_SPEED)


def _setup_controllers(bots: list[Bot]) -> dict[str, Controller]:
    """One supervisor per bot; assign each a charge lane and a work lane by
    sorted address so the lanes are stable across runs."""
    controllers: dict[str, Controller] = {}
    for i, bot in enumerate(sorted(bots, key=lambda b: b.address)):
        lane_y = LANE_BASE_Y + i * LANE_SPACING
        controller = Controller(bot.address, SCT_PATH)
        controller.set_charge_waypoint(Position(CHARGE_X, lane_y))
        controller.set_work_waypoint(Position(WORK_X, lane_y))
        controllers[bot.address] = controller
    return controllers


async def work_and_charge(swarm: Swarm) -> None:
    bots = await _await_fleet(swarm)
    if not bots:
        print("no active bots")
        return
    print(f"{len(bots)} bots online; running work-and-charge (Ctrl-C to stop) ...")
    controllers = _setup_controllers(bots)
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)
    swarm.all.set_color("red")
    last_color: dict[str, tuple[int, int, int]] = {}

    async for _ in swarm.tick(rate_hz=1 / DT):
        active = [b for b in _online(swarm) if b.address in controllers]

        # Advance each bot's supervisor from its current position; the callbacks
        # set that bot's current goal (work or charge) and LED colour.
        goals: dict[str, Position] = {}
        for bot in active:
            controller = controllers[bot.address]
            controller.set_current_position(bot.position)
            controller.control_step()
            wp = controller.waypoint_current
            if wp is not None:
                goals[bot.address] = Position(wp.x, wp.y)

        agents = [
            Agent(
                id=b.address,
                position=Vec2(x=b.position.x, y=b.position.y),
                velocity=Vec2(x=0, y=0),
                radius=BOT_RADIUS,
                max_speed=MAX_SPEED,
                preferred_velocity=_preferred_vel(b, goals.get(b.address)),
            )
            for b in active
        ]
        by_address = {b.address: b for b in active}

        for agent in agents:
            neighbors = [
                n
                for n in agents
                if n.id != agent.id
                and math.hypot(
                    n.position.x - agent.position.x, n.position.y - agent.position.y
                )
                <= ORCA_RANGE
            ]
            if neighbors:
                velocity = compute_orca_velocity_for_agent(agent, neighbors, params)
            else:
                velocity = agent.preferred_velocity
            step = Vec2(x=velocity.x, y=velocity.y)

            goal = goals.get(agent.id)
            if goal is not None:  # clamp the step so it never overshoots the goal
                dist = math.hypot(goal.x - agent.position.x, goal.y - agent.position.y)
                length = math.hypot(step.x, step.y)
                if length > dist and length > 0:
                    step = Vec2(x=step.x * dist / length, y=step.y * dist / length)

            # Keep the target on the map (the simulator rejects negative coords).
            target_x = max(0.0, agent.position.x + step.x)
            target_y = max(0.0, agent.position.y + step.y)

            bot = by_address[agent.id]
            bot.goto(target_x, target_y, threshold=THRESHOLD)
            color = controllers[agent.id].led
            if last_color.get(agent.id) != color:  # only send the LED on a change
                bot.set_color(color)
                last_color[agent.id] = color


if __name__ == "__main__":
    Swarm.run(work_and_charge)
