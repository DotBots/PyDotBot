"""minimum_naming_game_with_motion_sdk.py - naming game + motion on the SDK.

The dynamic variant of the minimum naming game: the bots wander the arena
(walk straight, avoid each other and the walls) and play the naming game with
whoever is in range. They start out of communication range of each other, so
consensus depends on them mixing as they move. The per-bot agent
(controller_with_motion.py), its walk-and-avoid step (walk_avoid.py), and the
SCT runtime are unchanged domain code.

This is the SDK rewrite of minimum_naming_game_with_motion.py. The REST/ws
plumbing and scipy KD-tree collapse into the Swarm: each tick a bot advances
its supervisor, gets a walk vector, and streams it with `bot.goto(...)`. The
walk/avoid step still reads `neighbour.lh2_position`, so neighbours are passed
as lightweight wrappers exposing the bot's current Position.

Run a controller in simulator mode, then run this script:

    dotbot run controller --conn simulator --headless \\
        --simulator-init-state \\
        dotbot/examples/minimum_naming_game/init_state_with_motion.toml
    python -m dotbot.examples.minimum_naming_game.minimum_naming_game_with_motion_sdk
"""

import asyncio
import random
from pathlib import Path
from types import SimpleNamespace

from dotbot.examples.minimum_naming_game.controller_with_motion import Controller
from dotbot.sdk import Bot, Swarm

COMM_RANGE = 250  # mm, a bot can hear neighbours within this radius
MAX_SPEED = 300  # mm/s
ARENA = (2000, 2000)  # mm, the simulator map the walk-avoid keeps bots inside
RATE_HZ = 10  # control + naming-game steps per second
GOTO_THRESHOLD = 50  # mm, streaming-waypoint tolerance
MAX_STEPS = 4000  # safety bound if the swarm never fully converges

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


def _neighbours(bot: Bot, bots: list[Bot]) -> list[SimpleNamespace]:
    """Neighbours within COMM_RANGE, wrapped so the domain code can read
    `neighbour.address` and `neighbour.lh2_position.x/.y`."""
    return [
        SimpleNamespace(address=b.address, lh2_position=b.position)
        for b in bots
        if b.address != bot.address
        and bot.position.distance_to(b.position) <= COMM_RANGE
    ]


def _consensus_word(controllers: dict[str, Controller]) -> int | None:
    words = set()
    for c in controllers.values():
        if len(c.inventory) != 1:
            return None
        words.add(next(iter(c.inventory)))
    return next(iter(words)) if len(words) == 1 else None


async def minimum_naming_game(swarm: Swarm) -> None:
    bots = await _await_fleet(swarm)
    if not bots:
        print("no active bots")
        return
    print(f"{len(bots)} bots; naming game with motion (Ctrl-C to stop) ...")
    controllers = {
        b.address: Controller(b.address, SCT_PATH, 0.9 * MAX_SPEED, arena_limits=ARENA)
        for b in bots
    }
    last_color: dict[str, tuple[int, int, int]] = {}

    step = 0
    async for _ in swarm.tick(rate_hz=RATE_HZ):
        step += 1
        active = [b for b in _online(swarm) if b.address in controllers]
        for bot in active:
            controller = controllers[bot.address]
            controller.update_pose(bot.position)

            neighbours = _neighbours(bot, active)
            if neighbours:  # hear one random neighbour's current word
                heard = controllers[random.choice(neighbours).address]
                if heard.w_index != 0:
                    controller.received_word = heard.w_index
                    controller.new_word_received = True
                    controller.received_word_checked = False
            controller.neighbors = neighbours
            controller.control_step()  # naming game + LED + walk vector

            vx, vy = controller.vector
            target_x = min(ARENA[0], max(0.0, bot.position.x + vx))
            target_y = min(ARENA[1], max(0.0, bot.position.y + vy))
            bot.goto(target_x, target_y, threshold=GOTO_THRESHOLD)

            color = controller.led
            if last_color.get(bot.address) != color:  # only send on a change
                bot.set_color(color)
                last_color[bot.address] = color

        word = _consensus_word(controllers)
        if word is not None:
            print(f"consensus reached after {step} steps: word {word}")
            return
        if step % 50 == 0:
            settled = sum(len(c.inventory) == 1 for c in controllers.values())
            distinct = {
                next(iter(c.inventory))
                for c in controllers.values()
                if len(c.inventory) == 1
            }
            print(
                f"  step {step}: {settled}/{len(controllers)} bots hold one word, "
                f"{len(distinct)} distinct"
            )
        if step >= MAX_STEPS:
            print(f"stopped after {step} steps without full consensus")
            return


if __name__ == "__main__":
    Swarm.run(minimum_naming_game)
