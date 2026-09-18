# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The Mari TSCH schedules a gateway can be flashed with.

A gateway's schedule is a compile-time pointer in Mari's
`03app_gateway_net/main.c`, so each schedule is a separate net-core image and
changing schedule means reflashing the gateway. Nodes are never reflashed for
it: they adopt whatever schedule the gateway's beacon advertises.

Leaf module with no imports, so the CLI can name the schedules without
pulling in the flashing engine.
"""

# Names and node capacities mirror Mari's firmware/mari/all_schedules.c; keep
# them in step with it.
MARI_SCHEDULES = {
    "tiny": 10,
    "medium": 44,
    "big": 66,
    "huge": 102,
}


def net_image_name(schedule: str) -> str:
    """Net-core image file name for one schedule, as build-schedules.sh files it."""
    return f"03app_gateway_net-{schedule}.hex"


def describe_schedules() -> str:
    """The schedule names with their node capacities, for help and error text."""
    return ", ".join(
        f"{name} (up to {nodes} nodes)" for name, nodes in MARI_SCHEDULES.items()
    )
