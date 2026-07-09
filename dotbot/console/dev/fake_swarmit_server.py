"""Fake SwarmIT status server for console development.

Serves the two read-only endpoints the console consumes, shaped exactly like
swarmit's webserver:

- GET /status   -> {"response": {"<addr>": {device, status, battery, pos_x, pos_y}}}
- GET /settings -> {network_id, area_width, area_height, calibration_distance, auth_mode}

Bot addresses are read live from the PyDotBot controller (GET /controller/dotbots)
so the two planes join on the same ids. States are simulated: everything Running,
except a periodic Programming episode that sweeps the fleet, plus two ghost bots
that exist only on the orchestration plane (state Bootloader, not drivable) to
exercise the console's conditional-controllability UI.

Usage: python fake_swarmit_server.py [--controller http://localhost:8000] [--port 8001]
"""

import argparse
import json
import time
import urllib.request

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

GHOSTS = {
    "C0FFEE0000000001": {"pos_x": 300, "pos_y": 1800},
    "C0FFEE0000000002": {"pos_x": 1750, "pos_y": 1650},
}

PROGRAMMING_PERIOD_S = 25  # a bot enters Programming this often
PROGRAMMING_LASTS_S = 8

app = FastAPI(title="fake-swarmit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = {"controller": "http://localhost:8000"}


def fetch_dotbots() -> list:
    try:
        with urllib.request.urlopen(
            f"{settings['controller']}/controller/dotbots", timeout=2
        ) as res:
            return json.loads(res.read())
    except Exception:
        return []


@app.get("/status")
def status():
    now = time.time()
    response = {}
    bots = fetch_dotbots()
    for i, bot in enumerate(sorted(bots, key=lambda b: b["address"])):
        addr = bot["address"]
        state = "Running"
        # Deterministic Programming sweep: bot i is Programming during its slot.
        slot = int(now // PROGRAMMING_PERIOD_S) % max(len(bots), 1)
        if i == slot and (now % PROGRAMMING_PERIOD_S) < PROGRAMMING_LASTS_S:
            state = "Programming"
        pos = bot.get("lh2_position") or {}
        response[addr] = {
            "device": "DotBotV3",
            "status": state,
            "battery": int(float(bot.get("battery", 3.0)) * 1000),
            "pos_x": int(pos.get("x", 0)),
            "pos_y": int(pos.get("y", 0)),
        }
    for addr, pos in GHOSTS.items():
        response[addr] = {
            "device": "DotBotV3",
            "status": "Bootloader",
            "battery": 3900,
            "pos_x": pos["pos_x"],
            "pos_y": pos["pos_y"],
        }
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller", default="http://localhost:8000")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    settings["controller"] = args.controller
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
