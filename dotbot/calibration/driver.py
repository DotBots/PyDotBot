# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The controller's side of a calibration session: one at a time, with events.

The capture loop itself is `CalibrationSession`; this drives it from async
routes. It owns the swarmit client, built when a session starts and rebuilt
when the robot changes, and a start with no fleet in reach still opens; it
turns every state change into exactly one WebSocket notification, in the
order the changes happened; and it routes a capture that arrives from the
robot's own button to the outstanding point.

The blocking capture runs in a worker thread. Progress is published from
there by handing the coroutine back to the loop and waiting for it, so the
notifications keep the order the reads arrived in.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Sequence

from dotbot.calibration.ota import CAPTURE_READS_DEFAULT
from dotbot.calibration.points import resolve_placement_points
from dotbot.calibration.push import PushRefused, gate_push, push_worklist
from dotbot.calibration.session import (
    CalibrationSession,
    SessionError,
    placement_dict,
)
from dotbot.logger import LOGGER
from dotbot.site import Site

# Seconds between two checks for a button press given up incomplete.
EXPIRED_PRESS_POLL_INTERVAL = 1.0

# The swarmit log-event tag a raw-count capture carries. Imported lazily so
# the swarmit protocol registry stays out of PyDotBot test collection.
_CAPTURE_TAG: int | None = None


def capture_tag() -> int:
    global _CAPTURE_TAG
    if _CAPTURE_TAG is None:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        _CAPTURE_TAG = LH2_CALIB_TAG
    return _CAPTURE_TAG


class SessionDriver:
    """One calibration session at a time, with its transport and its events.

    `client_factory` takes the device address and returns a swarmit client,
    injected so a test drives the whole loop without a fleet.
    """

    def __init__(
        self,
        client_factory: Callable[[str], Any],
        notify: Callable[[dict | None], Any],
        site: Site | None = None,
        stream_factory: Callable[[Any, str, Callable], Any] | None = None,
    ):
        self._client_factory = client_factory
        self._notify = notify
        self._stream_factory = stream_factory or _default_stream
        self.site = site or Site()
        self.session: CalibrationSession | None = None
        self.logger = LOGGER.bind(context=__name__)
        self._client: Any = None
        self._stream: Any = None
        self._device = ""
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._expiry_watch: asyncio.Task | None = None

    # -- state

    def state(self) -> dict | None:
        """The whole session, or None when there is none."""
        return None if self.session is None else self.session.as_dict()

    async def _emit(self) -> None:
        await self._notify(self.state())

    # -- the loop

    def preview(self, specs: Sequence[str]) -> dict:
        """What a start over `specs` would open on, without opening it.

        Same resolver as `start`, so the points a client shows before
        committing are the points it then captures.
        """
        placements = resolve_placement_points(list(specs), self.site.registry())
        return {
            "points": [
                placement_dict(index, placement)
                for index, placement in enumerate(placements)
            ],
            "reads": CAPTURE_READS_DEFAULT,
        }

    async def start(
        self,
        specs: Sequence[str],
        device: str = "",
        area: str = "",
        reads: int | None = None,
    ) -> dict:
        """Resolve the points and open a session with point 0 outstanding."""
        async with self._lock:
            self._close_stream()
            extra = {} if reads is None else {"reads": reads}
            session = CalibrationSession.resolve(list(specs), site=self.site, **extra)
            session.device = device.upper()
            session.area = area
            self.session = session
            self._loop = asyncio.get_running_loop()
            # Button captures come unrequested from any robot, so the stream
            # is listening from the start rather than from the first capture.
            await asyncio.to_thread(self._listen_for_buttons, session.device)
            if self._expiry_watch is None or self._expiry_watch.done():
                self._expiry_watch = asyncio.create_task(self._watch_expired_presses())
            await self._emit()
            return session.as_dict()

    async def capture(self, device: str = "") -> dict:
        """Take the outstanding point's reads from `device`, then advance."""
        async with self._lock:
            session = self._require()
            if device:
                session.device = device.upper()
            if not session.device:
                raise SessionError(
                    "no robot chosen: click one on the map, or name it in the "
                    "capture request"
                )
            loop = asyncio.get_running_loop()
            self._loop = loop
            stream = await asyncio.to_thread(self._ensure_stream, session.device)

            def on_progress(_point) -> None:
                asyncio.run_coroutine_threadsafe(self._emit(), loop).result()

            try:
                await asyncio.to_thread(session.capture, stream, on_progress)
                session.error = ""
            except TimeoutError as exc:
                session.error = str(exc)
            await self._emit()
            return session.as_dict()

    async def redo(self) -> dict:
        """Discard the last captured point's reads and re-open it."""
        async with self._lock:
            session = self._require()
            session.redo()
            session.error = ""
            await self._emit()
            return session.as_dict()

    async def save(self, tag: str = "") -> dict:
        """Solve, write the schema 2 file, and report its id and path."""
        async with self._lock:
            session = self._require()
            calibration = await asyncio.to_thread(session.save, tag or None)
            session.error = ""
            await self._emit()
            return {
                "id": calibration.id,
                "id8": calibration.id8,
                "path": session.saved_path,
                "session": session.as_dict(),
            }

    async def push(self, site_changed: bool = False) -> dict:
        """Check the fleet, send it the saved calibration, report who is still stale.

        Always the whole fleet, whichever robot the session captures from.
        """
        async with self._lock:
            session = self._require()
            payload = session.push_payload()
            client = await asyncio.to_thread(self._ensure_client, "")
            try:
                try:
                    check = await asyncio.to_thread(
                        gate_push, client, session.saved, site_changed
                    )
                except PushRefused as exc:
                    raise SessionError(f"push refused: {exc}") from exc
                await asyncio.to_thread(
                    client.send_lh2_calibration, payload, check.send_to
                )
                stale = await asyncio.to_thread(
                    push_worklist, client, session.saved, check.addresses
                )
            finally:
                await asyncio.to_thread(self._listen_for_buttons, "")
            await self._emit()
            return {
                "id": session.saved_id,
                "bytes": len(payload),
                "stale": stale,
            }

    async def abandon(self) -> dict:
        """Drop the session; nothing captured is written anywhere."""
        async with self._lock:
            self._close_stream()
            self.session = None
            await self._emit()
            return {"session": None}

    # -- the robot's own trigger

    def on_button_capture(self, capture: Any) -> Any:
        """A capture from the robot's own button, from the stream's reader thread.

        Stored on the event loop under the session lock; returns the
        concurrent future of that, or None when no session ever started.
        """
        if self._loop is None:
            self.logger.info(
                "LH2 button capture arrived with no calibration session open; dropped",
                device=capture.device,
            )
            return None
        return asyncio.run_coroutine_threadsafe(
            self._store_button_capture(capture), self._loop
        )

    async def _watch_expired_presses(self) -> None:
        """Report each button press given up incomplete, until the session ends."""
        while self.session is not None:
            await asyncio.sleep(EXPIRED_PRESS_POLL_INTERVAL)
            async with self._lock:
                if self.session is None or self._stream is None:
                    continue
                expired = self._stream.expired_presses()
                if not expired:
                    continue
                self.session.error = "; ".join(
                    f"incomplete capture from {addr} (press {press}): a chunk "
                    "never arrived; press again"
                    for addr, press in expired
                )
                await self._emit()

    async def _store_button_capture(self, capture: Any) -> None:
        """Point k, or dropped."""
        async with self._lock:
            session = self.session
            if session is None:
                self.logger.info(
                    "LH2 button capture arrived with no calibration session open; dropped",
                    device=capture.device,
                )
                return
            if capture.lost:
                self.logger.warning(
                    "LH2 button captures lost", device=capture.device, lost=capture.lost
                )
            try:
                point = session.store_reads(capture.reads)
            except SessionError as exc:
                session.error = str(exc)
            else:
                if point is None:
                    self.logger.info(
                        "LH2 button capture arrived with every point captured; dropped",
                        device=capture.device,
                    )
                    return
                session.error = ""
                self.logger.info(
                    "LH2 capture stored from the robot's own button",
                    device=capture.device,
                    point=point.index,
                )
            await self._emit()

    # -- transport

    def _require(self) -> CalibrationSession:
        if self.session is None:
            raise SessionError(
                "no calibration session is open; start one with the points to "
                "capture"
            )
        return self.session

    def _ensure_client(self, device: str) -> Any:
        if self._client is None or device != self._device:
            self._close_stream()
            if self._client is not None:
                self._client.__exit__(None, None, None)
                self._client = None
            self._client = self._client_factory(device)
            self._client.__enter__()
            self._device = device
        return self._client

    def _ensure_stream(self, device: str) -> Any:
        client = self._ensure_client(device)
        if self._stream is None:
            self._stream = self._stream_factory(client, device, self.on_button_capture)
            self._stream.__enter__()
        return self._stream

    def _listen_for_buttons(self, device: str) -> None:
        try:
            self._ensure_stream(device)
        except Exception as exc:  # a fleet out of reach is not a failure
            self.logger.warning(
                "Not listening for button captures until a capture reaches the fleet",
                error=str(exc),
            )

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.__exit__(None, None, None)
            self._stream = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the loop the reader thread must publish its events on."""
        self._loop = loop


def _default_stream(client: Any, device: str, on_button_capture: Callable) -> Any:
    from dotbot.calibration.ota import CaptureSession

    return CaptureSession(
        client, device, capture_tag(), on_button_capture=on_button_capture
    )
