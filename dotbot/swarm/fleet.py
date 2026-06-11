# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The `Fleet` - a handle over many bots that shares the single-bot verbs.

`swarm.all` and `swarm.select(pred)` return a `Fleet`; `swarm.all.set_color(...)`
reads like `bot.set_color(...)`. Over the HTTP connection a fleet verb fans out
one command per bot; the true one-frame broadcast (SDK plan, principle 1) is a
backend optimization that lands with the direct/mqtt connection, behind this
same surface.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from dotbot.swarm.bot import Bot


class Fleet:
    """A group of bots addressed together. Verbs fan out to each member."""

    def __init__(self, bots: Iterable[Bot]):
        self._bots: list[Bot] = list(bots)

    def __iter__(self) -> Iterator[Bot]:
        return iter(self._bots)

    def __len__(self) -> int:
        return len(self._bots)

    def set_color(
        self, color=None, *, red: int = 0, green: int = 0, blue: int = 0
    ) -> None:
        for bot in self._bots:
            bot.set_color(color, red=red, green=green, blue=blue)

    def move_raw(
        self, *, left: tuple[int, int] = (0, 0), right: tuple[int, int] = (0, 0)
    ) -> None:
        for bot in self._bots:
            bot.move_raw(left=left, right=right)

    def stop(self) -> None:
        for bot in self._bots:
            bot.stop()
