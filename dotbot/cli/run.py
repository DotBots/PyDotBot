# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot run` — launch host-side processes (software on your computer).

The fourth top-level namespace. `fw` / `device` / `swarm` are *nouns* —
things you manage (artifacts, one board, the fleet). `run` is the *verb*:
the long-running software you start on your own machine — the control
plane, the gateway bridge, the simulator, the calibration workflow, the
demos, the teleop drivers. Every reference CLI keeps "launch a process"
as a top-level `run` (docker, cargo, ros2), so the asymmetry is correct,
not an inconsistency.

Note the two "gateway"s the namespaces disambiguate:
`dotbot device flash-gateway` flashes gateway firmware onto a board;
`dotbot run gateway` runs the host-side UART<->MQTT bridge process that
talks to that board. Different objects, named by their namespace.

Each subcommand is loaded lazily (see `_lazygroup`) so `dotbot run --help`
lists everything without importing `dotbot.controller_app` (FastAPI +
StaticFiles) or the teleop drivers' pygame/pynput.
"""

import click

from dotbot.cli._lazygroup import LazyGroup

# (cli-name, dotted module path exposing `cmd`, short help under `run --help`)
_RUN_SUBCOMMANDS = (
    (
        "controller",
        "dotbot.cli.controller",
        "Control plane + REST/WS + dashboard.",
    ),
    (
        "gateway",
        "dotbot.cli.gateway",
        "Host-side Mari gateway bridge (UART <-> MQTT).",
    ),
    (
        "simulator",
        "dotbot.cli.simulator",
        "Standalone simulator (≡ run controller --conn simulator).",
    ),
    (
        "lh2-calibration",
        "dotbot.cli.calibrate",
        "LH2 calibration: capture, apply, export (serial-side / single device).",
    ),
    (
        "demo",
        "dotbot.cli.demo",
        "Built-in research demos (qrkey phone bridge, ...).",
    ),
    ("keyboard", "dotbot.cli.keyboard", "Drive a DotBot from the keyboard (live)."),
    ("joystick", "dotbot.cli.joystick", "Drive a DotBot from a joystick (live)."),
)


@click.group(
    cls=LazyGroup,
    name="run",
    subcommands=_RUN_SUBCOMMANDS,
    help=(
        "Launch host-side processes: the controller (+ REST/WS + UI), the "
        "gateway bridge, a simulator, LH2 calibration, demos, and teleop "
        "drivers. These run on your computer; `fw` / `device` / `swarm` are "
        "the things you manage."
    ),
)
def cmd():
    pass
