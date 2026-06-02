# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The DotBot Swarm SDK.

`from dotbot.sdk import Swarm` (and, once wired, `from dotbot import Swarm`).
v1 implements the `http(s)://` connection to a running `dotbot run controller`;
the direct links and simulator backend land behind the same surface.
"""

from __future__ import annotations

from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.sdk.action import Action
from dotbot.sdk.bot import Bot
from dotbot.sdk.events import (
    BatteryUpdate,
    BotJoined,
    BotLeft,
    Event,
    ModeChanged,
    PositionUpdate,
)
from dotbot.sdk.fleet import Fleet
from dotbot.sdk.link import GatewayBudget, LinkProfile
from dotbot.sdk.position import Position
from dotbot.sdk.swarm import Swarm

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
]
