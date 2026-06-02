# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""The `Action` handle returned by `Bot.move_to` / `Bot.follow`.

A motion command returns its handle immediately and starts running in the
background (SDK plan, principle 10): `a = bot.move_to(x, y)` fires it, `await a`
waits for arrival, `a.cancel()` stops waiting (it does not stop the bot). This
lets a student write `await bot.move_to(...)` and a researcher compose
non-blocking actions across a fleet with `asyncio.gather(...)`.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable


class Action:
    """A running motion command. Awaitable; resolves when the bot arrives."""

    def __init__(self, coro: Awaitable[None]):
        # Scheduling here (not on await) is what makes the command fire
        # immediately and lets several run concurrently under gather().
        self._task = asyncio.ensure_future(coro)

    def __await__(self):
        return self._task.__await__()

    def cancel(self) -> None:
        """Stop waiting for arrival. Does not stop the bot - call `bot.stop()`
        for that."""
        self._task.cancel()

    def done(self) -> bool:
        return self._task.done()
