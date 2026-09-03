"""Broker plumbing and controller client shared by the playground demos.

A demo script is a declaration and a loop: it announces itself on the broker
with the inputs it wants, the playground page renders that announcement and
sends back what a person does, and the script drives the bots through the
controller the way every other example already does.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import click
import httpx
import numpy as np
import websockets
from gmqtt import Client as MQTTClient
from gmqtt import Message as MQTTMessage

DEFAULT_BROKER = "mqtt://localhost:1883"
DEFAULT_CONTROLLER = "http://localhost:8000"

#: Topics live under `dotbot/`, the DotBot layer; marilib keeps `/mari/`.
TOPIC_ROOT = "dotbot"

#: Keepalive, seconds. The broker publishes the will after 1.5x this, so it is
#: what decides how long a killed demo lingers in the page's rail.
KEEPALIVE_S = 5

#: DotBot application id the controller's REST paths take. 0 is DotBot.
APPLICATION_DOTBOT = 0


# --------------------------------------------------------------- announcement


def slider(
    control_id: str,
    minimum: float,
    maximum: float,
    value: float,
    *,
    step: Optional[float] = None,
    label: Optional[str] = None,
    unit: Optional[str] = None,
) -> Dict[str, Any]:
    """A slider control, in the announcement's schema."""
    decl: Dict[str, Any] = {
        "id": control_id,
        "type": "slider",
        "min": minimum,
        "max": maximum,
        "value": value,
    }
    if step is not None:
        decl["step"] = step
    if label is not None:
        decl["label"] = label
    if unit is not None:
        decl["unit"] = unit
    return decl


def toggle(
    control_id: str, value: bool, *, label: Optional[str] = None
) -> Dict[str, Any]:
    """A toggle control."""
    decl: Dict[str, Any] = {"id": control_id, "type": "toggle", "value": value}
    if label is not None:
        decl["label"] = label
    return decl


def button(control_id: str, *, label: Optional[str] = None) -> Dict[str, Any]:
    """A button control, which sends one input and carries no value."""
    decl: Dict[str, Any] = {"id": control_id, "type": "button"}
    if label is not None:
        decl["label"] = label
    return decl


def select(
    control_id: str,
    options: Sequence[str],
    value: str,
    *,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """A select control."""
    decl: Dict[str, Any] = {
        "id": control_id,
        "type": "select",
        "options": list(options),
        "value": value,
    }
    if label is not None:
        decl["label"] = label
    return decl


def text_field(
    control_id: str,
    *,
    value: str = "",
    placeholder: Optional[str] = None,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """A text control."""
    decl: Dict[str, Any] = {"id": control_id, "type": "text", "value": value}
    if placeholder is not None:
        decl["placeholder"] = placeholder
    if label is not None:
        decl["label"] = label
    return decl


# ------------------------------------------------------------------ overlays


def overlay_point(
    x: float,
    y: float,
    *,
    r: Optional[float] = None,
    label: Optional[str] = None,
    color: Optional[str] = None,
) -> Dict[str, Any]:
    """A ring on the arena. `color` is a role the page maps to a token."""
    item: Dict[str, Any] = {"type": "point", "x": round(x, 1), "y": round(y, 1)}
    if r is not None:
        item["r"] = round(r, 1)
    if label is not None:
        item["label"] = label
    if color is not None:
        item["color"] = color
    return item


def overlay_polyline(
    points: Sequence[Point], *, closed: bool = False, color: Optional[str] = None
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "type": "polyline",
        "points": [{"x": round(p.x, 1), "y": round(p.y, 1)} for p in points],
    }
    if closed:
        item["closed"] = True
    if color is not None:
        item["color"] = color
    return item


def overlay_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    label: Optional[str] = None,
    fill: bool = False,
    color: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "type": "rect",
        "x": round(x, 1),
        "y": round(y, 1),
        "w": round(w, 1),
        "h": round(h, 1),
    }
    if label is not None:
        item["label"] = label
    if fill:
        item["fill"] = True
    if color is not None:
        item["color"] = color
    return item


def overlay_label(
    x: float, y: float, text: str, *, color: Optional[str] = None
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "type": "label",
        "x": round(x, 1),
        "y": round(y, 1),
        "text": text,
    }
    if color is not None:
        item["color"] = color
    return item


def overlay_badge(
    address: str, text: str, *, color: Optional[str] = None
) -> Dict[str, Any]:
    """A ring and a word on one bot, which the page finds by address."""
    item: Dict[str, Any] = {"type": "badge", "address": address, "text": text}
    if color is not None:
        item["color"] = color
    return item


@dataclass
class Announcement:
    """What a script publishes, retained, on `dotbot/<swarm>/apps/<name>`."""

    name: str
    title: str
    hint: str
    inputs: List[str] = field(default_factory=list)
    controls: List[Dict[str, Any]] = field(default_factory=list)
    overlay: bool = False
    #: The script republishes fleet positions on its `/out` topic.
    positions: bool = False
    #: The topics are wrapped by qrkey and a PIN is needed.
    protected: bool = False
    #: A URL when the script brings its own front end.
    ui: Optional[str] = None

    def payload(self) -> bytes:
        return json.dumps(asdict(self)).encode()

    def defaults(self) -> Dict[str, Any]:
        """The declared value of every control that carries one."""
        return {c["id"]: c["value"] for c in self.controls if "value" in c}


def app_topics(root: str, swarm: str, name: str) -> Tuple[str, str, str]:
    """The announce, input and output topics of one app."""
    base = f"{root}/{swarm}/apps/{name}"
    return base, f"{base}/in", f"{base}/out"


def clear_message(announce_topic: str) -> MQTTMessage:
    """
    The retained announcement, emptied.

    An empty retained payload deletes the retained message rather than
    storing one, so this is both the will the broker sends when a demo dies
    and what the demo publishes when it exits cleanly. Either way the page
    drops the entry from its rail.
    """
    return MQTTMessage(announce_topic, b"", qos=1, retain=True)


# ---------------------------------------------------------------- page inputs


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class PointerSample:
    """A pointer or finger over the arena; `at` is None when it left."""

    client: str
    at: Optional[Point]


@dataclass(frozen=True)
class Rect:
    """An axis-aligned region in arena mm, width and height positive."""

    x: float
    y: float
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> Point:
        return Point(self.x + self.w / 2, self.y + self.h / 2)


@dataclass(frozen=True)
class ControlChange:
    client: str
    id: str
    value: Any


@dataclass(frozen=True)
class Action:
    """A button press, which carries no value."""

    client: str
    id: str


@dataclass(frozen=True)
class GoalsInput:
    """Every pin on the map, in the order they were placed."""

    client: str
    points: List[Point]


@dataclass(frozen=True)
class RectsInput:
    """Every rectangle on the map."""

    client: str
    rects: List[Rect]


@dataclass(frozen=True)
class TextInput:
    client: str
    text: str


def _point(raw: Any) -> Optional[Point]:
    try:
        return Point(float(raw["x"]), float(raw["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _rect(raw: Any) -> Optional[Rect]:
    try:
        return Rect(
            float(raw["x"]), float(raw["y"]), float(raw["w"]), float(raw["h"])
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_input(payload: Any) -> Any:
    """
    One message off the `/in` topic, as the object a callback wants.

    Every kind the page sends comes back typed; anything else comes back as
    the plain dict it arrived as, so a demo can read a kind this helper does
    not model yet. Junk returns None.
    """
    if isinstance(payload, (bytes, bytearray, str)):
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return None
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    client = str(payload.get("client", ""))
    if kind == "pointer":
        at = payload.get("at")
        if at is None:
            return PointerSample(client=client, at=None)
        point = _point(at)
        return None if point is None else PointerSample(client=client, at=point)
    if kind == "control":
        if "id" not in payload:
            return None
        return ControlChange(
            client=client, id=str(payload["id"]), value=payload.get("value")
        )
    if kind == "action":
        if "id" not in payload:
            return None
        return Action(client=client, id=str(payload["id"]))
    if kind == "goals":
        raw = payload.get("points")
        if not isinstance(raw, list):
            return None
        points = [_point(p) for p in raw]
        if any(p is None for p in points):
            return None
        return GoalsInput(client=client, points=[p for p in points if p is not None])
    if kind == "rects":
        raw = payload.get("rects")
        if not isinstance(raw, list):
            return None
        rects = [_rect(r) for r in raw]
        if any(r is None for r in rects):
            return None
        return RectsInput(client=client, rects=[r for r in rects if r is not None])
    if kind == "text":
        text = payload.get("text")
        return None if not isinstance(text, str) else TextInput(client=client, text=text)
    if kind is None:
        return None
    return payload


# ------------------------------------------------------------- assignment


def _greedy(cost: np.ndarray) -> np.ndarray:
    """Nearest pair first, then the nearest of what is left, until none is."""
    rows, columns = cost.shape
    work = cost.astype(float, copy=True)
    assign = np.zeros(rows, dtype=int)
    for _ in range(rows):
        row, column = divmod(int(np.argmin(work)), columns)
        assign[row] = column
        work[row, :] = np.inf
        work[:, column] = np.inf
    return assign


def _swap_passes(cost: np.ndarray, assign: np.ndarray, max_passes: int) -> np.ndarray:
    """
    Exchange the targets of two bots while that shortens the pair.

    Greedy leaves crossings behind - the bot picked early takes a target a
    later one was much closer to - and every such crossing is one exchange
    away from being gone.
    """
    n = len(assign)
    rows = np.arange(n)
    for _ in range(max_passes):
        held = cost[rows, assign]
        swapped = cost[:, assign]
        gain = np.triu(held[:, None] + held[None, :] - swapped - swapped.T, 1)
        pairs = np.argwhere(gain > 1e-9)
        if len(pairs) == 0:
            break
        # At most n/2 exchanges can apply in one pass, so only the best n
        # candidates are worth walking.
        best = np.argsort(-gain[pairs[:, 0], pairs[:, 1]])[:n]
        moved = np.zeros(n, dtype=bool)
        for i, j in pairs[best]:
            if moved[i] or moved[j]:
                continue
            assign[i], assign[j] = assign[j], assign[i]
            moved[i] = moved[j] = True
    return assign


def assign_targets(
    sources: Any, targets: Any, *, max_passes: int = 8
) -> np.ndarray:
    """
    One distinct target per source, by squared distance.

    Greedy nearest-first followed by swap passes: not optimal, but within a
    few percent of it and fast enough to run every time the swarm is
    re-aimed. Returns a target index per source, in source order. There must
    be at least as many targets as sources.
    """
    src = np.asarray(sources, dtype=float).reshape(-1, 2)
    dst = np.asarray(targets, dtype=float).reshape(-1, 2)
    if len(src) == 0:
        return np.zeros(0, dtype=int)
    if len(dst) < len(src):
        raise ValueError(f"{len(src)} sources need {len(src)} targets, got {len(dst)}")
    cost = ((src[:, None, :] - dst[None, :, :]) ** 2).sum(axis=2)
    return _swap_passes(cost, _greedy(cost), max_passes)


# ------------------------------------------------------------ controller side


@dataclass
class Bot:
    """One robot as a demo needs it: where it is and which way it faces."""

    address: str
    x: float
    y: float
    heading: float
    application: int = APPLICATION_DOTBOT
    #: Last reported battery voltage, volts.
    battery: float = 0.0


class CommandQueue:
    """
    Latest-target-wins, one slot per (bot, command kind).

    A follow loop recomputes a target far faster than the swarm can act on
    one, so queueing every command would build a backlog the robots run
    minutes behind. Overwriting the slot keeps only the target that is still
    true when the flush comes round.
    """

    def __init__(self) -> None:
        self._pending: Dict[Tuple[str, str], Tuple[str, str, Any]] = {}

    def put(self, address: str, kind: str, payload: Any) -> None:
        self._pending[(address, kind)] = (address, kind, payload)

    def drain(self) -> List[Tuple[str, str, Any]]:
        """Every pending command in insertion order, leaving the queue empty."""
        out = list(self._pending.values())
        self._pending.clear()
        return out

    def __len__(self) -> int:
        return len(self._pending)


class ControllerClient:
    """
    The controller as a demo uses it: positions in, commands out.

    Positions arrive on `/controller/ws/status`, which pushes an update per
    advertisement; the REST endpoints take the commands. Commands are
    coalesced per bot and flushed at a fixed rate.
    """

    def __init__(
        self, base_url: str = DEFAULT_CONTROLLER, command_rate_hz: float = 5.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.command_rate_hz = command_rate_hz
        self.bots: Dict[str, Bot] = {}
        self.swarm_id: str = "0000"
        self.map_size: Tuple[int, int] = (2000, 2000)
        self._queue = CommandQueue()
        self._http = httpx.AsyncClient(timeout=5.0)
        self._tasks: List[asyncio.Task] = []
        self._stop = asyncio.Event()

    @property
    def _api(self) -> str:
        return f"{self.base_url}/controller"

    @property
    def _ws_url(self) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}/controller/ws/status"

    async def start(self) -> None:
        conn = (await self._http.get(f"{self._api}/connection")).json()
        self.swarm_id = conn["swarm_id"]
        size = (await self._http.get(f"{self._api}/map_size")).json()
        self.map_size = (size["width"], size["height"])
        await self.refresh()
        self._tasks = [
            asyncio.create_task(self._listen()),
            asyncio.create_task(self._flush()),
        ]

    async def close(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        await self._http.aclose()

    async def refresh(self) -> None:
        """Re-read the whole fleet, which is how a new bot is noticed."""
        try:
            listing = (await self._http.get(f"{self._api}/dotbots")).json()
        except httpx.HTTPError:
            return
        for raw in listing:
            self._absorb(raw)

    def _absorb(self, raw: Dict[str, Any]) -> None:
        address = raw.get("address")
        if not address:
            return
        position = raw.get("lh2_position")
        bot = self.bots.get(address)
        if position is None and bot is None:
            return
        heading = raw.get("direction")
        battery = raw.get("battery")
        self.bots[address] = Bot(
            address=address,
            x=float(position["x"]) if position else bot.x,
            y=float(position["y"]) if position else bot.y,
            # -1000 is the controller's "no heading yet".
            heading=(
                float(heading)
                if heading is not None and heading != -1000
                else (bot.heading if bot else 0.0)
            ),
            application=int(raw.get("application", APPLICATION_DOTBOT)),
            battery=(
                float(battery)
                if battery is not None
                else (bot.battery if bot else 0.0)
            ),
        )

    async def _listen(self) -> None:
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._ws_url) as socket:
                    async for raw in socket:
                        try:
                            message = json.loads(raw)
                        except ValueError:
                            continue
                        data = message.get("data") or {}
                        if message.get("cmd") == 2 and data.get("address"):
                            self._absorb({**self._as_raw(data["address"]), **data})
                        else:
                            await self.refresh()
            except (OSError, websockets.WebSocketException):
                await asyncio.sleep(1.0)

    def _as_raw(self, address: str) -> Dict[str, Any]:
        bot = self.bots.get(address)
        if bot is None:
            return {"address": address}
        return {
            "address": address,
            "lh2_position": {"x": bot.x, "y": bot.y},
            "direction": bot.heading,
            "application": bot.application,
            "battery": bot.battery,
        }

    async def _flush(self) -> None:
        period = 1.0 / max(0.1, self.command_rate_hz)
        while not self._stop.is_set():
            await asyncio.sleep(period)
            for address, kind, payload in self._queue.drain():
                bot = self.bots.get(address)
                application = bot.application if bot else APPLICATION_DOTBOT
                url = f"{self._api}/dotbots/{address}/{application}/{kind}"
                try:
                    await self._http.put(url, json=payload)
                except httpx.HTTPError:
                    continue

    def waypoints(
        self, address: str, points: Sequence[Point], threshold: int = 100
    ) -> None:
        """Hand the bot's own controller a route to drive."""
        self._queue.put(
            address,
            "waypoints",
            {
                "threshold": threshold,
                "waypoints": [{"x": round(p.x), "y": round(p.y)} for p in points],
            },
        )

    def move_raw(self, address: str, left: int, right: int) -> None:
        """Drive the wheels directly, bypassing the bot's own controller."""
        self._queue.put(
            address,
            "move_raw",
            {"left_x": 0, "left_y": int(left), "right_x": 0, "right_y": int(right)},
        )

    def rgb_led(self, address: str, red: int, green: int, blue: int) -> None:
        self._queue.put(
            address,
            "rgb_led",
            {"red": int(red), "green": int(green), "blue": int(blue)},
        )


# ----------------------------------------------------------------- the app


class PlaygroundApp:
    """
    One demo, as the page sees it.

    Publishes the announcement retained with a will that empties it, so a page
    opened later still finds the demo and a killed demo leaves the rail by
    itself. Inputs arrive as callbacks; overlays and status go back out.
    """

    def __init__(
        self,
        announcement: Announcement,
        *,
        broker: str = DEFAULT_BROKER,
        controller: str = DEFAULT_CONTROLLER,
        root: str = TOPIC_ROOT,
        swarm: Optional[str] = None,
        command_rate_hz: float = 5.0,
    ) -> None:
        self.announcement = announcement
        self.root = root
        self.swarm = swarm
        self.values: Dict[str, Any] = announcement.defaults()
        self.pointer: Optional[PointerSample] = None
        #: The latest of each map input, so a loop can read it like a value.
        self.goals: List[Point] = []
        self.rects: List[Rect] = []
        self.text: str = ""
        self.controller = ControllerClient(controller, command_rate_hz=command_rate_hz)
        self._broker = urlparse(broker if "://" in broker else f"mqtt://{broker}")
        self._client: Optional[MQTTClient] = None
        self._client_id = f"playground-{announcement.name}-{uuid.uuid4().hex[:8]}"
        self._on_pointer: List[Callable[[PointerSample], None]] = []
        self._on_control: List[Callable[[ControlChange], None]] = []
        self._on_action: List[Callable[[Action], None]] = []
        self._on_goals: List[Callable[[GoalsInput], None]] = []
        self._on_rects: List[Callable[[RectsInput], None]] = []
        self._on_text: List[Callable[[TextInput], None]] = []
        self._on_input: List[Callable[[Dict[str, Any]], None]] = []

    @property
    def bots(self) -> Dict[str, Bot]:
        return self.controller.bots

    @property
    def topics(self) -> Tuple[str, str, str]:
        if self.swarm is None:
            raise RuntimeError("swarm id unknown until start() has read the controller")
        return app_topics(self.root, self.swarm, self.announcement.name)

    def on_pointer(self, callback: Callable[[PointerSample], None]) -> None:
        self._on_pointer.append(callback)

    def on_control(self, callback: Callable[[ControlChange], None]) -> None:
        self._on_control.append(callback)

    def on_action(self, callback: Callable[[Action], None]) -> None:
        self._on_action.append(callback)

    def on_goals(self, callback: Callable[[GoalsInput], None]) -> None:
        self._on_goals.append(callback)

    def on_rects(self, callback: Callable[[RectsInput], None]) -> None:
        self._on_rects.append(callback)

    def on_text(self, callback: Callable[[TextInput], None]) -> None:
        self._on_text.append(callback)

    def on_input(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Every input kind this helper does not model, as a plain dict."""
        self._on_input.append(callback)

    async def start(self) -> None:
        await self.controller.start()
        if self.swarm is None:
            self.swarm = self.controller.swarm_id
        announce, inbound, _ = self.topics
        self._client = MQTTClient(self._client_id, will_message=clear_message(announce))
        self._client.on_message = self._on_message
        if self._broker.username:
            self._client.set_auth_credentials(
                self._broker.username, self._broker.password
            )
        await self._client.connect(
            self._broker.hostname or "localhost",
            self._broker.port or 1883,
            ssl=self._broker.scheme in ("mqtts", "wss"),
            keepalive=KEEPALIVE_S,
        )
        self._client.publish(announce, self.announcement.payload(), qos=1, retain=True)
        self._client.subscribe(inbound, qos=0)

    async def stop(self) -> None:
        """Leave the rail on the way out, rather than waiting for the will."""
        if self._client is not None:
            announce, _, _ = self.topics
            self._client.publish(announce, b"", qos=1, retain=True)
            await asyncio.sleep(0.1)
            await self._client.disconnect()
            self._client = None
        await self.controller.close()

    def publish_overlay(self, items: Sequence[Dict[str, Any]]) -> None:
        self._publish_out({"kind": "overlay", "items": list(items)})

    def publish_status(self, text: str) -> None:
        self._publish_out({"kind": "status", "text": text})

    def publish_positions(self, bots: Sequence[Bot]) -> None:
        """For a page that cannot reach the controller, e.g. a phone."""
        self._publish_out(
            {
                "kind": "positions",
                "bots": [
                    {"address": b.address, "x": b.x, "y": b.y, "heading": b.heading}
                    for b in bots
                ],
            }
        )

    def _publish_out(self, message: Dict[str, Any]) -> None:
        if self._client is None:
            return
        _, _, outbound = self.topics
        message.setdefault("t", time.time())
        self._client.publish(outbound, json.dumps(message).encode(), qos=0)

    def _on_message(self, _client, _topic, payload, _qos, _properties):
        parsed = parse_input(payload)
        if parsed is None:
            return
        if isinstance(parsed, PointerSample):
            self.pointer = parsed
            self._fire(self._on_pointer, parsed)
        elif isinstance(parsed, ControlChange):
            self.values[parsed.id] = parsed.value
            self._fire(self._on_control, parsed)
        elif isinstance(parsed, Action):
            self._fire(self._on_action, parsed)
        elif isinstance(parsed, GoalsInput):
            self.goals = parsed.points
            self._fire(self._on_goals, parsed)
        elif isinstance(parsed, RectsInput):
            self.rects = parsed.rects
            self._fire(self._on_rects, parsed)
        elif isinstance(parsed, TextInput):
            self.text = parsed.text
            self._fire(self._on_text, parsed)
        else:
            self._fire(self._on_input, parsed)

    @staticmethod
    def _fire(callbacks: Sequence[Callable[[Any], None]], value: Any) -> None:
        for callback in callbacks:
            callback(value)


# ------------------------------------------------------------- the launcher


def demo_command(func: Callable[..., None]) -> Any:
    """The three options every demo takes, declared once."""
    func = click.option(
        "--rate",
        default=5.0,
        show_default=True,
        help="Command rate per bot, in hertz.",
    )(func)
    func = click.option(
        "--controller",
        default=DEFAULT_CONTROLLER,
        show_default=True,
        help="Controller base URL.",
    )(func)
    func = click.option(
        "--broker", default=DEFAULT_BROKER, show_default=True, help="MQTT broker URL."
    )(func)
    return click.command()(func)


def serve(
    announcement: Announcement,
    drive: Callable[[PlaygroundApp], Any],
    *,
    broker: str = DEFAULT_BROKER,
    controller: str = DEFAULT_CONTROLLER,
    rate: float = 5.0,
) -> None:
    """Announce the demo, run its loop until interrupted, then leave the rail."""

    async def main() -> None:
        app = PlaygroundApp(
            announcement, broker=broker, controller=controller, command_rate_hz=rate
        )
        await app.start()
        announce, _, _ = app.topics
        click.echo(f"{announcement.name} announced on {announce}, driving {controller}")
        try:
            await drive(app)
        finally:
            await app.stop()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
