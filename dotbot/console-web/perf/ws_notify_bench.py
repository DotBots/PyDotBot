"""Load check of the controller's console notification path.

Starts a simulator controller with N robots, subscribes K clients to
/controller/ws/status and measures how late each update reaches them
(receipt time minus the robot's `last_seen`), alone, alongside a client that
never reads, and alongside one that reads too slowly. Also samples the
controller's RSS. Writes <out>/ws_notify.json and prints a table.

    python perf/ws_notify_bench.py [--robots 10,100,200] [--seconds 20]
        [--out DIR] [--dotbot CMD] [--port 18200]
"""

import argparse
import asyncio
import base64
import json
import os
import platform
import re
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

AREA_MM = 2000
DROP_LINE = re.compile(r"Dropping websocket client.*?reason='([^']*)'")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def write_world(folder: Path, robots: int):
    lines = ["[network]", "pdr = 100", ""]
    for i in range(robots):
        address = f"{0xBE00000000000000 + i:016X}"
        lines += ["[[dotbots]]", f'address = "{address}"', "direction = 0", ""]
    (folder / "world.toml").write_text("\n".join(lines))
    (folder / "config.toml").write_text(
        'site = "perf"\n\n[sites.perf]\nanchor = "benchmark"\n'
        f"extent_mm = [{AREA_MM}, {AREA_MM}]\n\n"
        f"[sites.perf.areas.arena]\nx = 0\ny = 0\nw = {AREA_MM}\nh = {AREA_MM}\n"
    )


def start_controller(args, folder: Path, robots: int):
    write_world(folder, robots)
    log = open(folder / "controller.log", "w")
    cmd = [
        args.dotbot,
        "--config",
        str(folder / "config.toml"),
        "run",
        "simulator",
        "--simulator-init-state",
        str(folder / "world.toml"),
        "--controller-http-port",
        str(args.port),
        "--swarmit-url",
        f"http://127.0.0.1:{args.port + 99}",
        "--mrta-url",
        f"http://127.0.0.1:{args.port + 98}",
        "--log-level",
        "warning",
        "--headless",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=folder,
        env={**os.environ, "BROWSER": "true"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 60 + robots * 0.1
    url = f"http://127.0.0.1:{args.port}/controller/dotbots"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"controller exited, see {folder}/controller.log")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if len(json.load(response)) >= robots:
                    return proc
        except OSError:
            pass
        time.sleep(0.5)
    stop_controller(proc)
    raise RuntimeError(f"controller did not report {robots} robots in time")


def stop_controller(proc):
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def cpu_seconds(pid: int) -> float:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


class Reader:
    """A client that reads every update, optionally sleeping after each."""

    def __init__(self, url: str, delay_s: float = 0.0):
        self.url = url
        self.delay_s = delay_s
        self.latencies_ms = []
        self.received = 0
        self.closed_at = None

    async def run(self, stop: asyncio.Event, t0: float):
        try:
            # A slow reader keeps a short receive queue, so its pace reaches
            # the controller as TCP backpressure instead of piling up here.
            queue = 16 if self.delay_s else None
            async with websockets.connect(self.url, max_queue=queue) as ws:
                while not stop.is_set():
                    try:
                        text = await asyncio.wait_for(ws.recv(), 0.5)
                    except asyncio.TimeoutError:
                        continue
                    now = time.time()
                    self.received += 1
                    data = json.loads(text).get("data") or {}
                    if "last_seen" in data:
                        self.latencies_ms.append((now - data["last_seen"]) * 1000)
                    if self.delay_s:
                        await asyncio.sleep(self.delay_s)
        except (websockets.ConnectionClosed, OSError):
            self.closed_at = time.monotonic() - t0


class Stalled:
    """A client that completes the handshake and then never reads a byte."""

    def __init__(self, port: int):
        self.port = port
        self.sock = None

    def open(self):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.connect(("127.0.0.1", self.port))
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            (
                "GET /controller/ws/status HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            head += sock.recv(1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.sock = sock

    def closed_by_server(self) -> bool:
        """Drains what is buffered and reports whether the server hung up."""
        self.sock.setblocking(False)
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    return True
        except BlockingIOError:
            return False
        except ConnectionResetError:
            return True
        finally:
            self.sock.close()


def drops_in_log(log: Path, since: int):
    text = ANSI.sub("", log.read_text(errors="replace"))
    return [m.group(1) for m in DROP_LINE.finditer(text[since:])], len(text)


async def scenario(args, proc, folder, fast: int, stalled: bool, slow: bool):
    url = f"ws://127.0.0.1:{args.port}/controller/ws/status"
    log = folder / "controller.log"
    # The previous scenario's clients disconnecting log as drops too.
    await asyncio.sleep(2)
    _, log_mark = drops_in_log(log, 0)
    stop = asyncio.Event()
    t0 = time.monotonic()
    readers = [Reader(url) for _ in range(fast)]
    slow_reader = Reader(url, delay_s=args.slow_delay) if slow else None
    stall = Stalled(args.port) if stalled else None
    if stall:
        stall.open()
    tasks = [asyncio.create_task(r.run(stop, t0)) for r in readers]
    if slow_reader:
        tasks.append(asyncio.create_task(slow_reader.run(stop, t0)))
    rss = []
    cpu0 = cpu_seconds(proc.pid)
    own0 = time.process_time()
    first_drop_s = None
    while time.monotonic() - t0 < args.seconds:
        await asyncio.sleep(1)
        rss.append(rss_mb(proc.pid))
        if first_drop_s is None and drops_in_log(log, log_mark)[0]:
            first_drop_s = round(time.monotonic() - t0, 1)
    stop.set()
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - t0
    cpu = (cpu_seconds(proc.pid) - cpu0) / elapsed
    own = (time.process_time() - own0) / elapsed
    drops, _ = drops_in_log(log, log_mark)
    latencies = [x for r in readers for x in r.latencies_ms]
    result = {
        "fast_clients": fast,
        "stalled_client": stalled,
        "slow_client": slow,
        "fast_msgs_per_s_each": round(
            statistics.mean(r.received for r in readers) / elapsed, 1
        ),
        "fast_clients_closed": sum(r.closed_at is not None for r in readers),
        "latency_ms": {
            "p50": round(quantile(latencies, 0.5), 2),
            "p95": round(quantile(latencies, 0.95), 2),
            "p99": round(quantile(latencies, 0.99), 2),
            "max": round(max(latencies), 2),
        },
        # One core is 1.0; the controller's event loop cannot use more than one.
        "controller_cpu_cores": round(cpu, 2),
        # Near 1.0 means the readers here, not the controller, set the pace.
        "bench_cpu_cores": round(own, 2),
        "controller_rss_mb": {
            "start": round(rss[0], 1),
            "max": round(max(rss), 1),
            "end": round(rss[-1], 1),
        },
        "drops_logged": drops,
        "first_drop_s": first_drop_s,
    }
    if stall:
        result["stalled_closed_by_server"] = stall.closed_by_server()
    if slow_reader:
        result["slow_received"] = slow_reader.received
        result["slow_closed_at_s"] = (
            round(slow_reader.closed_at, 1) if slow_reader.closed_at else None
        )
    return result


async def run_robots(args, robots: int):
    folder = Path(args.out) / f"ws-n{robots}"
    folder.mkdir(parents=True, exist_ok=True)
    proc = start_controller(args, folder, robots)
    try:
        await asyncio.sleep(2)
        results = []
        for fast, stalled, slow in [
            (1, False, False),
            (5, False, False),
            (5, True, False),
            (5, False, True),
        ]:
            print(
                f"[n={robots}] fast={fast} stalled={stalled} slow={slow}",
                file=sys.stderr,
            )
            results.append(await scenario(args, proc, folder, fast, stalled, slow))
        return {"robots": robots, "scenarios": results}
    finally:
        stop_controller(proc)


def table(report):
    header = f"{'robots':>6} {'clients':<14} {'msg/s':>7} {'p50 ms':>7} {'p95 ms':>7} {'p99 ms':>7} {'max ms':>7} {'cpu':>5} {'rss MB start/max/end':>21}  drops"
    lines = [header]
    for run in report["runs"]:
        for s in run["scenarios"]:
            name = f"{s['fast_clients']} fast" + (
                " +stalled" if s["stalled_client"] else ""
            ) + (" +slow" if s["slow_client"] else "")
            lat = s["latency_ms"]
            rss = s["controller_rss_mb"]
            drops = ", ".join(s["drops_logged"]) or "-"
            if s["first_drop_s"] is not None:
                drops += f" (first at {s['first_drop_s']} s)"
            lines.append(
                f"{run['robots']:>6} {name:<14} {s['fast_msgs_per_s_each']:>7} {lat['p50']:>7} {lat['p95']:>7} {lat['p99']:>7} {lat['max']:>7} {s['controller_cpu_cores']:>5} "
                f"{rss['start']:>7}/{rss['max']}/{rss['end']:<7}  {drops}"
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--robots", default="10,100,200")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--slow-delay", type=float, default=0.02)
    parser.add_argument(
        "--out", default=os.path.join(tempfile.gettempdir(), "console-perf")
    )
    parser.add_argument("--dotbot", default="dotbot")
    parser.add_argument("--port", type=int, default=18200)
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    runs = [
        asyncio.run(run_robots(args, int(n))) for n in args.robots.split(",") if n
    ]
    report = {
        "schema": 1,
        "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": {"platform": platform.platform(), "cpus": os.cpu_count()},
        "options": {"seconds": args.seconds, "slow_delay_s": args.slow_delay},
        "runs": runs,
    }
    out = Path(args.out) / "ws_notify.json"
    out.write_text(json.dumps(report, indent=2))
    print(table(report))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
