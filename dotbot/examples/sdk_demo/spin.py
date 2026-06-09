# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Every bot spins in place for a few seconds, then stops.

A motion demo, but each bot turns about its own axis so its *position* barely
moves - low collision risk and a good first motion test on real hardware. The
two wheels are driven in opposite directions via move_raw, and the command is
re-sent periodically so a real bot's command timeout never stalls the spin.

    python -m dotbot.examples.sdk_demo.spin [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import settle
from dotbot.sdk import Swarm

SPEED = 70  # wheel PWM magnitude, 0..100
DURATION = 6.0  # seconds of spinning
RESEND = 0.5  # seconds between move_raw refreshes (command-timeout safe)


async def spin(swarm: Swarm) -> None:
    await settle(swarm)
    print(f"spinning {len(swarm)} bots in place for {DURATION:.0f}s ...")
    swarm.all.set_color("magenta")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DURATION
    try:
        while loop.time() < deadline:
            swarm.all.move_raw(left=(0, SPEED), right=(0, -SPEED))
            await asyncio.sleep(RESEND)
    finally:
        swarm.all.stop()
        swarm.all.set_color("off")
    print("done")


if __name__ == "__main__":
    Swarm.run(spin)
