# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The controller's side of a calibration session: one at a time, with events.

The capture loop itself is `CalibrationSession`; this drives it from async
routes. It owns the swarmit client, built on first capture rather than at
start so a controller with no fleet in reach still serves the routes; it
turns every state change into exactly one WebSocket notification, in the
order the changes happened; and it routes a capture that arrives from the
robot's own trigger to the outstanding point.

The blocking capture runs in a worker thread. Progress is published from
there by handing the coroutine back to the loop and waiting for it, so the
notifications keep the order the reads arrived in.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional, Sequence

from dotbot.calibration.session import CalibrationSession, SessionError
from dotbot.logger import LOGGER
from dotbot.site import Site

# The swarmit log-event tag a raw-count capture carries. Imported lazily so
# the swarmit protocol registry stays out of PyDotBot test collection.
_CAPTURE_TAG: Optional[int] = None


def capture_tag() -> int:
    global _CAPTURE_TAG
    if _CAPTURE_TAG is None:
        from swarmit.testbed.protocol import LH2_CALIB_TAG

        _CAPTURE_TAG = LH2_CALIB_TAG
    return _CAPTURE_TAG


class SessionDriver:
    """One calibration session at a time, with its transport and its events.

    `client_factory` takes the device address and returns a swarmit client;
    `stale_devices` reports which robots do not hold the calibration in use.
    Both are injected so a test drives the whole loop without a fleet.
    """

    def __init__(
        self,
        client_factory: Callable[[str], Any],
        notify: Callable[[Optional[dict]], Any],
        site: Optional[Site] = None,
        stale_devices: Optional[Callable[[], list[str]]] = None,
        stream_factory: Optional[Callable[[Any, str, Callable], Any]] = None,
    ):
        self._client_factory = client_factory
        self._notify = notify
        self._stale_devices = stale_devices or (lambda: [])
        self._stream_factory = stream_factory or _default_stream
        self.site = site or Site()
        self.session: Optional[CalibrationSession] = None
        self.logger = LOGGER.bind(context=__name__)
        self._client: Any = None
        self._stream: Any = None
        self._device = ""
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- state

    def state(self) -> Optional[dict]:
        """The whole session, or None when there is none."""
        return None if self.session is None else self.session.as_dict()

    async def _emit(self) -> None:
        await self._notify(self.state())

    # -- the loop

    async def start(
        self, specs: Sequence[str], device: str = "", area: str = ""
    ) -> dict:
        """Resolve the points and open a session with point 0 outstanding."""
        async with self._lock:
            self._close_stream()
            session = CalibrationSession.resolve(list(specs), site=self.site)
            session.device = device.upper()
            session.area = area
            self.session = session
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

    async def push(self) -> dict:
        """Send the saved calibration and report which robots are still stale."""
        async with self._lock:
            session = self._require()
            payload = session.push_payload()
            client = await asyncio.to_thread(self._ensure_client, session.device)
            await asyncio.to_thread(client.send_lh2_calibration, payload)
            await self._emit()
            return {
                "id": session.saved_id,
                "bytes": len(payload),
                "stale": self._stale_devices(),
            }

    async def abandon(self) -> dict:
        """Drop the session; nothing captured is written anywhere."""
        async with self._lock:
            self._close_stream()
            self.session = None
            await self._emit()
            return {"session": None}

    # -- the robot's own trigger

    def on_idle_records(self, records: list) -> None:
        """A capture that arrived without a request: point k, or dropped."""
        session = self.session
        if session is None:
            self.logger.info(
                "LH2 capture arrived with no calibration session open; dropped",
                records=len(records),
            )
            return
        point = session.store_records(records)
        if point is None:
            self.logger.info(
                "LH2 capture arrived with every point captured; dropped",
                records=len(records),
            )
            return
        self.logger.info(
            "LH2 capture stored from the robot's own trigger", point=point.index
        )
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._emit(), self._loop)

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
            self._client = self._client_factory(device)
            self._client.__enter__()
            self._device = device
        return self._client

    def _ensure_stream(self, device: str) -> Any:
        client = self._ensure_client(device)
        if self._stream is None:
            self._stream = self._stream_factory(
                client, device, self.on_idle_records
            )
            self._stream.__enter__()
        return self._stream

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.__exit__(None, None, None)
            self._stream = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the loop the reader thread must publish its events on."""
        self._loop = loop


def _default_stream(client: Any, device: str, on_idle_records: Callable) -> Any:
    from dotbot.calibration.ota import CaptureSession

    return CaptureSession(
        client, device, capture_tag(), on_idle_records=on_idle_records
    )
