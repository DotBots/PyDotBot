# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""A rainbow gradient that sweeps across the swarm, left to right.

Pure LED, collision-free. Each bot's hue is set by its position along the sweep
axis; the phase advances over time so the whole rainbow travels across the
physical field. A bot is only re-coloured when its hue *bucket* changes, so the
fleet is not re-sent every frame - the demo stays inside the downlink budget on
real hardware.

Set AXIS = "y" to sweep bottom-to-top instead.

    python -m dotbot.examples.sdk_demo.led_sweep [--swarm-url http://localhost:8000]
"""

import asyncio

from dotbot.examples.sdk_demo._lib import hsv, settle
from dotbot.swarm import Swarm

AXIS = "x"  # "x": sweep left->right, "y": sweep bottom->top
WAVELENGTHS = 1.5  # how many full rainbows span the field
SPEED = 0.03  # hue phase advanced per frame
FRAME = 0.1  # seconds per frame
BUCKETS = 18  # hue quantisation (fewer = coarser, less traffic)


async def led_sweep(swarm: Swarm) -> None:
    bots = await settle(swarm)
    if not bots:
        return

    coord = {b.address: (b.position.x if AXIS == "x" else b.position.y) for b in bots}
    lo, hi = min(coord.values()), max(coord.values())
    span = (hi - lo) or 1.0
    base = {a: ((c - lo) / span) * WAVELENGTHS for a, c in coord.items()}

    print(f"sweeping a rainbow across {len(bots)} bots ... (Ctrl-C to stop)")
    last_bucket: dict = {}
    phase = 0.0
    try:
        while True:
            for b in bots:
                bucket = int(((base[b.address] + phase) % 1.0) * BUCKETS)
                if last_bucket.get(b.address) != bucket:
                    last_bucket[b.address] = bucket
                    b.set_color(hsv(bucket / BUCKETS))
            phase = (phase + SPEED) % 1.0
            await asyncio.sleep(FRAME)
    finally:
        swarm.all.set_color("off")


if __name__ == "__main__":
    Swarm.run(led_sweep)
