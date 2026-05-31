# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Root `dotbot` Click group: four object-namespaces, lazily loaded.

The top level is exactly four groups, each one *kind of thing*:

  fw      — firmware artifacts (files in ./artifacts/, no hardware)
  device  — one connected device (cable / probe)
  swarm   — the fleet (radio / OTA)
  run     — host-side processes (software you launch on your computer)

Three are nouns (things you manage); `run` is the verb (the thing you do).
`dotbot --help` teaches the system in four lines.

Each group lives in its own module under `dotbot.cli.<name>` exposing a
`cmd` attribute. The root lists the groups eagerly (so `dotbot --help` is
cheap) but only imports a group's module when it's actually invoked — see
`dotbot.cli._lazygroup.LazyGroup`.

Adding a new top-level group:
  1. Create `dotbot/cli/<name>.py` exposing `cmd = click.Command(...)`.
  2. Add a `(cli-name, module path, short help)` entry to `_SUBCOMMANDS`.
  3. If the backend lives in an optional sibling package, wrap it with
     `dotbot.cli._lazy.lazy_subcommand` inside that module.
"""

import click

from dotbot import pydotbot_version
from dotbot.cli._lazygroup import LazyGroup

# (cli-name, dotted module path, short help shown by `dotbot --help`)
_SUBCOMMANDS = (
    (
        "fw",
        "dotbot.cli.fw",
        "Firmware artifacts (no hardware): build / fetch / list / make.",
    ),
    (
        "device",
        "dotbot.cli.device",
        "One connected device (cable/probe): flash an app/role, read info.",
    ),
    (
        "swarm",
        "dotbot.cli.swarm",
        "The fleet over the air: status, start/stop, OTA flash, monitor.",
    ),
    (
        "run",
        "dotbot.cli.run",
        "Host-side processes: controller, gateway, sim, calibration, demos, teleop.",
    ),
)


@click.group(
    cls=LazyGroup,
    subcommands=_SUBCOMMANDS,
    help=(
        "One CLI for the whole DotBot workflow: build and flash firmware, "
        "program and control a single robot, and run experiments over the air "
        "across a swarm - from one bot to a thousand."
    ),
)
@click.version_option(
    version=pydotbot_version(),
    prog_name="dotbot",
    message="%(prog)s %(version)s",
)
def cli():
    pass
