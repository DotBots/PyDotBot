# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Discrete swarm events.

The SDK keeps two telemetry idioms separate (SDK plan, principle 4): discrete
change-events (this module) versus declared-rate streams
(`swarm.positions(rate_hz=...)`). `swarm.on(BotJoined, cb)` and `swarm.events()`
are keyed by these Event classes, never by stringly-typed names, so there is a
single event vocabulary that cannot typo or drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from dotbot.protocol import ControlModeType
from dotbot.sdk.position import Position


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for every swarm event.

    `address` is the bot the event concerns; `timestamp` is the host time
    (`time.monotonic()`-style) at which the backend emitted it.
    """

    address: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class BotJoined(Event):
    """A bot was seen for the first time, or re-appeared after being lost."""


@dataclass(frozen=True, slots=True)
class BotLeft(Event):
    """A bot stopped being heard (went inactive / lost)."""


@dataclass(frozen=True, slots=True)
class PositionUpdate(Event):
    """A bot reported a fresh LH2 position."""

    position: Position


@dataclass(frozen=True, slots=True)
class BatteryUpdate(Event):
    """A bot reported a fresh battery voltage (in volts)."""

    battery: float


@dataclass(frozen=True, slots=True)
class ModeChanged(Event):
    """A bot's control mode changed (MANUAL <-> AUTO)."""

    mode: ControlModeType


__all__ = [
    "Event",
    "BotJoined",
    "BotLeft",
    "PositionUpdate",
    "BatteryUpdate",
    "ModeChanged",
]
