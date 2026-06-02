# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The DotBot Swarm SDK.

The value types (`Position`, the event classes, the link budget) are in place;
the active objects (`Swarm`, `Bot`, `Fleet`, `Action`) and the connection
backends land next, after which `from dotbot import Swarm` is wired at the
package top level.
"""

from __future__ import annotations

from dotbot.protocol import ApplicationType, ControlModeType
from dotbot.sdk.events import (
    BatteryUpdate,
    BotJoined,
    BotLeft,
    Event,
    ModeChanged,
    PositionUpdate,
)
from dotbot.sdk.link import GatewayBudget, LinkProfile
from dotbot.sdk.position import Position

__all__ = [
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
