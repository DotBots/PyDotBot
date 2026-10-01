"""The controller stream: snapshot, merge-patch deltas, acks and resync."""

import asyncio
import copy
import json
import math
import random
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotbot_utils.protocol import Frame, Header, Packet
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from dotbot import addr_to_hex, stream
from dotbot.controller import STALE_AFTER_S, Controller, ControllerSettings
from dotbot.models import DotBotLH2Position, DotBotRgbLedCommandModel
from dotbot.protocol import PayloadDotBotAdvertisement, WaypointsStatus
from dotbot.server import api
from dotbot.stream import (
    SNAPSHOT_CHUNK,
    STALL_S,
    WINDOW,
    WRITE_BUFFER_LIMIT,
    StreamOptions,
)
from dotbot.ws_clients import TRANSPORT_KEY


def merge_patch(target, patch):
    """RFC 7396."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


class Client:
    """A stream client over a fake socket, keeping the fleet it was sent."""

    def __init__(self, hub, trail=0, hz=20, acks=True, since=None, run=None):
        self.hub = hub
        self.acks = acks
        self.frames = []
        self.texts = []
        self.fleet = {}
        self.models = None
        self._parts = []
        self.seq = None
        self.transport = MagicMock()
        self.transport.get_write_buffer_size.return_value = 0
        self.scope = {TRANSPORT_KEY: self.transport}
        self.close = AsyncMock()
        self.trail = trail
        options = StreamOptions(hz=hz, trail=trail, since=since, run=run)
        self.client = hub.client(self, options)
        self.hello = json.loads(hub.hello(self.client))
        hub.add(self.client)

    async def send_text(self, text):
        self.texts.append(text)
        message = json.loads(text)
        if message.get("event") == "robot_models":
            # Sent with every snapshot; kept apart so frames count the rest
            self.models = message["data"]
        else:
            self.frames.append(message)
        self.apply(message)
        if self.acks:
            self.hub.receive(self, json.dumps({"ack": message["seq"]}))

    def apply(self, message):
        if message["type"] == "snapshot":
            if message["part"] == 1:
                self._parts = []
            self._parts.extend(message["robots"])
            if message["part"] == message["parts"]:
                self.fleet = {robot["address"]: robot for robot in self._parts}
        elif message["type"] == "delta":
            for address, patch in message["robots"].items():
                if patch is None:
                    self.fleet.pop(address, None)
                    continue
                patch = dict(patch)
                reset = patch.pop("trail_reset", False)
                append = patch.pop("trail_append", [])
                # A robot new to the client, or back after being forgotten,
                # comes whole and replaces what was held
                held = {} if "address" in patch else self.fleet.get(address, {})
                robot = merge_patch(held, patch)
                trail = [] if reset else list(robot.get("trail", []))
                robot["trail"] = (trail + append)[-self.trail :] if self.trail else []
                self.fleet[address] = robot
        self.seq = message["seq"]

    def of_type(self, kind):
        return [f for f in self.frames if f["type"] == kind]

    def body(self, address):
        """A robot's body as a UI draws it: its model's shape turned by the
        pose's heading about the origin, then moved onto the pose's axle."""
        robot = self.fleet[address]
        return expand(self.models[robot["model"]], robot["pose"])


def expand(shape, pose):
    theta = math.radians(pose["heading_deg"])
    cos, sin = math.cos(theta), math.sin(theta)

    def place(point):
        x, y = point["x"], point["y"]
        return {"x": pose["x"] + x * cos - y * sin, "y": pose["y"] + x * sin + y * cos}

    return {
        **shape,
        "heading_deg": pose["heading_deg"],
        "heading_source": pose["heading_source"],
        **{
            name: place(shape[name])
            for name in ("photodiode", "axle", "centre", "nose", "led")
        },
        "outline": [place(p) for p in shape["outline"]],
        "wheels": [[place(p) for p in wheel] for wheel in shape["wheels"]],
    }


def _flat(value):
    """Every number in a JSON value, in order."""
    if isinstance(value, dict):
        return [n for key in sorted(value) for n in _flat(value[key])]
    if isinstance(value, list):
        return [n for item in value for n in _flat(item)]
    return [value]


async def settle():
    for _ in range(50):
        await asyncio.sleep(0)


async def tick(hub, now):
    hub.tick(now)
    await settle()


def _advertised(source: int, **fields) -> Frame:
    sent = Frame(
        header=Header(destination=0, source=source),
        packet=Packet().from_payload(PayloadDotBotAdvertisement(**fields)),
    )
    return Frame().from_bytes(sent.to_bytes())


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    _controller = Controller(
        ControllerSettings(
            port="/dev/null", baudrate=115200, network_id="0", gw_address="78"
        )
    )
    _controller.stream.autostart = False
    previous = getattr(api, "controller", None)
    api.controller = _controller
    yield _controller
    api.controller = previous


def advertise(controller, source, x=1000, y=1000, **fields):
    fields.setdefault("direction", 0)
    fields.setdefault("battery", 3000)
    controller.handle_received_frame(_advertised(source, pos_x=x, pos_y=y, **fields))


async def rest_fleet(trail, body=False):
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/controller/dotbots?include_lost=true&trail={trail}"
            + ("&body=1" if body else "")
        )
    return {robot["address"]: robot for robot in response.json()}


def _differences(held, rest):
    return {
        (address, key): (held.get(address, {}).get(key), robot.get(key))
        for address, robot in rest.items()
        for key in set(robot) | set(held.get(address, {}))
        if held.get(address, {}).get(key) != robot.get(key)
    }


def without_last_seen(fleet):
    return {
        address: {k: v for k, v in robot.items() if k != "last_seen"}
        for address, robot in fleet.items()
    }


# --- hello and snapshot -----------------------------------------------------


@pytest.mark.asyncio
async def test_hello_says_what_the_client_is_served(controller):
    client = Client(controller.stream, trail=5, hz=7)
    assert client.hello == {
        "type": "hello",
        "protocol": 2,
        "run": controller.run_id,
        "seq": controller.seq,
        "hz": 7,
        "unacked_hz": 1,
        "window": WINDOW,
        "trail": 5,
        "acks": True,
        "resumed": False,
    }


@pytest.mark.asyncio
async def test_a_snapshot_is_the_rest_list_in_parts_of_a_hundred(controller):
    for i in range(250):
        advertise(controller, 0x1000 + i, x=500 + i, y=700)
    controller.seed_trail(
        addr_to_hex(0x1000), [DotBotLH2Position(x=i, y=i) for i in range(10)]
    )
    client = Client(controller.stream, trail=4)
    await tick(controller.stream, 0)
    parts = client.of_type("snapshot")
    assert [(p["part"], p["parts"], len(p["robots"])) for p in parts] == [
        (1, 3, SNAPSHOT_CHUNK),
        (2, 3, SNAPSHOT_CHUNK),
        (3, 3, 50),
    ]
    assert {p["seq"] for p in parts} == {controller.seq}
    listed = [robot for p in parts for robot in p["robots"]]
    rest = await rest_fleet(4)
    assert listed == list(rest.values())
    assert [p["x"] for p in rest[addr_to_hex(0x1000)]["trail"]] == [6, 7, 8, 9]


@pytest.mark.asyncio
async def test_an_empty_fleet_is_one_empty_snapshot(controller):
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    (snapshot,) = client.frames
    assert (snapshot["part"], snapshot["parts"], snapshot["robots"]) == (1, 1, [])
    assert list(client.models) == ["dotbot-v3"]


# --- deltas -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_delta_carries_only_what_changed(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    advertise(controller, 0x42, battery=2900)
    await tick(controller.stream, 0.1)
    (delta,) = client.of_type("delta")
    address = addr_to_hex(0x42)
    assert delta["seq"] == controller.seq
    assert delta["robots"] == {
        address: {
            "battery": 2.9,
            "last_seen": controller.dotbots[address].last_seen,
        }
    }


@pytest.mark.asyncio
async def test_an_unchanged_fleet_sends_nothing(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    advertise(controller, 0x42)
    await tick(controller.stream, 0.1)
    assert client.of_type("delta") == []


@pytest.mark.asyncio
async def test_deltas_are_merge_patches_over_the_rest_object(controller):
    """Applied as RFC 7396 patches, the deltas rebuild what REST serves."""
    rng = random.Random(4)
    for i in range(6):
        advertise(controller, 0x10 + i, x=1000 + 100 * i)
    client = Client(controller.stream, trail=8)
    quiet = Client(controller.stream, trail=0, hz=5)
    now = 0.0
    await tick(controller.stream, now)
    for step in range(60):
        source = 0x10 + rng.randrange(6)
        address = addr_to_hex(source)
        action = rng.randrange(7)
        known = address in controller.dotbots
        if action == 0:
            advertise(
                controller,
                source,
                x=rng.randrange(500, 3000),
                y=rng.randrange(500, 3000),
                direction=rng.randrange(360),
            )
        elif action == 1:
            advertise(
                controller,
                source,
                axle_x=1000,
                axle_y=rng.randrange(900, 1000),
                waypoints_status=rng.choice(list(WaypointsStatus)),
                waypoint_idx=rng.randrange(3),
                report=True,
            )
        elif action == 2:
            # A report that stops coming leaves its fields to null
            advertise(controller, source, report=True, axle_x=0xFFFF, axle_y=0xFFFF)
        elif action == 3 and known:
            controller.update_dotbot(
                address,
                rgb_led=DotBotRgbLedCommandModel(
                    red=rng.randrange(255), green=0, blue=0
                ),
            )
        elif action == 4 and known:
            controller.clear_trail(address)
        elif action == 5:
            await controller._refresh_status(time.monotonic() + STALE_AFTER_S + 1)
        elif action == 6 and known:
            controller.forget(address)
        now += 0.05
        await tick(controller.stream, now)
        rest = without_last_seen(await rest_fleet(8))
        held = without_last_seen(client.fleet)
        assert held == rest, (step, _differences(held, rest))
        for address, robot in (await rest_fleet(0, body=True)).items():
            # The axle is sent to 0.1 mm, so the drawn body is within 0.05
            drawn = client.body(address)
            assert _flat(drawn) == pytest.approx(_flat(robot["body"]), abs=0.06)
    now += 1
    await tick(controller.stream, now)
    assert without_last_seen(quiet.fleet) == without_last_seen(await rest_fleet(0))


@pytest.mark.asyncio
async def test_a_moving_robot_appends_its_new_points_only(controller):
    advertise(controller, 0x42, x=1000, y=1000)
    client = Client(controller.stream, trail=10)
    blind = Client(controller.stream, trail=0)
    await tick(controller.stream, 0)
    advertise(controller, 0x42, x=1100, y=1000)
    advertise(controller, 0x42, x=1200, y=1000)
    await tick(controller.stream, 0.1)
    patch = client.of_type("delta")[0]["robots"][addr_to_hex(0x42)]
    assert patch["trail_append"] == [
        {"x": 1100.0, "y": 1000.0},
        {"x": 1200.0, "y": 1000.0},
    ]
    assert "trail_reset" not in patch
    await tick(controller.stream, 1.1)
    blind_patch = blind.of_type("delta")[0]["robots"][addr_to_hex(0x42)]
    assert "trail_append" not in blind_patch
    assert blind_patch["lh2_position"] == {"x": 1200.0, "y": 1000.0}

    controller.clear_trail(addr_to_hex(0x42))
    advertise(controller, 0x42, x=1300, y=1000)
    await tick(controller.stream, 1.2)
    patch = client.of_type("delta")[-1]["robots"][addr_to_hex(0x42)]
    assert patch["trail_reset"] is True
    assert patch["trail_append"] == [{"x": 1300.0, "y": 1000.0}]


@pytest.mark.asyncio
async def test_a_new_robot_arrives_whole(controller):
    client = Client(controller.stream, trail=3)
    await tick(controller.stream, 0)
    advertise(controller, 0x42)
    await tick(controller.stream, 0.1)
    (delta,) = client.of_type("delta")
    assert delta["robots"] == await rest_fleet(3)


@pytest.mark.asyncio
async def test_caught_up_clients_share_one_encoding(controller):
    advertise(controller, 0x42)
    first, second = Client(controller.stream), Client(controller.stream)
    await tick(controller.stream, 0)
    advertise(controller, 0x42, battery=2800)
    await tick(controller.stream, 0.1)
    assert first.texts[-1] is second.texts[-1]


@pytest.mark.asyncio
async def test_clients_connecting_apart_are_served_together(controller):
    advertise(controller, 0x42)
    first = Client(controller.stream, hz=10)
    await tick(controller.stream, 0.0)
    second = Client(controller.stream, hz=10)
    for step in range(1, 11):
        advertise(controller, 0x42, battery=3000 - step)
        await tick(controller.stream, step * 0.05)
    assert first.texts[-1] is second.texts[-1]


# --- events -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_calibration_session_event_keeps_its_nulls(controller):
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    await controller._notify_calibration_session({"outstanding": None, "total": 4})
    await tick(controller.stream, 0.1)
    await controller._notify_calibration_session(None)
    await tick(controller.stream, 0.2)
    first, second = client.of_type("event")
    assert first["event"] == "calibration_session"
    assert first["data"]["outstanding"] is None
    assert second["data"] is None


@pytest.mark.asyncio
async def test_a_late_client_is_sent_the_last_events_with_its_snapshot(controller):
    controller.set_event(
        "camera_detection/arena", "camera_detection", {"area": "arena"}
    )
    controller.set_event(
        "camera_detection/arena", "camera_detection", {"area": "arena", "sequence": 2}
    )
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    assert [f["type"] for f in client.frames] == ["snapshot", "event"]
    assert client.frames[1]["data"] == {"area": "arena", "sequence": 2}


# --- flow control -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_client_that_never_acks_is_served_once_a_second(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream, hz=20, acks=False)
    for step in range(60):  # 3 s of a robot changing every 50 ms
        advertise(controller, 0x42, battery=3000 - step)
        await tick(controller.stream, step * 0.05)
    assert len(client.frames) == 3
    assert client.client.unacked == stream.deque()


@pytest.mark.asyncio
async def test_the_first_ack_switches_a_client_to_its_rate(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream, hz=10, acks=False)
    await tick(controller.stream, 0)
    controller.stream.receive(client, json.dumps({"ack": client.seq}))
    client.acks = True
    for step in range(1, 21):  # 1 s at 20 ticks per second
        advertise(controller, 0x42, battery=3000 - step)
        await tick(controller.stream, step * 0.05)
    assert 9 <= len(client.of_type("delta")) <= 11


@pytest.mark.asyncio
async def test_jittery_ticks_never_exceed_the_rate(controller):
    rng = random.Random(1)
    advertise(controller, 0x42)
    client = Client(controller.stream, hz=10)
    now = 0.0
    while now < 5:
        now += 0.05 + rng.uniform(-0.02, 0.02)
        advertise(controller, 0x42, battery=3000 - int(now * 100))
        await tick(controller.stream, now)
    assert 45 <= len(client.of_type("delta")) <= 50


@pytest.mark.asyncio
async def test_a_full_window_sends_nothing(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    client.acks = False
    for step in range(1, 20):
        advertise(controller, 0x42, battery=3000 - step)
        await tick(controller.stream, step * 0.05)
    assert len(client.of_type("delta")) == WINDOW
    # Acking the newest frame opens the window, and one frame catches up
    controller.stream.receive(client, json.dumps({"ack": client.seq}))
    await tick(controller.stream, 1.0)
    assert len(client.of_type("delta")) == WINDOW + 1
    assert client.frames[-1]["robots"][addr_to_hex(0x42)]["battery"] == 2.981


@pytest.mark.asyncio
async def test_a_client_that_stops_acking_is_closed_at_15_s(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    reader = Client(controller.stream)
    await tick(controller.stream, 0)
    client.acks = False
    now = 0.0
    sent = []
    while now < STALL_S + 1:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20) % 500)
        await tick(controller.stream, now)
        sent.append(len(client.frames))
        if client.close.await_count:
            break
    # Its backlog never grew: the window, then nothing
    assert max(sent) == 1 + WINDOW
    assert STALL_S < now <= STALL_S + 0.2
    assert client not in controller.stream.clients
    assert reader in controller.stream.clients
    assert len(reader.of_type("delta")) > 250


@pytest.mark.asyncio
async def test_a_stuck_send_is_closed_at_15_s_and_starves_nobody(controller):
    advertise(controller, 0x42)
    stuck = Client(controller.stream)
    reader = Client(controller.stream)

    async def never(_text):
        await asyncio.Event().wait()

    stuck.send_text = never
    now = 0.0
    while now < STALL_S + 0.5:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20) % 500)
        await tick(controller.stream, now)
    assert stuck not in controller.stream.clients
    stuck.close.assert_awaited()
    assert len(reader.of_type("delta")) > 250


@pytest.mark.parametrize("seconds", [6, 16])
@pytest.mark.asyncio
async def test_a_slow_snapshot_that_keeps_sending_is_not_dropped(controller, seconds):
    for source in range(1, 3 * SNAPSHOT_CHUNK + 1):
        advertise(controller, source)
    hub = controller.stream
    slow = Client(hub)
    reader = Client(hub)
    parts = 3
    fast_send = Client.send_text.__get__(slow)
    sent_at = []

    async def send_text(text):
        # Each snapshot part takes its share of `seconds` to go out
        if json.loads(text)["type"] == "snapshot":
            target = hub.now + seconds / parts
            while hub.now < target:
                await asyncio.sleep(0)
        sent_at.append(hub.now)
        await fast_send(text)

    slow.send_text = send_text
    now = 0.0
    while now < seconds + STALL_S + 1:
        now += 0.05
        advertise(controller, 1, battery=3000 - int(now * 20) % 500)
        await tick(hub, now)
    assert slow in hub.clients
    assert len(slow.of_type("snapshot")) == parts
    assert sent_at[parts - 1] >= seconds - 0.1
    # Caught up with deltas after its snapshot, never snapshotted again
    assert len(slow.of_type("delta")) > 100
    assert reader in hub.clients


@pytest.mark.asyncio
async def test_a_failing_client_is_dropped_and_the_others_still_served(
    controller, monkeypatch
):
    advertise(controller, 0x42)
    hub = controller.stream
    broken = Client(hub)
    reader = Client(hub)
    await tick(hub, 0)
    serve = hub._serve

    def failing(client, now, shared):
        if client is broken.client:
            raise RuntimeError("boom")
        serve(client, now, shared)

    monkeypatch.setattr(hub, "_serve", failing)
    for step in range(1, 5):
        advertise(controller, 0x42, battery=3000 - step)
        await tick(hub, step * 0.05)
    assert broken not in hub.clients
    broken.close.assert_awaited()
    assert reader in hub.clients
    assert len(reader.of_type("delta")) == 4


@pytest.mark.asyncio
async def test_the_tick_task_survives_a_failing_client(controller, monkeypatch):
    advertise(controller, 0x42)
    hub = controller.stream
    hub.autostart = True
    monkeypatch.setattr(stream, "TICK_S", 0.001)
    serve = hub._serve
    calls = {"n": 0}

    def failing_once(client, now, shared):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        serve(client, now, shared)

    monkeypatch.setattr(hub, "_serve", failing_once)
    broken = Client(hub)
    reader = Client(hub)
    for _ in range(200):
        await asyncio.sleep(0.001)
        if reader.frames:
            break
    assert reader.of_type("snapshot")
    assert not hub._task.done()
    for client in list(hub.clients.values()):
        hub.remove(client.websocket)
    await asyncio.sleep(0.01)
    assert broken not in hub.clients


@pytest.mark.asyncio
async def test_a_non_acking_client_that_stops_reading_is_bounded_and_closed(
    controller,
):
    advertise(controller, 0x42)
    client = Client(controller.stream, acks=False)
    await tick(controller.stream, 0)
    client.transport.get_write_buffer_size.return_value = WRITE_BUFFER_LIMIT + 1
    now = 0.0
    while now < STALL_S + 0.5:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20) % 500)
        await tick(controller.stream, now)
    assert len(client.frames) == 1
    assert client not in controller.stream.clients


# --- resync -----------------------------------------------------------------


async def _run_for(controller, start, seconds):
    now = start
    while now < start + seconds:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20) % 1000)
        await tick(controller.stream, now)
    return now


@pytest.mark.asyncio
async def test_a_client_held_back_5_s_gets_a_snapshot(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    # Past the 10 s that follow its first snapshot
    now = await _run_for(controller, 0, 10.5)
    client.acks = False
    held = now
    while now < held + 6:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20))
        await tick(controller.stream, now)
    controller.stream.receive(client, json.dumps({"ack": client.seq}))
    client.acks = True
    await tick(controller.stream, now + 0.05)
    assert client.frames[-1]["type"] == "snapshot"
    assert client.fleet == await rest_fleet(0)


@pytest.mark.asyncio
async def test_a_client_needing_a_second_snapshot_within_10_s_is_closed(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    client.acks = False
    now = 0.0
    while now < 5.5:
        now += 0.05
        advertise(controller, 0x42, battery=3000 - int(now * 20))
        await tick(controller.stream, now)
    controller.stream.receive(client, json.dumps({"ack": client.seq}))
    await tick(controller.stream, now + 0.05)
    assert client not in controller.stream.clients
    client.close.assert_awaited()


@pytest.mark.asyncio
async def test_evicted_trail_points_mean_a_snapshot(controller):
    advertise(controller, 0x42)
    client = Client(controller.stream, trail=5)
    await tick(controller.stream, 0)
    controller.seed_trail(
        addr_to_hex(0x42), [DotBotLH2Position(x=i, y=i) for i in range(1000)]
    )
    controller.seed_trail(addr_to_hex(0x42), [DotBotLH2Position(x=-1, y=-1)])
    # Past the 10 s that follow its first snapshot
    await tick(controller.stream, 10.1)
    assert client.frames[-1]["type"] == "snapshot"
    assert client.fleet == await rest_fleet(5)


# --- resume -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_since_resumes_with_a_delta_of_what_changed(controller):
    for i in range(3):
        advertise(controller, 0x10 + i, x=1000 + 100 * i)
    first = Client(controller.stream, trail=5)
    await tick(controller.stream, 0)
    controller.stream.remove(first)
    fleet, seq = copy.deepcopy(first.fleet), first.seq
    advertise(controller, 0x10, x=2000, y=2000)
    advertise(controller, 0x13)
    await controller._notify_calibration_session(None)

    second = Client(controller.stream, trail=5, since=seq, run=controller.run_id)
    second.fleet = fleet
    assert second.hello["resumed"] is True
    await tick(controller.stream, 1)
    assert [f["type"] for f in second.frames] == ["delta", "event"]
    assert set(second.frames[0]["robots"]) == {addr_to_hex(0x10), addr_to_hex(0x13)}
    assert second.fleet == await rest_fleet(5)


@pytest.mark.asyncio
async def test_a_seq_from_the_rest_snapshot_resumes_the_stream(controller):
    advertise(controller, 0x42)
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as http:
        response = await http.get("/controller/dotbots?include_lost=true")
    seq = int(response.headers["X-Controller-Seq"])
    run = response.headers["X-Controller-Run"]
    advertise(controller, 0x42, battery=2500)
    client = Client(controller.stream, since=seq, run=run)
    client.fleet = {r["address"]: r for r in response.json()}
    await tick(controller.stream, 0)
    assert [f["type"] for f in client.frames] == ["delta"]
    assert client.fleet == await rest_fleet(0)


@pytest.mark.parametrize(
    "run,since", [("0123456789ab", 1), (None, 1), ("current", 10**9), ("current", -1)]
)
@pytest.mark.asyncio
async def test_a_seq_that_cannot_resume_gets_a_snapshot(controller, run, since):
    advertise(controller, 0x42)
    run = controller.run_id if run == "current" else run
    client = Client(controller.stream, since=since, run=run)
    assert client.hello["resumed"] is False
    await tick(controller.stream, 0)
    assert client.frames[0]["type"] == "snapshot"


@pytest.mark.asyncio
async def test_a_seq_older_than_an_evicted_point_gets_a_snapshot(controller):
    advertise(controller, 0x42)
    seq = controller.seq
    controller.seed_trail(
        addr_to_hex(0x42), [DotBotLH2Position(x=i, y=i) for i in range(1001)]
    )
    controller.seed_trail(addr_to_hex(0x42), [DotBotLH2Position(x=-1, y=-1)])
    client = Client(controller.stream, trail=5, since=seq, run=controller.run_id)
    assert client.hello["resumed"] is False
    trail0 = Client(controller.stream, trail=0, since=seq, run=controller.run_id)
    assert trail0.hello["resumed"] is True


# --- query ------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,hz,trail,since",
    [
        ({}, 10, 0, None),
        ({"hz": "50", "trail": "5000"}, 20, 1000, None),
        ({"hz": "0", "trail": "-3"}, 1, 0, None),
        ({"hz": "fast", "trail": "x", "since": "y"}, 10, 0, None),
        ({"hz": "3", "trail": "200", "since": "42"}, 3, 200, 42),
    ],
)
def test_the_query_is_clamped(query, hz, trail, since):
    options = StreamOptions.from_query(query)
    assert (options.hz, options.trail, options.since) == (hz, trail, since)


# --- the endpoint -----------------------------------------------------------


def test_the_stream_endpoint_says_hello_then_snapshots(controller):
    controller.stream.autostart = True
    advertise(controller, 0x42)
    with TestClient(api).websocket_connect(
        "/controller/ws/stream?hz=5&trail=2"
    ) as websocket:
        hello = websocket.receive_json()
        assert (hello["type"], hello["hz"], hello["trail"]) == ("hello", 5, 2)
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["robots"][0]["address"] == addr_to_hex(0x42)
        websocket.send_json({"ack": snapshot["seq"]})


def test_the_old_status_endpoint_is_gone(controller):
    with pytest.raises(WebSocketDisconnect):
        with TestClient(api).websocket_connect("/controller/ws/status") as websocket:
            websocket.receive_text()


@pytest.mark.asyncio
async def test_the_rest_list_is_the_model_serialised(controller):
    """The list built from the stream's cached dumps reads as FastAPI would
    serialise the robot models it documents."""
    from dotbot.models import DotBotModel, DotBotWaypoints

    advertise(
        controller, 0x42, axle_x=1000, axle_y=971, waypoints_status=3, report=True
    )
    advertise(controller, 0x43, x=1500)
    controller.update_dotbot(
        addr_to_hex(0x43),
        waypoints=DotBotWaypoints(
            threshold=10,
            waypoints=[{"x": 1, "y": 2}, {"x": 3, "y": 4, "heading_deg": 90}],
        ).waypoints,
    )
    controller.seed_trail(
        addr_to_hex(0x42), [DotBotLH2Position(x=i, y=i) for i in range(5)]
    )
    expected = [
        DotBotModel.model_validate(
            dotbot.model_dump() | {"trail": controller.records[address].trail.json(3)}
        ).model_dump(mode="json", exclude_none=True)
        for address, dotbot in controller.dotbots.items()
    ]
    assert list((await rest_fleet(3)).values()) == expected


@pytest.mark.asyncio
async def test_a_forgotten_robot_is_null_in_the_delta(controller):
    advertise(controller, 0x42)
    advertise(controller, 0x43)
    client = Client(controller.stream)
    await tick(controller.stream, 0)
    controller.forget(addr_to_hex(0x42))
    await tick(controller.stream, 1)
    (delta,) = client.of_type("delta")
    assert delta["robots"] == {addr_to_hex(0x42): None}
    assert set(client.fleet) == {addr_to_hex(0x43)}


@pytest.mark.asyncio
async def test_a_robot_back_after_being_forgotten_comes_whole(controller):
    advertise(controller, 0x42, x=1000)
    controller.update_dotbot(
        addr_to_hex(0x42), rgb_led=DotBotRgbLedCommandModel(red=9, green=0, blue=0)
    )
    since = controller.seq
    controller.forget(addr_to_hex(0x42))
    advertise(controller, 0x42, x=2000)
    (delta,) = (json.loads(t) for t in stream.delta_frames(controller, since, 0))
    robot = delta["robots"][addr_to_hex(0x42)]
    assert robot["address"] == addr_to_hex(0x42)
    assert robot["lh2_position"]["x"] == 2000
    assert "rgb_led" not in robot
    assert controller.forgotten == {}


@pytest.mark.asyncio
async def test_a_resumed_client_is_told_what_was_forgotten(controller):
    advertise(controller, 0x42)
    advertise(controller, 0x43)
    first = Client(controller.stream)
    await tick(controller.stream, 0)
    controller.forget(addr_to_hex(0x43))
    second = Client(controller.stream, since=first.seq, run=controller.run_id)
    second.fleet = copy.deepcopy(first.fleet)
    await tick(controller.stream, 1)
    assert second.hello["resumed"] is True
    assert second.fleet == await rest_fleet(0)
    assert addr_to_hex(0x43) not in second.fleet


@pytest.mark.asyncio
async def test_a_forgotten_robot_is_not_found_and_takes_no_command(controller):
    advertise(controller, 0x42)
    address = addr_to_hex(0x42)
    controller.forget(address)
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as http:
        assert (await http.get(f"/controller/dotbots/{address}")).status_code == 404
        response = await http.put(
            f"/controller/dotbots/{address}/0/rgb_led",
            json={"red": 1, "green": 2, "blue": 3},
        )
        assert response.status_code == 404
        response = await http.put(
            "/controller/dotbots/waypoints",
            json={"threshold": 50, "dotbots": {address: [{"x": 400, "y": 1600}]}},
        )
        assert response.status_code == 404
