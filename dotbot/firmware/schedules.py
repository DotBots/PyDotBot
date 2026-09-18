# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The Mari TSCH schedules a gateway can be flashed with.

A gateway's schedule is a compile-time pointer in Mari's
`03app_gateway_net/main.c`, so each schedule is a separate net-core image and
changing schedule means reflashing the gateway. Nodes are never reflashed for
it: they adopt whatever schedule the gateway's beacon advertises.

The names and capacities are marilib's, which mirror Mari's own schedule
tables, so a schedule added or renamed upstream shows up here with no edit.
"""

from marilib.model import SCHEDULES as _MARILIB_SCHEDULES

# Schedule name -> node capacity, smallest first so help text reads as a ladder.
MARI_SCHEDULES = {
    schedule["name"]: schedule["max_nodes"]
    for schedule in sorted(
        _MARILIB_SCHEDULES.values(), key=lambda schedule: schedule["max_nodes"]
    )
}


def net_image_name(schedule: str) -> str:
    """Net-core image file name for one schedule, as build-schedules.sh files it."""
    return f"03app_gateway_net-{schedule}.hex"


def describe_schedules() -> str:
    """The schedule names with their node capacities, for help and error text."""
    return ", ".join(
        f"{name} (up to {nodes} nodes)" for name, nodes in MARI_SCHEDULES.items()
    )
