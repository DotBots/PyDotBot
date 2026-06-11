# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The Swarm SDK's 2D position value type.

`Position` is intentionally distinct from the wire/controller
`DotBotLH2Position` (a pydantic model): the SDK exposes a lightweight, immutable
value that supports vector arithmetic, so a planner can write
`bot.position + step` directly (see the charging_station rewrite in the SDK
plan). The backend maps a `DotBotLH2Position` onto a `Position`; the SDK never
re-uses the pydantic model on its hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Iterator


def _xy(other: Position | tuple[float, float]) -> tuple[float, float]:
    """Coerce a Position or any (x, y) sequence (tuple, list, numpy array) to a
    plain float pair."""
    if isinstance(other, Position):
        return other.x, other.y
    x, y = other
    return float(x), float(y)


@dataclass(frozen=True, slots=True)
class Position:
    """An immutable 2D position in millimetres, in the LH2 map frame.

    Treated as both a point and a vector: adding/subtracting another position
    (or any `(x, y)` pair) yields a new `Position`, so `bot.position + step`
    reads directly when `step` is an offset from a planner.
    """

    x: float
    y: float

    def __add__(self, other: Position | tuple[float, float]) -> Position:
        ox, oy = _xy(other)
        return Position(self.x + ox, self.y + oy)

    def __sub__(self, other: Position | tuple[float, float]) -> Position:
        ox, oy = _xy(other)
        return Position(self.x - ox, self.y - oy)

    def __mul__(self, scalar: float) -> Position:
        return Position(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y

    def distance_to(self, other: Position | tuple[float, float]) -> float:
        """Euclidean distance in millimetres to another position."""
        ox, oy = _xy(other)
        return hypot(self.x - ox, self.y - oy)

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)
