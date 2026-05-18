# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot testbed` — provision, OTA-flash, start/stop/monitor.

Phase 1 mounts the upstream `swarmit` Click group verbatim under the
new name. Users get `dotbot testbed status|start|stop|flash|monitor|
reset|message|calibrate-lh2` with the same flags they have today.

The `provision` subcommand (one-time bootloader/netcore bringup) is
mounted from `dotbot-provision`. See plans/dotbot-unified-dx.md for
the long-term plan to fold both into `dotbot/testbed/`.
"""

from dotbot.cli._lazy import lazy_subcommand


def _load_swarmit_group():
    from swarmit.cli.main import main as swarmit_group

    return swarmit_group


def _load_provision_group():
    from dotbot_provision.cli import cli as provision_group

    return provision_group


cmd = lazy_subcommand(
    name="testbed",
    extra="testbed",
    package="swarmit",
    help=(
        "Testbed-side ops: provision, status, start/stop/monitor, OTA-flash. "
        "Wraps swarmit + dotbot-provision today; folds inline in Phase 6."
    ),
    loader=_load_swarmit_group,
)

# Best-effort: if both swarmit and dotbot-provision are installed, mount
# provision as a subgroup of testbed so the layout matches the planned
# `dotbot testbed provision ...` UX. If either is missing the stub above
# already handled the user message.
try:
    import click  # noqa: F401  (guard the attach below)

    if hasattr(cmd, "commands"):
        try:
            provision_group = _load_provision_group()
            cmd.add_command(provision_group, name="provision")
        except ImportError:
            # provision extra not installed; testbed itself still works.
            pass
except Exception:  # pylint: disable=broad-except
    pass
