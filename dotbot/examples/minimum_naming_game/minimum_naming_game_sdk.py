"""minimum_naming_game_sdk.py - the minimum naming game on the Swarm SDK.

A field of stationary bots play the minimum naming game: each step a bot hears
one random neighbour within COMM_RANGE, folds that word into its inventory, and
shows its word as an LED colour (off until it holds a single word). Through
purely local exchange the swarm converges on one word - every bot the same
colour. The per-bot agent (controller.py) and the SCT runtime
(dotbot.examples.common.sct) are unchanged domain code.

This is the SDK rewrite of minimum_naming_game.py. The REST polling, the ws
client, the scipy KD-tree and the rgb pydantic tower collapse into the Swarm:
the loop is `async for _ in swarm.tick(...)`, neighbours are a plain range
query, and a colour goes out only when a bot's word actually changes.

Run a controller in simulator mode, then run this script:

    dotbot run controller --conn simulator --headless \\
        --simulator-init-state \\
        dotbot/examples/minimum_naming_game/init_state.toml
    python -m dotbot.examples.minimum_naming_game.minimum_naming_game_sdk
"""

import asyncio
import random
from pathlib import Path

from dotbot.examples.minimum_naming_game.controller import Controller
from dotbot.swarm import Bot, Swarm

COMM_RANGE = 250  # mm, a bot can hear neighbours within this radius
RATE_HZ = 20  # naming-game steps per second
MAX_STEPS = 2000  # safety bound if the swarm never fully converges

# The naming-game supervisor FSM, resolved next to this example (not the cwd).
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


def _neighbours(bot: Bot, bots: list[Bot]) -> list[Bot]:
    return [
        b
        for b in bots
        if b.address != bot.address
        and bot.position.distance_to(b.position) <= COMM_RANGE
    ]


def _consensus_word(controllers: dict[str, Controller]) -> int | None:
    """The single word the whole swarm agrees on, or None if not yet converged
    (some bot holds zero or several words, or two bots disagree)."""
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
    print(f"{len(bots)} bots; playing the minimum naming game ...")
    controllers = {b.address: Controller(b.address, SCT_PATH) for b in bots}
    last_color: dict[str, tuple[int, int, int]] = {}

    step = 0
    async for _ in swarm.tick(rate_hz=RATE_HZ):
        step += 1
        active = [b for b in _online(swarm) if b.address in controllers]
        for bot in active:
            controller = controllers[bot.address]
            controller.position = bot.position
            controller.direction = bot.direction

            neighbours = _neighbours(bot, active)
            if neighbours:  # hear one random neighbour's current word
                heard = controllers[random.choice(neighbours).address]
                if heard.w_index != 0:
                    controller.received_word = heard.w_index
                    controller.new_word_received = True
                    controller.received_word_checked = False
            controller.neighbors = neighbours
            controller.control_step()

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
