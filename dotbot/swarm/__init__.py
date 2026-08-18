# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The DotBot Swarm SDK.

`from dotbot.swarm import Swarm` (and, once wired, `from dotbot import Swarm`).
v1 implements the `http(s)://` connection to a running `dotbot run controller`;
the direct links and simulator backend land behind the same surface.
"""

from __future__ import annotations

from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.swarm.action import Action
from dotbot.swarm.avoid import bvc_waypoint, safe_hop
from dotbot.swarm.bot import Bot
from dotbot.swarm.events import (
    BatteryUpdate,
    BotJoined,
    BotLeft,
    Event,
    ModeChanged,
    PositionUpdate,
)
from dotbot.swarm.fleet import Fleet
from dotbot.swarm.link import GatewayBudget, LinkProfile
from dotbot.swarm.position import Position
from dotbot.swarm.swarm import Swarm

__all__ = [
    # active objects
    "Swarm",
    "Bot",
    "Fleet",
    "Action",
    # re-exported enums (the SDK's vocabulary for application + control mode)
    "ApplicationType",
    "ControlModeType",
    # value types
    "Position",
    "LinkProfile",
    "GatewayBudget",
    # events
    "Event",
    "BotJoined",
    "BotLeft",
    "PositionUpdate",
    "BatteryUpdate",
    "ModeChanged",
    # collision avoidance (the composable low-level rung; the high-level rung
    # is Swarm.connect(..., collision_avoidance=True))
    "bvc_waypoint",
    "safe_hop",
]
