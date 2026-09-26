"""Controller backend benchmark, with and without the simulator.

For each fleet size, starts a real controller in a child process (headless,
on a free loopback port, logging as `dotbot run controller` does) and loads
it from this process: K status WebSocket clients, and REST requests on the
hot endpoints. Two modes:

- `sim`: the controller runs the dotbot simulator in-process, as
  `dotbot run simulator` does, and every robot drives a waypoint batch.
- `synth`: no simulator. A gateway adapter replays advertisements at the
  firmware's 2 Hz per robot through the same thread-to-loop queue the Mari
  edge adapter uses, so the controller's cost is measured alone.

A third, in-process figure is the simulator's own cost per robot tick on a
stepped clock, with no controller.

Writes a JSON result (one flat record per run, so thresholds can be keyed on
its fields later) and prints a text table. Linux only: it reads /proc.

    python utils/perf/bench_controller.py --out results.json
    python utils/perf/bench_controller.py -n 1 10 50 --clients 1 --window 5
"""

import argparse
import asyncio
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
SIM_THREAD_TARGETS = ("update_state", "advertise", "rx_frame", "run")


# --- the child: the controller under test ----------------------------------


class SyntheticGatewayAdapter:
    """Advertisements from `count` robots, 2 Hz each, out of phase, parsed
    from bytes on a gateway thread and handed to the loop through a queue."""

    def __init__(self, count: int):
        self.count = count
        self.sent = 0
        self._stop = threading.Event()

    def _frames(self, loop, frames: asyncio.Queue):
        from dotbot_utils.protocol import Frame, Header, Packet

        from dotbot import GATEWAY_ADDRESS_DEFAULT
        from dotbot.protocol import PayloadDotBotAdvertisement

        positions = _grid(self.count)
        start = time.monotonic()
        beat = 0
        while not self._stop.is_set():
            slot_s = ADVERTISEMENT_S / self.count
            due = start + beat * slot_s
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            index = beat % self.count
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
            wire = Frame(
                header=Header(
                    destination=int(GATEWAY_ADDRESS_DEFAULT, 16), source=0x1000 + index
                ),
                packet=Packet.from_payload(payload),
            ).to_bytes()
            loop.call_soon_threadsafe(frames.put_nowait, Frame.from_bytes(wire))
            beat += 1

    async def start(self, on_frame_received):
        frames = asyncio.Queue()
        loop = asyncio.get_running_loop()
        threading.Thread(target=self._frames, args=(loop, frames), daemon=True).start()
        while True:
            on_frame_received(await frames.get())

    def close(self):
        self._stop.set()

    def send_payload(self, destination, payload):
        self.sent += 1


def _grid(count: int):
    side = math.ceil(math.sqrt(count))
    pitch = AREA_MM / side
    return [
        (500 + (i % side + 0.5) * pitch, 500 + (i // side + 0.5) * pitch)
        for i in range(count)
    ]


def _world(count: int, path: Path):
    import toml

    dotbots = [
        {
            "address": f"{0x1000 + i:016X}",
            "pos_x": int(x),
            "pos_y": int(y),
            "direction": 0,
        }
        for i, (x, y) in enumerate(_grid(count))
    ]
    path.write_text(toml.dumps({"dotbots": dotbots}))


def child(mode: str, count: int, port: int, workdir: Path, trail: int):
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
    if mode == "sim":
        world = workdir / "world.toml"
        _world(count, world)
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
                controller.dotbots[address].position_history = [
                    DotBotLH2Position(x=i, y=i) for i in range(trail)
                ]

        controller.handle_received_frame = handle_with_trail
    if mode == "synth":
        synthetic = SyntheticGatewayAdapter(count)

        async def start_adapter():
            controller.adapter = synthetic
            await synthetic.start(controller.handle_received_frame)

        controller._start_adapter = start_adapter

    lags = []
    window = {}

    def robots():
        simulator = getattr(controller.adapter, "simulator", None)
        return simulator.dotbots if simulator is not None else []

    def open_window():
        lags.clear()
        window["start"] = time.monotonic()
        window["ticks"] = sum(bot.ticks for bot in robots())
        window["threads"] = {
            thread.native_id: _role(thread) for thread in threading.enumerate()
        }
        (workdir / "threads.json").write_text(json.dumps(window["threads"]))

    def close_window():
        elapsed = time.monotonic() - window.get("start", time.monotonic())
        ticks = sum(bot.ticks for bot in robots()) - window.get("ticks", 0)
        result = {"window_s": elapsed, "loop_lag_ms": lags}
        if robots():
            result["sim_ticks_per_bot_s"] = ticks / len(robots()) / elapsed
        (workdir / "child.json").write_text(json.dumps(result))
        os._exit(0)

    async def lag_monitor():
        period = 0.02
        while True:
            before = time.monotonic()
            await asyncio.sleep(period)
            lags.append((time.monotonic() - before - period) * 1000)

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


def _percentiles(samples) -> dict:
    if not samples:
        return {"p50": None, "p99": None, "max": None, "count": 0}
    ordered = sorted(samples)
    return {
        "p50": round(statistics.median(ordered), 2),
        "p99": round(ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))], 2),
        "max": round(ordered[-1], 2),
        "count": len(ordered),
    }


async def _status_client(url: str, stats: dict, stop: asyncio.Event):
    from websockets.asyncio.client import connect

    async with connect(url, max_size=None) as ws:
        while not stop.is_set():
            try:
                text = await asyncio.wait_for(ws.recv(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            now = time.time()
            if not stats["open"]:
                continue
            stats["messages"] += 1
            data = json.loads(text).get("data") or {}
            if "last_seen" in data:
                stats["latency_ms"].append((now - data["last_seen"]) * 1000)


async def _rest_load(base: str, addresses, stats: dict, stop: asyncio.Event, rate_hz):
    import httpx

    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        while not stop.is_set():
            began = time.perf_counter()
            await client.get("/controller/dotbots")
            listed = (time.perf_counter() - began) * 1000
            address = random.choice(addresses)
            x, y = random.uniform(1000, 9000), random.uniform(1000, 9000)
            began = time.perf_counter()
            await client.put(
                f"/controller/dotbots/{address}/0/waypoints",
                json={"threshold": 50, "waypoints": [{"x": x, "y": y, "z": 0}]},
            )
            posted = (time.perf_counter() - began) * 1000
            if stats["open"]:
                stats["list_ms"].append(listed)
                stats["waypoints_ms"].append(posted)
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


async def measure(mode, count, clients, warmup_s, window_s, rest_hz, trail, scratch):
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
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            cwd=workdir,
        )
    base = f"http://127.0.0.1:{port}"
    stop = asyncio.Event()
    ws_stats = [
        {"open": False, "messages": 0, "latency_ms": []} for _ in range(clients)
    ]
    rest_stats = {"open": False, "list_ms": [], "waypoints_ms": []}
    tasks = []
    try:
        addresses = await _wait_for_fleet(base, count, timeout_s=60 + count / 10)
        if mode == "sim":
            await _drive_all(base, addresses)
        url = f"ws://127.0.0.1:{port}/controller/ws/status"
        tasks = [
            asyncio.create_task(_status_client(url, stats, stop)) for stats in ws_stats
        ]
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
        for stats in ws_stats:
            stats["open"] = True
        rest_stats["open"] = True
        rss_peak = 0.0
        while time.monotonic() - wall_before < window_s:
            rss_peak = max(rss_peak, _rss_mb(process.pid))
            await asyncio.sleep(0.5)
        for stats in ws_stats:
            stats["open"] = False
        rest_stats["open"] = False
        wall = time.monotonic() - wall_before
        cpu = _cpu_s(process.pid) - cpu_before
        threads_after = _thread_cpu(process.pid)
    finally:
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
    latencies = [x for stats in ws_stats for x in stats["latency_ms"]]
    record = {
        "mode": mode,
        "robots": count,
        "clients": clients,
        "trail": trail,
        "window_s": round(wall, 2),
        "cpu_pct": round(100 * cpu / wall, 1),
        "cpu_pct_controller_thread": round(
            100 * by_role.get("controller", 0) / wall, 1
        ),
        "cpu_pct_simulator_threads": round(100 * by_role.get("simulator", 0) / wall, 1),
        "rss_mb_peak": round(rss_peak, 1),
        "loop_lag_ms": _percentiles(view["loop_lag_ms"]),
        "ws_msgs_per_client_s": round(
            statistics.mean(s["messages"] for s in ws_stats) / wall, 1
        ),
        # One UPDATE per advertisement, and one per waypoint request
        "ws_expected_msgs_s": round(count / ADVERTISEMENT_S + rest_hz, 1),
        "ws_latency_ms": _percentiles(latencies),
        "rest_list_ms": _percentiles(rest_stats["list_ms"]),
        "rest_waypoints_ms": _percentiles(rest_stats["waypoints_ms"]),
    }
    if "sim_ticks_per_bot_s" in view:
        record["sim_ticks_per_bot_s"] = round(view["sim_ticks_per_bot_s"], 1)
        record["sim_realtime_factor"] = round(view["sim_ticks_per_bot_s"] / 100, 3)
    return record


def stepped_simulator_cost(count: int, seconds: float = 2.0) -> dict:
    """The simulator alone on the caller's thread: CPU per robot tick."""
    sys.path.insert(0, str(REPO))
    import logging

    import structlog

    from dotbot.dotbot_simulator import DotBotSimulatorCommunicationInterface

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
    )
    with tempfile.TemporaryDirectory() as tmp:
        world = Path(tmp) / "world.toml"
        _world(count, world)
        sim = DotBotSimulatorCommunicationInterface(lambda frame: None, str(world))
        for bot in sim.dotbots:
            bot.steering.set_target(bot.pos_x, bot.pos_y + 3000, 50)
            bot.drive_mode = 3  # WAYPOINT: the steering runs every tick
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
        f"{'rssMB':>6} {'lag p99':>8} {'ws/s':>7} {'exp':>6} {'ws p50':>7} "
        f"{'ws p99':>8} {'list p50':>8} {'list p99':>8} {'wp p50':>7} "
        f"{'wp p99':>7} {'rt':>5}"
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
            f"{r['ws_msgs_per_client_s']:>7} {r['ws_expected_msgs_s']:>6} "
            f"{_f(r['ws_latency_ms']['p50']):>7} {_f(r['ws_latency_ms']['p99']):>8} "
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
        _, _, mode, count, port, workdir, trail = sys.argv
        child(mode, int(count), int(port), Path(workdir), int(trail))
        return
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "-n", "--robots", type=int, nargs="+", default=[1, 10, 50, 100, 200]
    )
    parser.add_argument("--clients", type=int, nargs="+", default=[1, 5])
    parser.add_argument(
        "--modes", nargs="+", default=["synth", "sim"], choices=["synth", "sim"]
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
