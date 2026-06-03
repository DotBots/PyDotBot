# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The simplest DotBot demo: drive one bot in a circle over the REST API.

No pydotbot internals - just HTTP with `requests`, so it doubles as a
copy-pasteable template for your own scripts. Start a controller
(e.g. `dotbot run simulator -w`), then run `dotbot run demo circle`.
"""

import time

import click
import requests


@click.command(name="circle", help="Drive one bot in a circle (bare-REST demo).")
@click.option(
    "--base",
    default="http://localhost:8000",
    show_default=True,
    help="Controller REST base URL.",
)
@click.option(
    "--seconds",
    "-t",
    default=5.0,
    show_default=True,
    help="How long to drive, in seconds.",
)
def main(base, seconds):
    """Drive the first DotBot the controller sees in a circle, then stop."""
    try:
        bots = requests.get(f"{base}/controller/dotbots", timeout=5).json()
    except requests.RequestException as exc:
        raise click.ClickException(
            f"Cannot reach a controller at {base} ({exc}). "
            "Start one first, e.g. `dotbot run simulator -w`."
        ) from exc
    if not bots:
        raise click.ClickException(
            f"No DotBots at {base}. The simulator (`dotbot run simulator -w`) "
            "spawns one; on hardware, flash and connect a bot first."
        )

    address = bots[0]["address"]
    move = f"{base}/controller/dotbots/{address}/0/move_raw"
    click.echo(f"Driving {address} in a circle for {seconds:.0f}s (Ctrl-C to stop)...")

    # left_y and right_y are the two wheel speeds; unequal -> the bot turns.
    end = time.time() + seconds
    try:
        while time.time() < end:
            requests.put(
                move, json={"left_x": 0, "left_y": 60, "right_x": 0, "right_y": 30}
            )
            time.sleep(0.1)
    finally:
        # always stop the motors, even on Ctrl-C
        requests.put(move, json={"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0})
    click.echo("Done.")
