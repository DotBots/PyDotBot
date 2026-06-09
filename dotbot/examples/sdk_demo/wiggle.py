# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""A cute in-place wiggle: every bot rocks gently side to side while a rainbow
rolls across the fleet.

Each beat flips the twist direction with move_raw, so a bot rotates one way,
then back - it never leaves its spot, which makes this collision-safe on the
real testbed. Because the SDK paces the fleet broadcast to the link budget, the
flip ripples across the swarm as a soft wave instead of a rigid snap. Colours
advance as a rolling rainbow; only a rotating slice is recoloured each beat, so
the whole thing stays inside the ~80 cmd/s downlink budget even at ~67 bots.

Run once (default) or pass --loop to keep going, with a short pause between
rounds, until Ctrl-C:

    python -m dotbot.examples.sdk_demo.wiggle [--loop] [--swarm-url ...]

Tune the feel with the constants below: SPEED/BEAT set how far and how fast each
twist is (with fewer bots you can shorten BEAT for a snappier wiggle).
"""

import argparse
import asyncio

from dotbot.examples.sdk_demo._lib import hsv, settle
from dotbot.sdk import Swarm

SPEED = 75  # wheel PWM magnitude of each twist, 0..100
BEAT = 1.0  # seconds per twist (held until the next flip)
BEATS_PER_RUN = 8  # twists in one round before stopping
PAUSE = 2.0  # seconds of stillness between rounds in --loop mode
COLOR_SLICES = 6  # recolour 1/COLOR_SLICES of the fleet each beat (budget-aware)
HUE_STEP = 0.05  # rainbow advance per beat


async def _run_once(swarm: Swarm, bots: list, hue: float) -> float:
    """One round: BEATS_PER_RUN twists with a rolling rainbow. Returns the hue
    to continue from so successive rounds keep drifting through the spectrum."""
    n = len(bots)
    direction = 1
    for beat in range(BEATS_PER_RUN):
        swarm.all.move_raw(left=(0, direction * SPEED), right=(0, -direction * SPEED))
        direction = -direction
        for i, bot in enumerate(bots):
            if i % COLOR_SLICES == beat % COLOR_SLICES:
                bot.set_color(hsv(hue + i / n))
        hue = (hue + HUE_STEP) % 1.0
        await asyncio.sleep(BEAT)
    swarm.all.stop()
    return hue


async def wiggle(swarm: Swarm) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--loop", action="store_true", help="repeat with a pause until Ctrl-C"
    )
    opts, _ = parser.parse_known_args()

    await settle(swarm)
    bots = sorted(swarm, key=lambda b: b.address)
    print(f"wiggling {len(bots)} bots {'in a loop' if opts.loop else 'once'} ...")

    hue = 0.0
    try:
        while True:
            hue = await _run_once(swarm, bots, hue)
            if not opts.loop:
                break
            swarm.all.set_color("off")
            await asyncio.sleep(PAUSE)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(wiggle)
