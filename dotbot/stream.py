"""The controller stream: `/controller/ws/stream`.

A client gets a `hello`, then a `snapshot` of the fleet, then `delta` frames
carrying what changed since the last frame it was sent, and `event` frames
for state that is not a robot. It answers each frame with `{"ack": seq}`.

A client holds a cursor into the controller's state, never a queue of
messages: a frame is built from every robot field and trail point whose seq
is newer than the client's `sent_seq`, so a slow client receives fewer,
larger frames and its backlog is bounded by the fleet size.

A delta patch is an RFC 7396 merge patch over the REST object: each changed
field with its whole value (null once it has none), `last_seen`, and the
trail as `trail_append` (new points, oldest first) and `trail_reset`. A new
robot arrives as its whole REST object.

A robot's `pose` is its axle and heading only. The body drawn around it is
its `model`'s shape, which the `robot_models` event carries with every
snapshot: turned by the heading about the origin, then moved onto the axle.
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterator, List, Optional, Tuple

from fastapi import WebSocket, WebSocketDisconnect

from dotbot.logger import LOGGER
from dotbot.models import MAX_TRAIL_SIZE
from dotbot.poses import robot_body
from dotbot.ws_clients import close_websocket, write_buffer_size

PROTOCOL = 1
HZ_DEFAULT = 10
HZ_MIN = 1
HZ_MAX = 20
# The rate a client that has never acked is served at
UNACKED_HZ = 1
# Frames a client may hold unacked before it is sent nothing more
WINDOW = 2
SNAPSHOT_CHUNK = 100
# A client held back this long with changes pending gets a snapshot next
BEHIND_S = 5.0
# A client needing a second snapshot within this long of its last is closed
SNAPSHOT_INTERVAL_S = 10.0
# No ack, no completed send, or no drained write buffer for this long: closed
STALL_S = 15.0
# Bytes waiting in a client's transport beyond which it is sent nothing more
WRITE_BUFFER_LIMIT = 256 * 1024
TICK_S = 1 / HZ_MAX

_encode = json.JSONEncoder(separators=(",", ":")).encode


def encode(value) -> str:
    """Compact JSON, as every stream frame is encoded."""
    return _encode(value)


def _clamp(value: Optional[str], default: int, low: int, high: int) -> int:
    try:
        number = int(value) if value is not None else default
    except ValueError:
        number = default
    return max(low, min(high, number))


@dataclass
class StreamOptions:
    """What a client asked for in its query string, clamped."""

    hz: int = HZ_DEFAULT
    trail: int = 0
    since: Optional[int] = None
    run: Optional[str] = None

    @classmethod
    def from_query(cls, query) -> "StreamOptions":
        since = query.get("since")
        try:
            since = int(since) if since is not None else None
        except ValueError:
            since = None
        return cls(
            hz=_clamp(query.get("hz"), HZ_DEFAULT, HZ_MIN, HZ_MAX),
            trail=_clamp(query.get("trail"), 0, 0, MAX_TRAIL_SIZE),
            since=since,
            run=query.get("run"),
        )


# --- frames, built from the controller's state -------------------------------


def _dump(controller, address: str) -> dict:
    """A robot's fields as JSON values, without its trail or its null fields.

    Cached on its record until the robot next changes, so a tick dumps a
    moving robot once however many clients it is sent to. `last_seen`
    changes without a change being recorded, so it is read fresh.
    """
    dotbot = controller.dotbots[address]
    record = controller.records.get(address)
    key = controller.changed.get(address)
    if record is not None and key is not None and record.dump_seq == key:
        return record.dump
    body = dotbot.model_dump(
        mode="json", exclude_none=True, exclude={"trail", "body"}
    )
    if record is not None and key is not None:
        record.dump_seq, record.dump = key, body
    return body


def robot_object(
    controller, address: str, trail: int, upto: int, body: bool = False
) -> dict:
    """A robot as the REST list returns it, with its newest `trail` points
    no newer than seq `upto`, and with `body` the body its pose places."""
    dotbot = controller.dotbots[address]
    fields = {**_dump(controller, address), "last_seen": dotbot.last_seen}
    if body and dotbot.pose is not None:
        fields["body"] = robot_body(dotbot.model, dotbot.pose).model_dump(mode="json")
    record = controller.records.get(address)
    fields["trail"] = record.trail.json(trail, upto) if record and trail else []
    return fields


def robot_patch(controller, address: str, since: int, trail: int) -> dict:
    """The merge patch taking a robot from seq `since` to now."""
    record = controller.records.get(address)
    if record is None or record.created > since:
        return robot_object(controller, address, trail, controller.seq)
    dump = _dump(controller, address)
    patch = {
        name: dump.get(name)
        for name, rev in record.revs.items()
        if rev > since and name != "trail"
    }
    patch["last_seen"] = controller.dotbots[address].last_seen
    if trail and record.revs.get("trail", 0) > since:
        if record.trail_reset > since:
            patch["trail_reset"] = True
        points = record.trail.json(trail, after=since)
        if points:
            patch["trail_append"] = points
    return patch


def delta_frames(controller, since: int, trail: int) -> List[str]:
    """The frames taking a client from seq `since` to now: one delta when a
    robot changed, then one event per changed event key."""
    seq = controller.seq
    robots = {}
    changed = controller.changed
    for address in reversed(changed):
        if changed[address] <= since:
            break
        robots[address] = robot_patch(controller, address, since, trail)
    frames = []
    if robots:
        frames.append(_encode({"type": "delta", "seq": seq, "robots": robots}))
    frames.extend(event_frames(controller, since, seq))
    return frames


def event_frames(controller, since: int, seq: int) -> List[str]:
    return [
        _encode({"type": "event", "seq": seq, "event": name, "data": data})
        for event_seq, name, data in list(controller.events.values())
        if event_seq > since
    ]


def snapshot_frames(controller, trail: int) -> Tuple[int, Iterator[str]]:
    """The snapshot of now: its seq, and its parts built one at a time.

    A part built later still holds no trail point newer than the snapshot's
    seq, so the deltas after it never repeat a point; a field newer than it
    is sent again by the next delta, which is harmless.
    """
    seq = controller.seq
    addresses = sorted(controller.dotbots)
    parts = max(1, -(-len(addresses) // SNAPSHOT_CHUNK))

    def frames():
        for part in range(parts):
            chunk = addresses[part * SNAPSHOT_CHUNK : (part + 1) * SNAPSHOT_CHUNK]
            robots = [
                robot_object(controller, address, trail, seq)
                for address in chunk
                if address in controller.dotbots
            ]
            yield _encode(
                {
                    "type": "snapshot",
                    "seq": seq,
                    "part": part + 1,
                    "parts": parts,
                    "robots": robots,
                }
            )
        yield from event_frames(controller, 0, seq)

    return seq, frames()


def resumable(controller, since: Optional[int], run: Optional[str], trail) -> bool:
    """Whether a client that held the state at seq `since` of run `run` can
    be brought up to date with a delta rather than a snapshot."""
    if since is None or run != controller.run_id:
        return False
    if not 0 <= since <= controller.seq:
        return False
    return not trail or controller.max_evicted <= since


# --- clients -----------------------------------------------------------------


@dataclass
class StreamClient:
    """One stream client's cursor and flow-control state."""

    websocket: WebSocket
    options: StreamOptions
    sent_seq: int = 0
    acked_seq: int = 0
    acking: bool = False
    # (seq, sent at) of each frame batch not yet acked, oldest first
    unacked: Deque[Tuple[int, float]] = field(default_factory=deque)
    snapshot_pending: bool = True
    last_snapshot: Optional[float] = None
    # Since when the client has had changes pending that it could not be sent
    held_since: Optional[float] = None
    blocked_since: Optional[float] = None
    sending_since: Optional[float] = None
    task: Optional[asyncio.Task] = None
    due: float = 0.0
    closed: bool = False

    @property
    def interval(self) -> float:
        return 1 / (self.options.hz if self.acking else UNACKED_HZ)

    def ack(self, seq: int) -> None:
        if seq > self.sent_seq:
            return
        if not self.acking:
            self.acking = True
            self.due = 0.0
        self.acked_seq = max(self.acked_seq, seq)
        while self.unacked and self.unacked[0][0] <= seq:
            self.unacked.popleft()


class StreamHub:
    """Serves every stream client from one tick.

    Each tick, every client that is due, has room in its window and is not
    mid-send gets the frames taking it from its `sent_seq` to now. Clients
    with the same cursor and trail length share one encoding. Must be used
    from the event loop thread.
    """

    def __init__(self, controller):
        self.controller = controller
        self.clients: Dict[WebSocket, StreamClient] = {}
        # False leaves ticking to the caller, as a stepped clock does
        self.autostart = True
        self._task: Optional[asyncio.Task] = None
        self.logger = LOGGER.bind(context=__name__)

    def hello(self, client: StreamClient) -> str:
        return _encode(
            {
                "type": "hello",
                "protocol": PROTOCOL,
                "run": self.controller.run_id,
                "seq": self.controller.seq,
                "hz": client.options.hz,
                "unacked_hz": UNACKED_HZ,
                "window": WINDOW,
                "trail": client.options.trail,
                "acks": client.options.hz > UNACKED_HZ,
                "resumed": not client.snapshot_pending,
            }
        )

    def client(self, websocket: WebSocket, options: StreamOptions) -> StreamClient:
        """A client for `websocket`, resumed from `options.since` when it can be."""
        client = StreamClient(websocket, options)
        if resumable(self.controller, options.since, options.run, options.trail):
            client.sent_seq = client.acked_seq = options.since
            client.snapshot_pending = False
        return client

    def add(self, client: StreamClient) -> None:
        self.clients[client.websocket] = client
        if self.autostart and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run())

    def remove(self, websocket: WebSocket) -> None:
        client = self.clients.pop(websocket, None)
        if client is not None:
            client.closed = True
            if client.task is not None and client.sending_since is not None:
                client.task.cancel()

    def receive(self, websocket: WebSocket, text: str) -> None:
        """Take one message from a client; anything but an ack is ignored."""
        client = self.clients.get(websocket)
        if client is None:
            return
        try:
            message = json.loads(text)
        except ValueError:
            return
        seq = message.get("ack") if isinstance(message, dict) else None
        if isinstance(seq, int) and not isinstance(seq, bool):
            client.ack(seq)

    async def _run(self):
        while self.clients:
            await asyncio.sleep(TICK_S)
            self.tick(time.monotonic())

    def tick(self, now: float) -> None:
        shared: Dict[Tuple[int, int], List[str]] = {}
        for client in list(self.clients.values()):
            self._serve(client, now, shared)

    def _serve(self, client: StreamClient, now: float, shared) -> None:
        if client.closed:
            return
        pending = client.snapshot_pending or self.controller.seq > client.sent_seq
        if client.sending_since is not None:
            if now - client.sending_since > STALL_S:
                self.drop(client, "send stalled")
            elif pending:
                client.held_since = client.held_since or now
            return
        if client.unacked and now - client.unacked[0][1] > STALL_S:
            self.drop(client, "no ack")
            return
        if not client.acking:
            if write_buffer_size(client.websocket) > WRITE_BUFFER_LIMIT:
                client.blocked_since = client.blocked_since or now
                if now - client.blocked_since > STALL_S:
                    self.drop(client, "not reading")
                elif pending:
                    client.held_since = client.held_since or now
                return
            client.blocked_since = None
        if client.acking and len(client.unacked) >= WINDOW:
            if pending:
                client.held_since = client.held_since or now
            return
        # Half a tick early still counts: ticks jitter around the grid
        if not pending or now < client.due - TICK_S / 2:
            return
        if self._needs_snapshot(client, now):
            if not client.snapshot_pending and (
                client.last_snapshot is not None
                and now - client.last_snapshot < SNAPSHOT_INTERVAL_S
            ):
                self.drop(client, "fell behind twice")
                return
            seq, frames = snapshot_frames(self.controller, client.options.trail)
            client.snapshot_pending = False
            client.last_snapshot = now
        else:
            seq = self.controller.seq
            key = (client.sent_seq, client.options.trail)
            frames = shared.get(key)
            if frames is None:
                frames = shared[key] = delta_frames(
                    self.controller, client.sent_seq, client.options.trail
                )
        client.sent_seq = seq
        client.held_since = None
        # The grid point after the one this tick stands for, so clients at one
        # rate are served on the same ticks and share their frames
        client.due = (round(now / client.interval) + 1) * client.interval
        if client.acking:
            client.unacked.append((seq, now))
        client.sending_since = now
        client.task = asyncio.create_task(self._send(client, frames))

    def _needs_snapshot(self, client: StreamClient, now: float) -> bool:
        if client.snapshot_pending:
            return True
        if client.held_since is not None and now - client.held_since > BEHIND_S:
            return True
        return bool(client.options.trail) and (
            self.controller.max_evicted > client.sent_seq
        )

    async def _send(self, client: StreamClient, frames) -> None:
        try:
            for text in frames:
                if client.closed:
                    return
                await client.websocket.send_text(text)
                # A snapshot's parts are built one per turn of the loop
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect as exc:
            self.logger.debug("Stream client closed", code=exc.code)
            self.remove(client.websocket)
        except Exception as exc:  # pylint:disable=broad-exception-caught
            self.drop(client, f"send failed: {exc}")
        finally:
            client.sending_since = None

    def drop(self, client: StreamClient, reason: str) -> None:
        """Stop serving a client and close its websocket, so it reconnects."""
        if client.closed:
            return
        self.logger.warning("Dropping stream client", reason=reason)
        self.remove(client.websocket)
        asyncio.create_task(close_websocket(client.websocket))
