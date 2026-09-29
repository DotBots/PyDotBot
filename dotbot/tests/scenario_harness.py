"""The controller and the dotbot simulator in one process, on one clock.

A `Scenario` drives the real `Controller` through its REST API and the real
simulated robots through `DotBotSimulatorCommunicationInterface.step()`, so a
scenario runs faster than real time and the same way on every run. Only the
clock is replaced: the controller reads simulated seconds, and nothing waits
on the wall.

These check the simulator and the controller together, not a robot.
"""

import asyncio
import json
import logging
import math
import random
import types
from typing import Callable, Dict, List, Optional

import httpx
import structlog
import toml

import dotbot.controller as controller_module
from dotbot.adapter import DotBotSimulatorAdapter
from dotbot.controller import Controller, ControllerSettings
from dotbot.dotbot_simulator import (
    SIMULATOR_STEP_DELTA_T,
    DotBotSimulatorCommunicationInterface,
    SimulatedDotBot,
)
from dotbot.protocol import ApplicationType
from dotbot.server import api
from dotbot.sim.core import SteeringState
from dotbot.stream import HZ_MAX, StreamOptions

DOTBOT = ApplicationType.DotBot.value
# Longer than any braking run-on of the simulated wheels
RUN_ON_S = 0.5


class RecordingSocket:
    """A stream client that keeps every frame sent to it, and acks each."""

    def __init__(self, hub):
        self.hub = hub
        self.messages: List[dict] = []

    async def send_text(self, text: str):
        message = json.loads(text)
        self.messages.append(message)
        self.hub.receive(self, json.dumps({"ack": message["seq"]}))

    def robot_states(self):
        """Every robot object and patch the frames carried, in order."""
        for message in self.messages:
            if message["type"] == "snapshot":
                yield from message["robots"]
            elif message["type"] == "delta":
                yield from (p for p in message["robots"].values() if p)


class Scenario:
    """A controller and a simulated fleet sharing a stepped clock."""

    def __init__(self, tmp_path, dotbots: List[dict], seed: int = 0):
        random.seed(seed)
        world = tmp_path / "world.toml"
        world.write_text(toml.dumps({"dotbots": dotbots}))
        self.seconds = 0.0
        self._structlog = structlog.get_config()
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
        )
        self._time = controller_module.time
        controller_module.time = types.SimpleNamespace(
            time=lambda: self.seconds, monotonic=lambda: self.seconds
        )
        self.controller = Controller(
            ControllerSettings(
                adapter="dotbot-simulator",
                headless=True,
                simulator_init_state=str(world),
                log_output=str(tmp_path / "pydotbot.log"),
            )
        )
        self.sim = DotBotSimulatorCommunicationInterface(
            self.controller.handle_received_frame, str(world)
        )
        adapter = DotBotSimulatorAdapter(str(world))
        adapter.simulator = self.sim
        self.controller.adapter = adapter
        # The stream is ticked on the scenario's clock, from `run`
        hub = self.controller.stream
        hub.autostart = False
        self.socket = RecordingSocket(hub)
        hub.add(hub.client(self.socket, StreamOptions(hz=HZ_MAX)))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://scenario"
        )
        self.robots: Dict[str, SimulatedDotBot] = {
            bot.address: bot for bot in self.sim.dotbots
        }
        # Each robot's steering states in the order it went through them
        self.states: Dict[str, List[SteeringState]] = {
            address: [bot.steering_state] for address, bot in self.robots.items()
        }

    async def close(self):
        await self.client.aclose()
        controller_module.time = self._time
        structlog.configure(**self._structlog)

    # --- the clock ----------------------------------------------------------

    async def run(
        self,
        seconds: float,
        until: Optional[Callable[[], bool]] = None,
        each_tick: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Step for up to `seconds`; True as soon as `until()` holds."""
        for _ in range(round(seconds / SIMULATOR_STEP_DELTA_T)):
            self.sim.step()
            self.seconds += SIMULATOR_STEP_DELTA_T
            for address, bot in self.robots.items():
                if bot.steering_state != self.states[address][-1]:
                    self.states[address].append(bot.steering_state)
            if each_tick is not None:
                each_tick()
            self.controller.stream.tick(self.seconds)
            # Lets the stream frames the tick scheduled go out
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if until is not None and until():
                return True
        return until is None

    def reported(self, address: str, status: str) -> bool:
        """Whether the controller holds `status` for the last batch it sent."""
        dotbot = self.dotbot(address)
        return (
            self.controller.advertised_batch_ids.get(address)
            == self.controller.batch_ids.get(address)
            and dotbot.waypoints_status is not None
            and dotbot.waypoints_status.name == status
        )

    async def run_until_reported(
        self, addresses, status: str, seconds: float, each_tick=None
    ) -> bool:
        """Step until the controller reports `status` for every address, then
        for the braking run-on, so the robots are at rest on return."""
        reported = await self.run(
            seconds,
            until=lambda: all(self.reported(a, status) for a in addresses),
            each_tick=each_tick,
        )
        if reported:
            await self.run(RUN_ON_S, each_tick=each_tick)
        return reported

    # --- the controller's surface ------------------------------------------

    def dotbot(self, address: str):
        return self.controller.dotbots[address]

    async def get(self, address: str) -> dict:
        response = await self.client.get(f"/controller/dotbots/{address}")
        response.raise_for_status()
        return response.json()

    async def waypoints(self, address: str, points, threshold: int = 20, **extra):
        body = {
            "threshold": threshold,
            "waypoints": [
                (
                    {"x": p[0], "y": p[1], "z": 0}
                    if len(p) == 2
                    else {"x": p[0], "y": p[1], "z": 0, "heading_deg": p[2]}
                )
                for p in points
            ],
            **extra,
        }
        response = await self.client.put(
            f"/controller/dotbots/{address}/{DOTBOT}/waypoints", json=body
        )
        response.raise_for_status()

    async def max_speed(self, address: str, mm_s: int):
        response = await self.client.put(
            f"/controller/dotbots/{address}/{DOTBOT}/max_speed",
            json={"max_speed_mm_s": mm_s},
        )
        response.raise_for_status()

    def batch_id(self, address: str) -> int:
        """The id the controller gave the last batch it sent."""
        return self.controller.batch_ids[address]


def axle_error_mm(bot: SimulatedDotBot, x: float, y: float) -> float:
    return math.hypot(bot.pos_x - x, bot.pos_y - y)


def heading_error_deg(actual: float, wanted: float) -> float:
    return abs((actual - wanted + 180.0) % 360.0 - 180.0)


def speed_mm_s(bot: SimulatedDotBot) -> float:
    return (bot.v_left + bot.v_right) / 2.0
