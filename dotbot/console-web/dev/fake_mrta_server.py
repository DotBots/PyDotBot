"""Fake MRTA mode server for console development.

Simulates the HTTP surface dotbot-logistics' `mrta_mode` is meant to expose,
with the same shapes (see dotbot-logistics/Button.md for the contract):

- GET  /status        -> {"state": off|connecting|on|stopping, "bots": int|null,
                          "detail": str|null}
- POST /mode  {"on": bool}  -> 202 with the TRANSITION state, or 409 while one
                               is already running

The transitions are the point. Both are slow for real reasons - ON builds a
whole PIBT session from a snapshot of the fleet, OFF stops the bots and waits
for the planning tick in flight - so they are simulated with the same rough
durations rather than answered instantly. A console that only ever sees the two
settled states cannot show whether the busy affordance works.

The bot count is read live from the PyDotBot controller, because "the fleet as
it was when the session started" is exactly what the tooltip reports.

Usage: python fake_mrta_server.py [--controller http://localhost:8000] [--port 8002]
"""

import argparse
import asyncio
import json
import urllib.request

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

CONNECT_S = 3.0   # roughly what connect() costs while it waits for min_bots
STOP_S = 2.5      # stop flag -> join the tick thread -> clear every waypoint

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {"state": "off", "bots": None, "detail": None}
CONTROLLER = "http://localhost:8000"


def fleet_size() -> int:
    try:
        with urllib.request.urlopen(f"{CONTROLLER}/controller/dotbots", timeout=3) as r:
            bots = json.load(r)
        return len([b for b in bots if b.get("lh2_position") and b.get("status") != 2])
    except Exception:
        return 0


async def go_on() -> None:
    await asyncio.sleep(CONNECT_S)
    n = fleet_size()
    if n < 2:
        # What MRTAConnectionError looks like from the console: back to off,
        # with the reason where the tooltip can show it.
        STATE.update(state="off", bots=None, detail=f"only {n} DotBot(s) localised (min: 2)")
        return
    STATE.update(state="on", bots=n, detail=None)


async def go_off() -> None:
    await asyncio.sleep(STOP_S)
    STATE.update(state="off", bots=None, detail=None)


@app.get("/status")
async def status():
    return STATE


@app.post("/mode")
async def mode(request: Request):
    body = await request.json()
    want_on = bool(body.get("on"))
    if STATE["state"] in ("connecting", "stopping"):
        return JSONResponse({"detail": "already transitioning"}, status_code=409)
    if want_on and STATE["state"] == "off":
        STATE.update(state="connecting", detail="building a PIBT session from the current fleet")
        asyncio.create_task(go_on())
    elif not want_on and STATE["state"] == "on":
        STATE.update(state="stopping", detail="stopping the bots")
        asyncio.create_task(go_off())
    return JSONResponse(STATE, status_code=202)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", default=CONTROLLER)
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    CONTROLLER = args.controller
    print(f"fake MRTA server on :{args.port} (controller {CONTROLLER})")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
