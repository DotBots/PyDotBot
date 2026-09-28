"""Bounded handoff of received frames from a gateway thread to the event loop."""

import asyncio
import itertools
import threading
import time
from collections import OrderedDict
from typing import Callable, Optional

from dotbot_utils.protocol import Frame

from dotbot.logger import LOGGER
from dotbot.protocol import PayloadType

# Periodic full-state reports: a newer one from the same robot supersedes one
# still waiting
STATE_PAYLOAD_TYPES = frozenset(
    (
        PayloadType.ADVERTISEMENT,
        PayloadType.DOTBOT_ADVERTISEMENT,
        PayloadType.GPS_POSITION,
        PayloadType.SAILBOT_DATA,
    )
)
MAX_EVENTS_DEFAULT = 1024
MAX_STATES_DEFAULT = 16384
LOG_INTERVAL_S = 10.0


class FrameInbox:
    """Frames put from any thread, handed to one handler on the event loop.

    A state frame waiting for the loop is replaced by a newer one from the
    same robot, in its place in line; any other frame waits its turn, and
    beyond `max_events` of those waiting the newest is dropped. What waits is
    therefore bounded by the fleet, not by how far the loop has fallen behind.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        max_events: int = MAX_EVENTS_DEFAULT,
        max_states: int = MAX_STATES_DEFAULT,
    ):
        self._loop = loop
        self._max_events = max_events
        self._max_states = max_states
        self._lock = threading.Lock()
        self._pending: OrderedDict = OrderedDict()
        self._events = 0
        self._ids = itertools.count()
        self._scheduled = False
        self._ready = asyncio.Event()
        self.coalesced = 0
        self.dropped = 0
        self._logged = (0, 0)
        self._logged_at = time.monotonic()

    def __len__(self) -> int:
        return len(self._pending)

    def put(self, frame) -> None:
        """Hand a frame to the loop; safe from any thread."""
        key = _state_key(frame)
        with self._lock:
            if key is None:
                if self._events >= self._max_events:
                    self.dropped += 1
                    return
                self._pending[next(self._ids)] = frame
                self._events += 1
            elif key in self._pending:
                self._pending[key] = frame
                self.coalesced += 1
                return
            elif len(self._pending) - self._events >= self._max_states:
                self.dropped += 1
                return
            else:
                self._pending[key] = frame
            if self._scheduled:
                return
            self._scheduled = True
        self._loop.call_soon_threadsafe(self._ready.set)

    def _take(self) -> list:
        with self._lock:
            frames = list(self._pending.values())
            self._pending.clear()
            self._events = 0
            self._scheduled = False
        return frames

    async def run(self, handler: Callable) -> None:
        """Call `handler` with every frame, in order, forever; a frame the
        handler raises on is logged and skipped."""
        while True:
            await self._ready.wait()
            self._ready.clear()
            for frame in self._take():
                try:
                    handler(frame)
                except Exception:  # pylint: disable=broad-exception-caught
                    LOGGER.exception("Frame not handled", frame=repr(frame)[:200])
            self._log_losses()
            # A full inbox would otherwise keep the loop to itself
            await asyncio.sleep(0)

    def _log_losses(self) -> None:
        now = time.monotonic()
        if now - self._logged_at < LOG_INTERVAL_S:
            return
        coalesced = self.coalesced - self._logged[0]
        dropped = self.dropped - self._logged[1]
        self._logged = (self.coalesced, self.dropped)
        self._logged_at = now
        if coalesced or dropped:
            LOGGER.warning(
                "Controller behind the gateway: older frames skipped",
                coalesced=coalesced,
                dropped=dropped,
                interval_s=LOG_INTERVAL_S,
            )


def _state_key(frame) -> Optional[tuple]:
    if not isinstance(frame, Frame):
        return None
    payload_type = frame.packet.payload_type
    if payload_type not in STATE_PAYLOAD_TYPES:
        return None
    return (frame.header.source, payload_type)
