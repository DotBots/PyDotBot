"""Fake SwarmIT server for console development.

Simulates the swarmit testbed server's HTTP surface with the same shapes:

- GET  /status        -> {"response": {"<addr>": {device, status, battery, pos_x, pos_y}}}
- GET  /settings      -> {network_id, area_width, area_height, calibration_distance, auth_mode}
- POST /start|/stop|/reset  {devices?}  -> state transitions
- POST /flash         {firmware_b64, devices?}  (blocking)
- POST /flash/stream  {firmware_b64, devices?}  -> SSE: flash_started / chunk /
                       device_done / complete (same event shapes as swarmit)
- GET  /events        -> SSE: log_event entries (+ periodic status snapshots)

Bot addresses are read live from the PyDotBot controller so both planes join
on the same ids; two ghost bots exist only on this plane (start in Bootloader,
never drivable). The DEVICE side is simulated; the HTTP contract is the real
one, so the console's write path exercises the same calls it will make against
a real swarmit server.

Usage: python fake_swarmit_server.py [--controller http://localhost:8000] [--port 8001]
"""

import argparse
import asyncio
import json
import time
import urllib.request

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

GHOSTS = {
    "C0FFEE0000000001": {"pos_x": 300, "pos_y": 1800},
    "C0FFEE0000000002": {"pos_x": 1750, "pos_y": 1650},
}

TOTAL_CHUNKS = 320
CHUNKS_PER_TICK = 12
TICK_S = 0.15

app = FastAPI(title="fake-swarmit")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

settings = {"controller": "http://localhost:8000"}

# Per-device simulated orchestration state.
states: dict = {}  # addr -> {"status": str, "progress": {"acked", "total"} | None}
events: list = []  # [{"id", "type": "log_event", "level", "message", "ts"}]
_event_seq = 0


def push_log(level: str, message: str) -> None:
    global _event_seq
    _event_seq += 1
    events.append(
        {
            "id": _event_seq,
            "type": "log_event",
            "level": level,
            "message": message,
            "ts": time.time(),
        }
    )
    del events[:-200]


def fetch_dotbots() -> list:
    try:
        with urllib.request.urlopen(
            f"{settings['controller']}/controller/dotbots", timeout=2
        ) as res:
            return json.loads(res.read())
    except Exception:
        return []


def known_devices() -> list:
    return sorted({b["address"] for b in fetch_dotbots()} | set(GHOSTS))


def state_of(addr: str) -> dict:
    if addr not in states:
        states[addr] = {
            "status": "Bootloader" if addr in GHOSTS else "Running",
            "progress": None,
        }
    return states[addr]


def resolve_devices(payload_devices) -> list:
    if not payload_devices:
        return known_devices()
    if isinstance(payload_devices, str):
        return [payload_devices]
    return list(payload_devices)


# --- device-info fixtures -----------------------------------------------------
#
# Shapes and vocabulary mirror swarmit's `_serialise_node` and the helpers it
# calls (`format_reset_cause`, `reset_severity`, `battery_pct`, `lh2_summary`).
# This file deliberately does NOT import swarmit: PyDotBot does not depend on
# it, and a dev harness is not the place to add a cross-repo import. The cost
# is that these tables have to be kept in step by hand if swarmit's wording
# changes, which is the normal bargain for a fake.
#
# Everything is picked deterministically from the address, so a screenshot taken
# twice looks the same.

SANDBOX_FW = "0.8.0rc3-87-gb8957de"

# (image_name, image_digest, image_size)
IMAGES = [
    ("dotbot-sandbox-dotbot-v3.bin", "c8a70af215722154", 6740),
    ("spin-sandbox-dotbot-v3.bin", "5ff0e9023306b1eb", 2292),
    ("move-sandbox-dotbot-v3.bin", "1b90c4de77a30265", 3128),
    ("rgbled-sandbox-dotbot-v3.bin", "9d31fa07c25e4418", 1984),
]

# (reset_cause, reset_severity, reset_reason, fault, fault_name, pc, lr)
# Chosen to exercise all three badge tiers. The "hung" entry is a real one: it
# is what a finished `spin` reports, pc landing in its terminal while(1).
RESETS = [
    ("power-on", "normal", 0x00000000, 0, "NoFault", 0, 0),
    ("soft-reset", "normal", 0x00000008, 0, "NoFault", 0, 0),
    ("stopped", "normal", 0x02000000, 0, "NoFault", 0, 0),
    ("lockup", "normal", 0x00000010, 0, "NoFault", 0, 0),
    (
        "hung (watchdog0 pc=0x00010230)",
        "hung",
        0x00000002,
        3,
        "WatchdogTimeout",
        0x00010230,
        0x0001022B,
    ),
    (
        "crashed (watchdog0 HardFault pc=0x2000abcd)",
        "crashed",
        0x00000002,
        1,
        "HardFault",
        0x2000ABCD,
        0x2000AB41,
    ),
]

# v3 pack: 3.0 V supercapacitor, brownout at 0.6 V, energy goes as V^2.
V_MAX_MV, V_EMPTY_MV, V_FULL_MV, V_WARN_MV = 3000, 600, 2900, 1500


def battery_fields(mv: int) -> dict:
    num = mv**2 - V_EMPTY_MV**2
    den = V_MAX_MV**2 - V_EMPTY_MV**2
    pct = max(0, min(100, int(num / den * 100)))
    level = "full" if mv > V_FULL_MV else "ok" if mv > V_WARN_MV else "low"
    return {"battery_pct": pct, "battery_level": level}


def _seed(addr: str) -> int:
    return int(addr[-8:], 16)


def device_info(addr: str) -> dict:
    seed = _seed(addr)
    name, digest, size = IMAGES[seed % len(IMAGES)]
    # A minority are uncalibrated, which is the state an operator acts on.
    homographies = 0 if seed % 9 == 0 else (2 if seed % 5 == 0 else 1)
    flags = 0 if not homographies else 0b11
    noun = "basestation" if homographies == 1 else "basestations"
    summary = (
        "uncalibrated"
        if not homographies
        else f"{homographies} {noun} (valid, from flash)"
    )
    return {
        "info_version": 1,
        "info_gen": 4,
        "boot_count": 2 + seed % 30,
        "uptime_s": 60 + seed % 9000,
        "bl_version": SANDBOX_FW,
        "net_version": SANDBOX_FW,
        "image_state": 0,
        "image_result": 1,
        "image_state_name": "Idle",
        "image_result_name": "Success",
        "image_size": size,
        "image_digest": digest,
        "image_name": name,
        "image_version": "",
        "lh2_homography_count": homographies,
        "lh2_flags": flags,
        "lh2_summary": summary,
        "raw": "8f0104" + f"{seed:08x}" * 4,
    }


def node(addr: str, status: str, battery_mv: int, x: int, y: int) -> dict:
    """One /status entry, the full shape a real swarmit daemon serves."""
    seed = _seed(addr)
    # Weighted so most of the fleet is unremarkable and the badges mean
    # something: about 5% of the fleet abnormal, split 2% a real fault and 3%
    # a deliberate exit through the deadman. A badge on one bot in twenty is
    # worth walking over to; a badge on one in five is wallpaper.
    if seed % 50 == 0:
        cause, severity, rr, fault, fault_name, pc, lr = RESETS[5]
    elif seed % 33 == 0:
        cause, severity, rr, fault, fault_name, pc, lr = RESETS[4]
    else:
        cause, severity, rr, fault, fault_name, pc, lr = RESETS[seed % 4]
    return {
        "device": "DotBotV3",
        "status": status,
        "battery": battery_mv,
        "pos_x": x,
        "pos_y": y,
        "reset_reason": rr,
        "fault": fault,
        "fault_name": fault_name,
        "reset_cause": cause,
        "reset_severity": severity,
        "from_ns": 1 if fault else 0,
        "cfsr": 0x00008200 if fault == 1 else 0,
        "sfsr": 0,
        "pc": pc,
        "lr": lr,
        "raw": "8001" + f"{seed:08x}" * 3,
        "last_updated_at": time.time(),
        "info_gen": 4,
        "info": device_info(addr),
        **battery_fields(battery_mv),
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.get("/status")
def status():
    response = {}
    for bot in fetch_dotbots():
        addr = bot["address"]
        pos = bot.get("lh2_position") or {}
        response[addr] = node(
            addr,
            state_of(addr)["status"],
            int(float(bot.get("battery", 3.0)) * 1000),
            int(pos.get("x", 0)),
            int(pos.get("y", 0)),
        )
    for addr, pos in GHOSTS.items():
        response[addr] = node(
            addr, state_of(addr)["status"], 2450, pos["pos_x"], pos["pos_y"]
        )
    return {"response": response}


@app.get("/settings")
def get_settings():
    return {
        "network_id": 0x12,
        "area_width": 2000,
        "area_height": 2000,
        "calibration_distance": 400,
        "auth_mode": "none",
    }


async def transition(devices: list, via: str, to: str, delay: float) -> None:
    for a in devices:
        state_of(a)["status"] = via
    await asyncio.sleep(delay)
    for a in devices:
        state_of(a)["status"] = to


@app.post("/start")
async def start(request: Request):
    body = (
        await request.json() if int(request.headers.get("content-length") or 0) else {}
    )
    devices = resolve_devices(body.get("devices"))
    for a in devices:
        state_of(a)["status"] = "Running"
    push_log("ok", f"testbed started · {len(devices)} device(s)")
    return {"result": "ok", "devices": devices}


@app.post("/stop")
async def stop(request: Request):
    body = (
        await request.json() if int(request.headers.get("content-length") or 0) else {}
    )
    devices = resolve_devices(body.get("devices"))
    push_log("warn", f"stopping · {len(devices)} device(s)")
    asyncio.create_task(transition(devices, "Stopping", "Bootloader", 1.2))
    return {"result": "ok", "devices": devices}


@app.post("/reset")
async def reset(request: Request):
    body = (
        await request.json() if int(request.headers.get("content-length") or 0) else {}
    )
    devices = resolve_devices(
        body.get("devices") or list(body.get("locations", {}) or {})
    )
    push_log("warn", f"resetting · {len(devices)} device(s)")
    asyncio.create_task(transition(devices, "Resetting", "Bootloader", 1.6))
    return {"result": "ok", "devices": devices}


async def flash_events(devices: list, fw_len: int):
    for a in devices:
        st = state_of(a)
        st["status"] = "Programming"
        st["progress"] = {"acked": 0, "total": TOTAL_CHUNKS}
    push_log("info", f"flash started · {len(devices)} device(s) · {fw_len} bytes")
    yield _sse(
        {
            "type": "flash_started",
            "image_size": fw_len,
            "total_chunks": TOTAL_CHUNKS,
            "fw_hash": "F4KEF4KE",
            "devices": sorted(devices),
        }
    )
    done: set = set()
    while len(done) < len(devices):
        await asyncio.sleep(TICK_S)
        for a in devices:
            if a in done:
                continue
            p = state_of(a)["progress"]
            p["acked"] = min(p["total"], p["acked"] + CHUNKS_PER_TICK)
            yield _sse(
                {"type": "chunk", "addr": a, "acked": p["acked"], "total": p["total"]}
            )
            if p["acked"] >= p["total"]:
                done.add(a)
                st = state_of(a)
                st["status"] = "Bootloader"  # flashed image sits ready; /start runs it
                st["progress"] = None
                push_log("ok", f"{a[-4:].upper()} flashed · {p['total']} chunks")
                yield _sse(
                    {
                        "type": "device_done",
                        "addr": a,
                        "success": True,
                        "retries": 0,
                        "chunks_acked": p["total"],
                        "chunks_total": p["total"],
                    }
                )
    push_log("ok", "flash complete · all devices")
    yield _sse(
        {
            "type": "complete",
            "all_success": True,
            "elapsed_s": TOTAL_CHUNKS / CHUNKS_PER_TICK * TICK_S,
        }
    )


@app.post("/flash/stream")
async def flash_stream(request: Request):
    body = await request.json()
    devices = resolve_devices(body.get("devices"))
    fw_len = len(body.get("firmware_b64", "")) * 3 // 4
    return StreamingResponse(
        flash_events(devices, fw_len), media_type="text/event-stream"
    )


@app.post("/flash")
async def flash(request: Request):
    body = await request.json()
    devices = resolve_devices(body.get("devices"))
    fw_len = len(body.get("firmware_b64", "")) * 3 // 4
    async for _ in flash_events(devices, fw_len):
        pass
    return {"result": "ok", "devices": devices}


@app.get("/events")
async def sse_events(request: Request):
    async def gen():
        last_id = max(0, _event_seq - 50)  # replay recent history on connect
        last_snapshot = 0.0
        while True:
            if await request.is_disconnected():
                return
            for ev in events:
                if ev["id"] > last_id:
                    yield _sse(ev)
                    last_id = ev["id"]
            now = time.time()
            if now - last_snapshot > 2.0:
                last_snapshot = now
                # The real daemon drops the device-info hex from the stream:
                # 310 characters per device twice a second is most of it, and
                # only `info --raw` reads it. Mirror that, so a client tested
                # here cannot come to depend on a field the real server
                # withholds (swarmit testbed/webserver.py, _serialise_node).
                snapshot = {
                    addr: {**n, "info": {**n["info"], "raw": ""}}
                    for addr, n in status()["response"].items()
                }
                yield _sse({"type": "status", "response": snapshot})
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller", default="http://localhost:8000")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    settings["controller"] = args.controller
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
