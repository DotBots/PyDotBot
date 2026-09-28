"""Controller backend benchmark, with and without the simulator.

For each fleet size, starts a real controller in a child process (headless,
on a free loopback port, logging as `dotbot run controller` does) and loads
it from this process: K acking stream clients, and REST requests on the hot
endpoints. Optionally one more client that acks once then stops reading
(`--stall`), and one that takes 20 ms per frame (`--slow`). Three modes:

- `sim`: the controller runs the dotbot simulator in-process, as
  `dotbot run simulator` does, and every robot drives a waypoint batch.
- `mari`: as `sim`, with every robot on the simulated Mari network, joined,
  so it advertises at the rate its firmware derives from the slotframe.
- `synth`: no simulator. A gateway adapter replays advertisements at the
  firmware's 2 Hz per robot through the same thread-to-loop inbox the Mari
  edge adapter uses, so the controller's cost is measured alone. The frames
  are built in a feeder process (`--feeder thread` builds them on the
  gateway thread instead, inside the controller's process and its GIL).

A third, in-process figure is the simulator's own cost per robot tick on a
stepped clock, with no controller.

Writes a JSON result (one flat record per run, so thresholds can be keyed on
its fields later) and prints a text table. Linux only: it reads /proc.

    python utils/perf/bench_controller.py --out results.json
    python utils/perf/bench_controller.py -n 1 10 50 --clients 1 --window 5
    python utils/perf/bench_controller.py -n 200 --modes synth --stall --window 25
"""

import argparse
import asyncio
import base64
import json
import math
import os
import platform
import random
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")
ADVERTISEMENT_S = 0.5
AREA_MM = 9000  # robots are spread over this square, inside the steering bounds
SIM_THREAD_TARGETS = ("run",)
STREAM_HZ = 10
SLOW_FRAME_S = 0.02
# The trail a connecting client asks for when its snapshot is measured
SNAPSHOT_TRAIL = 200


class Histogram:
    """Millisecond samples counted in log-spaced bins 1% wide.

    Its size depends on the spread of the values, never on how many there
    are, so a long window does not measure the bench's own growth. Quantiles
    are within 1% of the exact ones; the count and max are exact.
    """

    FLOOR_MS = 0.01
    RATIO = 1.01

    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.bins = {}
        self.count = 0
        self.max = None

    def add(self, ms: float) -> None:
        self.count += 1
        self.max = ms if self.max is None else max(self.max, ms)
        index = (
            0
            if ms <= self.FLOOR_MS
            else 1 + int(math.log(ms / self.FLOOR_MS) / math.log(self.RATIO))
        )
        self.bins[index] = self.bins.get(index, 0) + 1

    def merge(self, other: "Histogram") -> "Histogram":
        for index, n in other.bins.items():
            self.bins[index] = self.bins.get(index, 0) + n
        self.count += other.count
        if other.max is not None:
            self.max = other.max if self.max is None else max(self.max, other.max)
        return self

    def _quantile(self, q: float) -> float:
        rank = min(self.count - 1, int(q * self.count))
        seen = 0
        for index in sorted(self.bins):
            seen += self.bins[index]
            if seen > rank:
                if index == 0:
                    return 0.0
                # The bin's geometric middle
                return min(self.max, self.FLOOR_MS * self.RATIO ** (index - 0.5))
        return self.max

    def summary(self) -> dict:
        if not self.count:
            return {"p50": None, "p99": None, "max": None, "count": 0}
        return {
            "p50": round(self._quantile(0.5), 2),
            "p99": round(self._quantile(0.99), 2),
            "max": round(self.max, 2),
            "count": self.count,
        }


# --- the child: the controller under test ----------------------------------


def _advertisements(count: int):
    """Advertisement frames from `count` robots, 2 Hz each, out of phase, as
    wire bytes, each yielded at the time it is due."""
    from dotbot_utils.protocol import Frame, Header, Packet

    from dotbot import GATEWAY_ADDRESS_DEFAULT
    from dotbot.protocol import PayloadDotBotAdvertisement

    positions = _grid(count)
    start = time.monotonic()
    beat = 0
    while True:
        due = start + beat * ADVERTISEMENT_S / count
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        index = beat % count
        x, y = positions[index]
        angle = beat * 0.05
        payload = PayloadDotBotAdvertisement(
            calibrated=0xFF,
            direction=int(math.degrees(angle)) % 360 - 180,
            pos_x=int(x + 60 * math.cos(angle)),
            pos_y=int(y + 60 * math.sin(angle)),
            battery=2900,
            mode=1,
            waypoints_status=1,
            batch_id=1,
            max_speed_10mm=30,
            axle_x=int(x),
            axle_y=int(y),
            report=True,
        )
        yield Frame(
            header=Header(
                destination=int(GATEWAY_ADDRESS_DEFAULT, 16), source=0x1000 + index
            ),
            packet=Packet.from_payload(payload),
        ).to_bytes()
        beat += 1


def feeder(count: int):
    """Write `_advertisements` to stdout, each behind its 2-byte length."""
    out = sys.stdout.buffer
    for wire in _advertisements(count):
        out.write(len(wire).to_bytes(2, "big") + wire)
        out.flush()


class SyntheticGatewayAdapter:
    """Advertisements from `count` robots handed to the loop through an inbox
    from a gateway thread, as the Mari edge adapter does.

    With `feeder="process"` the frames are built in a separate process and
    the gateway thread only parses them, as a real gateway thread only
    decodes what the serial port gives it; with "thread" the gateway thread
    builds them too, which holds the GIL against the controller's loop.
    """

    def __init__(self, count: int, feeder: str = "process"):
        self.count = count
        self.feeder = feeder
        self.sent = 0
        self._process = None

    def _built(self):
        yield from _advertisements(self.count)

    def _piped(self):
        self._process = subprocess.Popen(
            [sys.executable, __file__, "--feeder", str(self.count)],
            stdout=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(REPO)},
        )
        pipe = self._process.stdout
        while True:
            head = pipe.read(2)
            if len(head) < 2:
                return
            yield pipe.read(int.from_bytes(head, "big"))

    def _frames(self):
        from dotbot_utils.protocol import Frame

        wires = self._piped() if self.feeder == "process" else self._built()
        for wire in wires:
            self.inbox.put(Frame.from_bytes(wire))

    async def start(self, on_frame_received):
        from dotbot.inbox import FrameInbox

        self.inbox = FrameInbox(asyncio.get_running_loop())
        threading.Thread(target=self._frames, daemon=True).start()
        await self.inbox.run(on_frame_received)

    def close(self):
        if self._process is not None:
            self._process.kill()

    def send_payload(self, destination, payload):
        self.sent += 1


def _grid(count: int):
    side = math.ceil(math.sqrt(count))
    pitch = AREA_MM / side
    return [
        (500 + (i % side + 0.5) * pitch, 500 + (i // side + 0.5) * pitch)
        for i in range(count)
    ]


def _world(count: int, path: Path, network: str = "default"):
    import toml

    dotbots = [
        {
            "address": f"{0x1000 + i:016X}",
            "pos_x": int(x),
            "pos_y": int(y),
            "direction": 0,
            "network_mode": network,
        }
        for i, (x, y) in enumerate(_grid(count))
    ]
    path.write_text(toml.dumps({"dotbots": dotbots}))


def child(mode: str, count: int, port: int, workdir: Path, trail: int, feeder: str):
    """Run the controller until SIGTERM; SIGUSR1 opens the measured window,
    and SIGTERM writes this process's view of it to `workdir/child.json`.

    `trail` points of history are given to each robot when it first
    appears, as a robot that has driven for a while carries."""
    from dotbot.controller import Controller, ControllerSettings
    from dotbot.logger import setup_logging

    settings = ControllerSettings(
        adapter="dotbot-simulator",
        controller_http_port=port,
        headless=True,
        log_output=str(workdir / "pydotbot.log"),
    )
    if mode in ("sim", "mari"):
        world = workdir / "world.toml"
        _world(count, world, "mari" if mode == "mari" else "default")
        settings.simulator_init_state = str(world)
    setup_logging(settings.log_output, settings.log_level, ["console", "file"])
    controller = Controller(settings)
    if trail:
        from dotbot.models import DotBotLH2Position

        handle = controller.handle_received_frame

        def handle_with_trail(frame):
            known = set(controller.dotbots)
            handle(frame)
            for address in set(controller.dotbots) - known:
                controller.seed_trail(
                    address, [DotBotLH2Position(x=i, y=i) for i in range(trail)]
                )

        controller.handle_received_frame = handle_with_trail
    if mode == "synth":
        synthetic = SyntheticGatewayAdapter(count, feeder)

        async def start_adapter():
            controller.adapter = synthetic
            await synthetic.start(controller.handle_received_frame)

        controller._start_adapter = start_adapter

    lags = Histogram()
    window = {}

    def simulator():
        return getattr(controller.adapter, "simulator", None)

    def robots():
        return simulator().dotbots if simulator() is not None else []

    def robot_ticks():
        return simulator().ticks * len(robots()) if simulator() is not None else 0

    def open_window():
        lags.clear()
        window["start"] = time.monotonic()
        window["ticks"] = robot_ticks()
        inbox = getattr(controller.adapter, "inbox", None)
        if inbox is not None:
            window["coalesced"], window["dropped"] = inbox.coalesced, inbox.dropped
        window["threads"] = {
            thread.native_id: _role(thread) for thread in threading.enumerate()
        }
        (workdir / "threads.json").write_text(json.dumps(window["threads"]))

    def close_window():
        elapsed = time.monotonic() - window.get("start", time.monotonic())
        ticks = robot_ticks() - window.get("ticks", 0)
        result = {"window_s": elapsed, "loop_lag_ms": lags.summary()}
        inbox = getattr(controller.adapter, "inbox", None)
        if inbox is not None:
            result["frames_coalesced"] = inbox.coalesced - window.get("coalesced", 0)
            result["frames_dropped"] = inbox.dropped - window.get("dropped", 0)
        if robots():
            result["sim_ticks_per_bot_s"] = ticks / len(robots()) / elapsed
        (workdir / "child.json").write_text(json.dumps(result))
        if isinstance(controller.adapter, SyntheticGatewayAdapter):
            controller.adapter.close()
        os._exit(0)

    async def lag_monitor():
        period = 0.02
        while True:
            before = time.monotonic()
            await asyncio.sleep(period)
            lags.add((time.monotonic() - before - period) * 1000)

    # Plain handlers, not the loop's, so a saturated loop still answers
    signal.signal(signal.SIGUSR1, lambda *_: open_window())
    signal.signal(signal.SIGTERM, lambda *_: close_window())

    async def main():
        asyncio.create_task(lag_monitor())
        await controller.run()

    asyncio.run(main())


def _role(thread: threading.Thread) -> str:
    if thread is threading.main_thread():
        return "controller"
    for target in SIM_THREAD_TARGETS:
        if f"({target})" in thread.name:
            return "simulator"
    return "other"


# --- the parent: load and measurement ---------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _cpu_s(pid: int, tid: int = None) -> float:
    path = f"/proc/{pid}/stat" if tid is None else f"/proc/{pid}/task/{tid}/stat"
    fields = Path(path).read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / CLK_TCK


def _rss_mb(pid: int) -> float:
    return int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * PAGE / 2**20


def _thread_cpu(pid: int) -> dict:
    cpu = {}
    for tid in os.listdir(f"/proc/{pid}/task"):
        try:
            cpu[int(tid)] = _cpu_s(pid, int(tid))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return cpu


def _percentiles(samples: "Histogram") -> dict:
    return samples.summary()


def _stream_stats():
    return {
        "open": False,
        "frames": 0,
        "updates": 0,
        "bytes": 0,
        "snapshots": 0,
        "age_ms": Histogram(),
        "closed": False,
    }


async def _stream_client(url: str, stats: dict, stop: asyncio.Event, delay_s=0.0):
    """A stream client acking every frame; the age of an update is its
    receipt time minus the robot's `last_seen`."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    try:
        # A slow reader keeps a short queue, so its pace reaches the
        # controller instead of piling up here
        async with connect(url, max_size=None, max_queue=4 if delay_s else 16) as ws:
            while not stop.is_set():
                try:
                    text = await asyncio.wait_for(ws.recv(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                now = time.time()
                frame = json.loads(text)
                if delay_s:
                    await asyncio.sleep(delay_s)
                if "seq" in frame:
                    await ws.send(json.dumps({"ack": frame["seq"]}))
                if not stats["open"]:
                    continue
                stats["frames"] += 1
                stats["bytes"] += len(text)
                if frame["type"] == "snapshot":
                    stats["snapshots"] += frame["part"] == frame["parts"]
                elif frame["type"] == "delta":
                    for patch in frame["robots"].values():
                        stats["updates"] += 1
                        if patch and "last_seen" in patch:
                            stats["age_ms"].add((now - patch["last_seen"]) * 1000)
    except (ConnectionClosed, OSError):
        stats["closed"] = True


def _masked_text(text: str) -> bytes:
    """One client-to-server WebSocket text frame."""
    payload = text.encode()
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes([0x81, 0x80 | len(payload)]) + mask + masked


class StalledClient:
    """A stream client that acks its first frame, then never reads again,
    as a frozen browser tab does; its TCP state says when the server let go."""

    def __init__(self, port: int):
        self.port = port
        self.sock = None
        self.local_port = None

    def open(self):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.connect(("127.0.0.1", self.port))
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            (
                f"GET /controller/ws/stream?hz={STREAM_HZ} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            head += sock.recv(1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        # The hello: a short unmasked text frame
        header = sock.recv(2)
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(sock.recv(2), "big")
        body = b""
        while len(body) < length:
            body += sock.recv(length - len(body))
        seq = json.loads(body)["seq"]
        # By now its snapshot has gone out, so the hello's seq is ackable
        time.sleep(0.3)
        sock.sendall(_masked_text(json.dumps({"ack": seq})))
        self.sock = sock
        self.local_port = sock.getsockname()[1]

    def established(self) -> bool:
        """Whether the server's end of the connection is still open.

        Its FIN queues behind the data this client never read, so the
        client's own socket would stay ESTABLISHED long after the server
        closed or aborted it.
        """
        local, remote = f":{self.port:04X}", f":{self.local_port:04X}"
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1].endswith(local) and fields[2].endswith(remote):
                return fields[3] == "01"  # ESTABLISHED
        return False

    def close(self):
        if self.sock is not None:
            self.sock.close()


async def _rest_load(base: str, addresses, stats: dict, stop: asyncio.Event, rate_hz):
    import httpx

    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        while not stop.is_set():
            began = time.perf_counter()
            response = await client.get("/controller/dotbots")
            listed = (time.perf_counter() - began) * 1000
            stats["list_bytes"] = len(response.content)
            address = random.choice(addresses)
            x, y = random.uniform(1000, 9000), random.uniform(1000, 9000)
            began = time.perf_counter()
            await client.put(
                f"/controller/dotbots/{address}/0/waypoints",
                json={"threshold": 50, "waypoints": [{"x": x, "y": y, "z": 0}]},
            )
            posted = (time.perf_counter() - began) * 1000
            if stats["open"]:
                stats["list_ms"].add(listed)
                stats["waypoints_ms"].add(posted)
            await asyncio.sleep(max(0.0, 1 / rate_hz - (listed + posted) / 1000))


async def _wait_for_fleet(base: str, count: int, timeout_s: float):
    import httpx

    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get("/controller/dotbots")
                robots = response.json()
                if len(robots) >= count:
                    return [robot["address"] for robot in robots]
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(0.2)
    raise TimeoutError(f"the controller did not list {count} robots")


async def _drive_all(base: str, addresses):
    import httpx

    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        for address in addresses:
            x, y = random.uniform(1000, 9000), random.uniform(1000, 9000)
            await client.put(
                f"/controller/dotbots/{address}/0/waypoints",
                json={"threshold": 50, "waypoints": [{"x": x, "y": y, "z": 0}]},
            )


async def _snapshot_size(url: str) -> dict:
    """What one client connecting with a trail is sent before its first delta."""
    from websockets.asyncio.client import connect

    began = time.perf_counter()
    size = 0
    async with connect(url, max_size=None) as ws:
        while True:
            text = await asyncio.wait_for(ws.recv(), timeout=60)
            frame = json.loads(text)
            if frame["type"] == "snapshot":
                size += len(text)
                if frame["part"] == frame["parts"]:
                    break
    return {
        "snapshot_kb": round(size / 1024, 1),
        "snapshot_ms": round((time.perf_counter() - began) * 1000, 1),
    }


async def measure(
    mode,
    count,
    clients,
    warmup_s,
    window_s,
    rest_hz,
    trail,
    scratch,
    stall=False,
    slow=False,
    feeder="process",
):
    workdir = Path(tempfile.mkdtemp(prefix=f"{mode}-{count}-{clients}-", dir=scratch))
    port = _free_port()
    env = {**os.environ, "BROWSER": "true", "PYTHONPATH": str(REPO)}
    with open(workdir / "stderr.log", "w") as stderr:
        process = subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--child",
                mode,
                str(count),
                str(port),
                str(workdir),
                str(trail),
                feeder,
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            cwd=workdir,
        )
    base = f"http://127.0.0.1:{port}"
    stop = asyncio.Event()
    ws_stats = [_stream_stats() for _ in range(clients)]
    slow_stats = _stream_stats()
    rest_stats = {
        "open": False,
        "list_ms": Histogram(),
        "waypoints_ms": Histogram(),
        "list_bytes": 0,
    }
    stalled = StalledClient(port) if stall else None
    stall_view = {}
    tasks = []
    try:
        addresses = await _wait_for_fleet(base, count, timeout_s=60 + count / 10)
        if mode in ("sim", "mari"):
            await _drive_all(base, addresses)
        url = f"ws://127.0.0.1:{port}/controller/ws/stream?hz={STREAM_HZ}"
        tasks = [
            asyncio.create_task(_stream_client(url, stats, stop)) for stats in ws_stats
        ]
        if slow:
            tasks.append(
                asyncio.create_task(
                    _stream_client(url, slow_stats, stop, delay_s=SLOW_FRAME_S)
                )
            )
        tasks.append(
            asyncio.create_task(_rest_load(base, addresses, rest_stats, stop, rest_hz))
        )
        await asyncio.sleep(warmup_s)

        process.send_signal(signal.SIGUSR1)
        # A saturated loop takes its time to run the signal handler
        signalled = time.monotonic()
        while not (workdir / "threads.json").exists():
            if time.monotonic() - signalled > 60:
                raise TimeoutError("the controller did not open the window")
            await asyncio.sleep(0.1)
        roles = {
            int(k): v
            for k, v in json.loads((workdir / "threads.json").read_text()).items()
        }
        cpu_before, threads_before = _cpu_s(process.pid), _thread_cpu(process.pid)
        wall_before = time.monotonic()
        for stats in [*ws_stats, slow_stats]:
            stats["open"] = True
        rest_stats["open"] = True
        rss_peak = 0.0
        rss_start = _rss_mb(process.pid)
        if stalled is not None:
            await asyncio.to_thread(stalled.open)
            stall_view["rss_start"] = _rss_mb(process.pid)
            stall_began = time.monotonic()
        while time.monotonic() - wall_before < window_s:
            rss_peak = max(rss_peak, _rss_mb(process.pid))
            if stalled is not None and "closed_s" not in stall_view:
                if not stalled.established():
                    stall_view["closed_s"] = round(time.monotonic() - stall_began, 1)
                    stall_view["rss_at_close"] = _rss_mb(process.pid)
            await asyncio.sleep(0.5)
        rss_end = _rss_mb(process.pid)
        for stats in [*ws_stats, slow_stats]:
            stats["open"] = False
        rest_stats["open"] = False
        wall = time.monotonic() - wall_before
        cpu = _cpu_s(process.pid) - cpu_before
        threads_after = _thread_cpu(process.pid)
        snapshot = await _snapshot_size(f"{url}&trail={SNAPSHOT_TRAIL}")
    finally:
        if stalled is not None:
            stalled.close()
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()

    by_role = {}
    for tid, after in threads_after.items():
        role = roles.get(tid, "other")
        by_role[role] = by_role.get(role, 0.0) + after - threads_before.get(tid, 0.0)
    view = json.loads((workdir / "child.json").read_text())
    ages = Histogram()
    for stats in ws_stats:
        ages.merge(stats["age_ms"])
    record = {
        "mode": mode,
        "robots": count,
        "clients": clients,
        "trail": trail,
        "feeder": feeder if mode == "synth" else None,
        "window_s": round(wall, 2),
        "cpu_pct": round(100 * cpu / wall, 1),
        "cpu_pct_controller_thread": round(
            100 * by_role.get("controller", 0) / wall, 1
        ),
        "cpu_pct_simulator_threads": round(100 * by_role.get("simulator", 0) / wall, 1),
        "rss_mb_peak": round(rss_peak, 1),
        "rss_mb_growth_per_min": round((rss_end - rss_start) / wall * 60, 1),
        "loop_lag_ms": view["loop_lag_ms"],
        "ws_frames_per_client_s": round(
            statistics.mean(s["frames"] for s in ws_stats) / wall, 1
        ),
        "ws_updates_per_client_s": round(
            statistics.mean(s["updates"] for s in ws_stats) / wall, 1
        ),
        # One robot update per advertisement that changes something; a
        # Mari robot's rate is its firmware's, from the slotframe
        "ws_expected_updates_s": (
            None if mode == "mari" else round(count / ADVERTISEMENT_S, 1)
        ),
        "ws_kb_per_client_s": round(
            statistics.mean(s["bytes"] for s in ws_stats) / wall / 1024, 1
        ),
        "ws_clients_closed": sum(s["closed"] for s in ws_stats),
        "ws_update_age_ms": _percentiles(ages),
        **snapshot,
        "rest_list_kb": round(rest_stats["list_bytes"] / 1024, 1),
        "rest_list_ms": _percentiles(rest_stats["list_ms"]),
        "rest_waypoints_ms": _percentiles(rest_stats["waypoints_ms"]),
    }
    if stalled is not None:
        closed_rss = stall_view.get("rss_at_close", rss_end)
        record["stalled_closed_s"] = stall_view.get("closed_s")
        record["stalled_rss_mb_growth"] = round(closed_rss - stall_view["rss_start"], 1)
    if slow:
        record["slow_frames_s"] = round(slow_stats["frames"] / wall, 1)
        record["slow_snapshots"] = slow_stats["snapshots"]
        record["slow_closed"] = slow_stats["closed"]
    for key in ("frames_coalesced", "frames_dropped"):
        if key in view:
            record[key] = view[key]
    if "sim_ticks_per_bot_s" in view:
        record["sim_ticks_per_bot_s"] = round(view["sim_ticks_per_bot_s"], 1)
        record["sim_realtime_factor"] = round(view["sim_ticks_per_bot_s"] / 100, 3)
    return record


def stepped_simulator_cost(count: int, seconds: float = 2.0) -> dict:
    """The simulator alone on the caller's thread: CPU per robot tick."""
    sys.path.insert(0, str(REPO))
    import logging

    import structlog
    from dotbot_utils.protocol import Frame, Header, Packet

    from dotbot.dotbot_simulator import DotBotSimulatorCommunicationInterface
    from dotbot.protocol import PayloadLH2Location, PayloadLH2Waypoints

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
    )
    with tempfile.TemporaryDirectory() as tmp:
        world = Path(tmp) / "world.toml"
        _world(count, world)
        sim = DotBotSimulatorCommunicationInterface(lambda frame: None, str(world))
        for bot in sim.dotbots:
            waypoint = PayloadLH2Location(
                pos_x=int(bot.pos_x), pos_y=int(bot.pos_y) + 3000
            )
            batch = PayloadLH2Waypoints(
                threshold=50, count=1, waypoints=[waypoint], batch_id=1
            )
            header = Header(destination=int(bot.address, 16), source=0)
            sim.write(
                Frame(header=header, packet=Packet.from_payload(batch)).to_bytes()
            )
        steps = 0
        began = time.process_time()
        while time.process_time() - began < seconds:
            sim.step()
            steps += 1
        spent = time.process_time() - began
    us_per_tick = spent / (steps * count) * 1e6
    return {
        "robots": count,
        "us_per_robot_tick": round(us_per_tick, 1),
        "max_robots_realtime_one_core": int(1e6 / (us_per_tick * 100)),
    }


def table(result: dict) -> str:
    head = (
        f"{'mode':5} {'N':>4} {'K':>2} {'cpu%':>6} {'ctl%':>6} {'sim%':>6} "
        f"{'rssMB':>6} {'lag p99':>8} {'upd/s':>7} {'exp':>6} {'kB/s':>6} "
        f"{'age p50':>7} {'age p99':>8} {'list p50':>8} {'list p99':>8} "
        f"{'wp p50':>7} {'wp p99':>7} {'rt':>5}"
    )
    lines = [head, "-" * len(head)]
    for r in result["runs"]:
        if "error" in r:
            lines.append(
                f"{r['mode']:5} {r['robots']:>4} {r['clients']:>2}  {r['error']}"
            )
            continue
        lines.append(
            f"{r['mode']:5} {r['robots']:>4} {r['clients']:>2} {r['cpu_pct']:>6} "
            f"{r['cpu_pct_controller_thread']:>6} {r['cpu_pct_simulator_threads']:>6} "
            f"{r['rss_mb_peak']:>6} {_f(r['loop_lag_ms']['p99']):>8} "
            f"{r['ws_updates_per_client_s']:>7} {_f(r['ws_expected_updates_s']):>6} "
            f"{r['ws_kb_per_client_s']:>6} "
            f"{_f(r['ws_update_age_ms']['p50']):>7} "
            f"{_f(r['ws_update_age_ms']['p99']):>8} "
            f"{_f(r['rest_list_ms']['p50']):>8} {_f(r['rest_list_ms']['p99']):>8} "
            f"{_f(r['rest_waypoints_ms']['p50']):>7} "
            f"{_f(r['rest_waypoints_ms']['p99']):>7} "
            f"{r.get('sim_realtime_factor', '-'):>5}"
        )
    lines.append("")
    lines.append("simulator alone, stepped: us per robot tick, robots in real time")
    for s in result["simulator_stepped"]:
        lines.append(
            f"  N={s['robots']:>4}  {s['us_per_robot_tick']:>6} us  "
            f"{s['max_robots_realtime_one_core']:>5} robots"
        )
    return "\n".join(lines)


def _f(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def _meta() -> dict:
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.processor(),
    )
    return {
        "commit": commit,
        "python": platform.python_version(),
        "cpu": cpu,
        "cores": os.cpu_count(),
        "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _, _, mode, count, port, workdir, trail, feed = sys.argv
        child(mode, int(count), int(port), Path(workdir), int(trail), feed)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--feeder":
        feeder(int(sys.argv[2]))
        return
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "-n", "--robots", type=int, nargs="+", default=[1, 10, 50, 100, 200]
    )
    parser.add_argument("--clients", type=int, nargs="+", default=[1, 5])
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["synth", "sim"],
        choices=["synth", "sim", "mari"],
    )
    parser.add_argument(
        "--warmup", type=float, default=3.0, help="seconds before measuring"
    )
    parser.add_argument("--window", type=float, default=10.0, help="seconds measured")
    parser.add_argument(
        "--rest-hz", type=float, default=5.0, help="REST request pairs per second"
    )
    parser.add_argument(
        "--trail",
        type=int,
        default=0,
        help="points of history each robot starts with (the controller keeps 1000)",
    )
    parser.add_argument(
        "--scratch", type=Path, default=Path(tempfile.gettempdir()) / "dotbot-perf"
    )
    parser.add_argument(
        "--stall", action="store_true", help="add a client that stops reading"
    )
    parser.add_argument(
        "--slow", action="store_true", help="add a client taking 20 ms a frame"
    )
    parser.add_argument(
        "--feeder",
        choices=["process", "thread"],
        default="process",
        help="synth: build the advertisements in their own process, or on the "
        "gateway thread, which contends with the controller for the GIL",
    )
    parser.add_argument("--out", type=Path, help="JSON result file")
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    random.seed(0)

    result = {"meta": _meta(), "runs": [], "simulator_stepped": []}
    for count in args.robots:
        result["simulator_stepped"].append(stepped_simulator_cost(count))
    for mode in args.modes:
        for count in args.robots:
            for clients in args.clients:
                print(f"{mode} N={count} K={clients} ...", file=sys.stderr, flush=True)
                try:
                    record = asyncio.run(
                        measure(
                            mode,
                            count,
                            clients,
                            args.warmup,
                            args.window,
                            args.rest_hz,
                            args.trail,
                            args.scratch,
                            stall=args.stall,
                            slow=args.slow,
                            feeder=args.feeder,
                        )
                    )
                except (
                    Exception
                ) as exc:  # noqa: BLE001 - one failed run keeps the sweep
                    record = {
                        "mode": mode,
                        "robots": count,
                        "clients": clients,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                result["runs"].append(record)
                if args.out is not None:
                    args.out.write_text(json.dumps(result, indent=2))
    print(table(result))


if __name__ == "__main__":
    main()
