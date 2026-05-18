# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Root `dotbot` Click group with lazy subcommand loading.

Each subcommand lives in its own module under `dotbot.cli.<name>` and
exposes a `cmd` attribute. The root group lists subcommand names
eagerly (so `dotbot --help` is cheap) but only imports a subcommand's
module when the subcommand is actually invoked.

Why lazy: importing `dotbot.controller_app` pulls in `dotbot.server`
which mounts FastAPI StaticFiles at module load — fine for the
controller subcommand, but `dotbot fw --help` shouldn't pay that cost
(or fail when the frontend bundle isn't built).

Adding a new subcommand:
  1. Create `dotbot/cli/<name>.py` exposing `cmd = click.Command(...)`.
  2. Add an entry to `_SUBCOMMANDS` below: (cli-name, module path,
     short help string shown in `dotbot --help`).
  3. If the backend lives in an optional sibling package, use
     `dotbot.cli._lazy.lazy_subcommand` inside that module.
"""

import importlib
from typing import Optional, Tuple

import click

from dotbot import pydotbot_version

# (cli-name, dotted module path, short help shown by `dotbot --help`)
_SUBCOMMANDS: Tuple[Tuple[str, str, str], ...] = (
    (
        "controller",
        "dotbot.cli.controller",
        "Start the controller (adapter + REST/WS + dashboard).",
    ),
    (
        "sim",
        "dotbot.cli.sim",
        "Standalone simulator (equivalent to controller --adapter dotbot-simulator).",
    ),
    (
        "testbed",
        "dotbot.cli.testbed",
        "Testbed-side ops: provision, status, start/stop, OTA flash, monitor.",
    ),
    ("calibrate", "dotbot.cli.calibrate", "Run the LH2 calibration workflow."),
    ("demo", "dotbot.cli.demo", "Built-in research demos (qrkey phone bridge, ...)."),
    (
        "fw",
        "dotbot.cli.fw",
        "Firmware-developer workflow (scaffold/build/flash). MOCK in Phase 1.",
    ),
    ("keyboard", "dotbot.cli.keyboard", "Drive a DotBot from the keyboard (live)."),
    ("joystick", "dotbot.cli.joystick", "Drive a DotBot from a joystick (live)."),
)

_HELP_INDEX = {name: short for name, _, short in _SUBCOMMANDS}
_MODULE_INDEX = {name: module_path for name, module_path, _ in _SUBCOMMANDS}


class _LazyGroup(click.Group):
    """Click group that resolves subcommands by importing on demand."""

    def list_commands(self, ctx):
        return [name for name, _, _ in _SUBCOMMANDS]

    def get_command(self, ctx, cmd_name) -> Optional[click.Command]:
        module_path = _MODULE_INDEX.get(cmd_name)
        if module_path is None:
            return None
        module = importlib.import_module(module_path)
        return module.cmd

    def format_commands(self, ctx, formatter):
        """Render `dotbot --help` from the static help-string table.

        Overriding this avoids importing each subcommand module just to
        pull its short help line — that would defeat the lazy load.
        """
        rows = [(name, _HELP_INDEX[name]) for name, _, _ in _SUBCOMMANDS]
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


@click.group(
    cls=_LazyGroup,
    help="Control DotBots: drive robots, run testbed experiments, calibrate, demos.",
)
@click.version_option(
    version=pydotbot_version(),
    prog_name="dotbot",
    message="%(prog)s %(version)s",
)
def cli():
    pass
