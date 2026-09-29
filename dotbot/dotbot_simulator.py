# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot simulator for the DotBot project.

Each simulated robot runs the DotBot app's control firmware, `dotbot.sim.core`:
the wheel loop, the pose estimator, the waypoint steering and the
advertisement, every 10 ms tick, on a body simulated by `dotbot.sim.plant`.
"""

import functools
import heapq
import queue
import random
import threading
import time
from enum import Enum
from math import ceil, sqrt
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import toml
from dotbot_utils.protocol import Frame, Header, Packet
from pydantic import BaseModel, Field, model_validator

from dotbot import (
    DOTBOT_ADDRESS_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    SIMULATOR_INIT_STATE_DEFAULT,
    addr_to_hex,
)
from dotbot.area import Area
from dotbot.logger import LOGGER
from dotbot.protocol import DIRECTION_NONE
from dotbot.sim import core as control
from dotbot.sim.plant import (
    INITIAL_BATTERY_VOLTAGE,
    FleetPlant,
    battery_discharge_model,
)
from dotbot.site import Site

SIMULATOR_STEP_DELTA_T = 0.01  # one app tick, 10 ms

ADVERTISEMENT_INTERVAL_S = 0.5
# How far the live clock may fall behind the wall before it stops catching up
MAX_LAG_TICKS = 10
ADVERTISEMENT_TICKS = round(ADVERTISEMENT_INTERVAL_S / SIMULATOR_STEP_DELTA_T)

# Version, type, destination and source
FRAME_HEADER_BYTES = 18

MARI_SLOTFRAME_SIZE = (
    102  # fixed schedule size; slotframe ≈ 126 ms → avg latency ≈ 63 ms
)

# Where a world file's unpositioned robots go. `arena` is the area name the
# rest of the CLI already defaults to (`--points` resolves `arena:corners`).
PLACEMENT_AREA_DEFAULT = "arena"
# Where `--robots N` puts a generated fleet, and how far apart
FLEET_AREA_DEFAULT = "field"
FLEET_PITCH_MM = 200
# Headings of a generated fleet's two halves, 0 facing +y (down)
FLEET_FACING_UP, FLEET_FACING_DOWN = 180, 0
# The square a site that measures neither an extent nor an area falls back to.
PLACEMENT_EXTENT_DEFAULT_MM = 2000

# Feature order must match utils/sim_to_real/train_gru.py FEATURE_COLS
GRU_FEATURE_COLS = [
    "pwm_left",
    "pwm_right",
    "encoder_left",
    "encoder_right",
    "direction",
    "pos_x",
    "pos_y",
]
GRU_SEQ_LEN_DEFAULT = 20  # must match --seq-len used during training


class SimulatedNetworkMode(str, Enum):
    DEFAULT = "default"
    MARI = "mari"


class SimulatedNetworkSettings(BaseModel):
    pdr: int = 100
    uplink_pdr: Optional[int] = None
    downlink_pdr: Optional[int] = None
    slot_duration_ms: float = 1.236
    mqtt_latency_ms: float = 0.0

    @model_validator(mode="after")
    def _fill_mari_pdrs(self):
        if self.uplink_pdr is None:
            self.uplink_pdr = self.pdr
        if self.downlink_pdr is None:
            self.downlink_pdr = self.pdr
        return self


def _random_address() -> str:
    return f"{random.getrandbits(64):016X}"


class SimulatedDotBotSettings(BaseModel):
    """One simulated robot as a world file declares it.

    `pos_x` / `pos_y` are the axle midpoint in frame millimetres. Leaving them
    out asks for a placement inside the active site instead - see
    `place_dotbots`. A `direction` is the robot's heading, which its
    estimator starts out tracking; without one the robot faces +y and starts
    with no heading, as a real robot does from boot.
    """

    address: str = Field(default_factory=_random_address)
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None
    direction: int = DIRECTION_NONE
    calibrated: int = 0xFF
    motor_left_error: float = 0
    motor_right_error: float = 0
    lh2_noise_mm: float = 0
    gru_model_path: Path = None
    battery_model_path: Path = None
    network_mode: SimulatedNetworkMode = SimulatedNetworkMode.DEFAULT


class InitStateToml(BaseModel):
    dotbots: List[SimulatedDotBotSettings]
    network: SimulatedNetworkSettings = SimulatedNetworkSettings()


class MariNetworkSimulator:
    """TSCH slot-based network simulator modelling the Mari link layer.

    Runs on the simulator's clock: frames are scheduled from `now`, in
    simulated seconds, and `deliver()` hands over those whose slot has come.
    """

    def __init__(self, settings: SimulatedNetworkSettings, on_frame_received: Callable):
        self._settings = settings
        self._on_frame_received = on_frame_received
        self._heap: list = []
        self._seq = 0
        self.now = 0.0
        # Downlinks are scheduled from the controller's thread
        self._lock = threading.Lock()

    @property
    def min_tx_interval_us(self) -> int:
        """A joined node's minimum TX interval: the slotframe's duration."""
        return round(MARI_SLOTFRAME_SIZE * self._settings.slot_duration_ms * 1000)

    def _slot_delay_s(self, dotbot_index: int, slot_shift: int = 0) -> float:
        slotframe_duration_s = (
            MARI_SLOTFRAME_SIZE * self._settings.slot_duration_ms / 1000
        )
        slot_pos = (dotbot_index + slot_shift) % MARI_SLOTFRAME_SIZE
        slot_offset_s = slot_pos * self._settings.slot_duration_ms / 1000
        phase = self.now % slotframe_duration_s
        return (slot_offset_s - phase) % slotframe_duration_s

    def _enqueue(self, delay_s: float, fn: Callable):
        with self._lock:
            heapq.heappush(self._heap, (self.now + delay_s, self._seq, fn))
            self._seq += 1

    def schedule_uplink(self, frame, dotbot_index: int):
        if random.randint(0, 100) > self._settings.uplink_pdr:
            return
        delay = self._slot_delay_s(dotbot_index) + self._settings.mqtt_latency_ms / 1000
        self._enqueue(delay, lambda: self._on_frame_received(frame))

    def schedule_downlink(self, dotbot_index: int, deliver: Callable):
        """Call `deliver` once the robot's downlink slot has come."""
        if random.randint(0, 100) > self._settings.downlink_pdr:
            return
        # Downlink slots are in the second half of the frame — distinct from uplink slots
        delay = (
            self._slot_delay_s(dotbot_index, slot_shift=MARI_SLOTFRAME_SIZE // 2)
            + self._settings.mqtt_latency_ms / 1000
        )
        self._enqueue(delay, deliver)

    def deliver(self):
        while True:
            with self._lock:
                if not self._heap or self._heap[0][0] > self.now:
                    return
                _, _, fn = heapq.heappop(self._heap)
            fn()


def packaged_init_state_path() -> Path:
    """Absolute path to the default simulator world shipped in the package."""
    return Path(__file__).with_name(SIMULATOR_INIT_STATE_DEFAULT)


def resolve_init_state_path(path: str) -> str:
    """Resolve the simulator init-state .toml to load.

    An existing file — an explicit ``--simulator-init-state`` path, or a
    ``simulator_init_state.toml`` in the working directory — is used as
    given. When the default is requested and no such file is present,
    fall back to the world shipped inside the package, so the no-hardware
    path (``dotbot run simulator`` / ``--conn simulator``) works from any directory
    and from a pip-installed wheel. An explicit path that does not exist
    is returned unchanged so the caller gets a clear FileNotFoundError.
    """
    if Path(path).is_file():
        return path
    if path == SIMULATOR_INIT_STATE_DEFAULT:
        return str(packaged_init_state_path())
    return path


def placement_area(
    site: Optional[Site] = None, preferred: str = PLACEMENT_AREA_DEFAULT
) -> Area:
    """The rectangle a fleet is spread over.

    The site's `preferred` area, else its first declared area, else its whole
    extent, else a 2 x 2 m square at the frame origin for a site that
    measures neither.
    """
    if site is not None:
        area = site.areas.get(preferred)
        if area is not None:
            return area
        for first in site.areas.values():
            return first
        if site.extent is not None:
            return site.extent
    side = PLACEMENT_EXTENT_DEFAULT_MM
    return Area(0, 0, side, side)


def _grid_shape(count: int) -> Tuple[int, int]:
    """Columns and rows of the near-square grid `count` points fill."""
    columns = ceil(sqrt(count))
    return columns, ceil(count / columns)


def grid_positions(area: Area, count: int) -> List[Tuple[int, int]]:
    """`count` points on the cell centres of a grid covering `area`, row-major.

    Deterministic, so the same world file and site always produce the same
    fleet layout.
    """
    if count <= 0:
        return []
    cols, rows = _grid_shape(count)
    return [
        (
            int(area.x + (index % cols + 0.5) * area.w / cols),
            int(area.y + (index // cols + 0.5) * area.h / rows),
        )
        for index in range(count)
    ]


def place_dotbots(
    dotbots: List[SimulatedDotBotSettings], site: Optional[Site] = None
) -> List[SimulatedDotBotSettings]:
    """Fill in the positions a world file left out.

    A robot that gives `pos_x` / `pos_y` keeps them; the rest take grid cells
    of the site's placement area, in file order.
    """
    unplaced = [
        index
        for index, bot in enumerate(dotbots)
        if bot.pos_x is None or bot.pos_y is None
    ]
    if not unplaced:
        return list(dotbots)
    positions = grid_positions(placement_area(site), len(unplaced))
    placed = list(dotbots)
    for slot, index in enumerate(unplaced):
        bot, (x, y) = dotbots[index], positions[slot]
        placed[index] = bot.model_copy(
            update={
                "pos_x": x if bot.pos_x is None else bot.pos_x,
                "pos_y": y if bot.pos_y is None else bot.pos_y,
            }
        )
    return placed


class FleetDoesNotFit(ValueError):
    """A generated fleet larger than its area holds at the fleet pitch."""


def fleet_capacity(area: Area, pitch_mm: int = FLEET_PITCH_MM) -> int:
    """The most robots `fleet_init_state` fits in `area`."""
    max_columns, max_rows = area.w // pitch_mm, area.h // pitch_mm
    best = 0
    for columns in range(1, max_columns + 1):
        count = min(columns * columns, columns * max_rows)
        if count > (columns - 1) ** 2:
            best = count
    return best


def fleet_init_state(
    count: int, site: Optional[Site] = None, pitch_mm: int = FLEET_PITCH_MM
) -> InitStateToml:
    """`count` robots in a near-square grid `pitch_mm` apart, centred in the
    site's `field` area (see `placement_area`).

    Rows fill left to right and a short last row is centred under the
    others. The top half of the rows face up (-y), the rest down (+y).
    Raises `FleetDoesNotFit` when the grid, with half a pitch of margin all
    round, is larger than the area.
    """
    area = placement_area(site, FLEET_AREA_DEFAULT)
    columns, rows = _grid_shape(count)
    if columns * pitch_mm > area.w or rows * pitch_mm > area.h:
        where = f"{area.name} " if area.name else ""
        raise FleetDoesNotFit(
            f"{count} robots do not fit in the {where}area ({area.w} x "
            f"{area.h} mm) at {pitch_mm} mm apart; at most "
            f"{fleet_capacity(area, pitch_mm)} do."
        )
    left = area.x + (area.w - (columns - 1) * pitch_mm) // 2
    top = area.y + (area.h - (rows - 1) * pitch_mm) // 2
    dotbots = []
    for index in range(count):
        row, column = divmod(index, columns)
        shift = (columns - min(columns, count - row * columns)) * pitch_mm // 2
        dotbots.append(
            SimulatedDotBotSettings(
                address=f"DE{index:014X}",
                pos_x=left + shift + column * pitch_mm,
                pos_y=top + row * pitch_mm,
                direction=FLEET_FACING_UP if row < rows // 2 else FLEET_FACING_DOWN,
            )
        )
    return InitStateToml(dotbots=dotbots)


def init_state_toml(init_state: InitStateToml) -> str:
    """`init_state` as a world file, each robot with its address, position
    and heading."""
    return toml.dumps(
        {
            "network": {"pdr": init_state.network.pdr},
            "dotbots": [
                bot.model_dump(include={"address", "pos_x", "pos_y", "direction"})
                for bot in init_state.dotbots
            ],
        }
    )


def _load_torch_model(path: Path, what: str, logger):
    """A TorchScript model from `path`, or None if it cannot be loaded."""
    try:
        import torch  # imported lazily — not required when no model is used

        model = torch.jit.load(str(path), map_location="cpu")
        model.eval()
        logger.info(f"{what} model loaded", path=str(path))
        return model
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to load {what} model", path=str(path), error=str(exc))
        return None


class SimulatedDotBot:
    """One robot of a simulated fleet: the truth of its body, and the report
    of the firmware it runs."""

    def __init__(self, fleet: "DotBotSimulatorCommunicationInterface", index: int):
        self._fleet = fleet
        self.index = index
        self.address = fleet.addresses[index]

    # --- truth --------------------------------------------------------------

    @property
    def pos_x(self) -> float:
        return float(self._fleet.plant.x[self.index])

    @property
    def pos_y(self) -> float:
        return float(self._fleet.plant.y[self.index])

    @property
    def heading_deg(self) -> float:
        return float(self._fleet.plant.heading_deg[self.index])

    @property
    def v_left(self) -> float:
        return float(self._fleet.plant.speed[0, self.index])

    @property
    def v_right(self) -> float:
        return float(self._fleet.plant.speed[1, self.index])

    @property
    def lh2_visible(self) -> bool:
        """Whether the lighthouses see the robot, so it gets fixes."""
        return bool(self._fleet.visible[self.index])

    @lh2_visible.setter
    def lh2_visible(self, visible: bool):
        self._fleet.visible[self.index] = visible

    @property
    def held(self) -> bool:
        """Whether a hand holds the robot, so its wheels cannot turn."""
        return bool(self._fleet.plant.held[self.index])

    @held.setter
    def held(self, held: bool):
        self._fleet.plant.held[self.index] = held

    def kidnap(self, x_mm: float, y_mm: float, heading_deg: float):
        """Move the robot elsewhere at once, as a hand would."""
        self._fleet.plant.place(self.index, x_mm, y_mm, heading_deg)

    # --- the firmware's report ---------------------------------------------

    @property
    def report(self):
        """This robot's control.REPORT record."""
        return self._fleet.reports()[self.index]

    @property
    def steering_state(self) -> control.SteeringState:
        return control.SteeringState(self.report["steering_state"])

    @property
    def waypoint_index(self) -> int:
        return int(self.report["waypoint_index"])

    @property
    def estimator_status(self) -> control.PoseStatus:
        return control.PoseStatus(self.report["estimator_status"])

    @property
    def drive_mode(self) -> control.DriveMode:
        return control.DriveMode(self.report["drive_mode"])

    @property
    def batch_id(self) -> int:
        return int(self.report["batch_id"])

    @property
    def direction(self) -> int:
        """The advertised heading, DIRECTION_NONE while the estimator has none."""
        return int(self.report["direction"])


class DotBotSimulatorCommunicationInterface:
    """Bidirectional serial interface to control simulated robots.

    Each robot's control is the firmware's own, stepped for the whole fleet
    in one call per tick; each robot's body is `FleetPlant`. One clock drives
    the whole fleet: `step()` advances every robot one tick on the caller's
    thread, and `start()` runs it on a thread at the tick rate of the wall
    clock.
    """

    def __init__(
        self,
        on_frame_received: Callable,
        simulator_init_state: "str | InitStateToml",
        site: Optional[Site] = None,
    ):
        self.on_frame_received = on_frame_received
        self.ticks = 0
        self.time_elapsed_s = 0.0
        self._stop_event = threading.Event()
        self.main_thread = threading.Thread(target=self.run, daemon=True)
        self.logger = LOGGER.bind(context=__name__)
        init_state = (
            simulator_init_state
            if isinstance(simulator_init_state, InitStateToml)
            else InitStateToml(
                **toml.load(resolve_init_state_path(simulator_init_state))
            )
        )
        self._network = init_state.network
        settings = place_dotbots(init_state.dotbots, site)
        count = len(settings)
        self.addresses = [s.address.upper() for s in settings]
        headed = np.array([s.direction != DIRECTION_NONE for s in settings], bool)

        self.core = control.ControlCore(count)
        self.plant = FleetPlant(
            x=[float(s.pos_x) for s in settings],
            y=[float(s.pos_y) for s in settings],
            heading_deg=[
                float(s.direction) if h else 0.0 for s, h in zip(settings, headed)
            ],
            motor_error=[
                [s.motor_left_error for s in settings],
                [s.motor_right_error for s in settings],
            ],
            noise_mm=[s.lh2_noise_mm for s in settings],
            rng=np.random.default_rng(random.getrandbits(64)),
        )
        self.visible = np.ones(count, dtype=bool)
        self.battery = np.full(count, float(INITIAL_BATTERY_VOLTAGE))
        self._inputs = np.zeros(count, dtype=control.INPUT)
        self._inputs["elapsed_ticks"] = 1
        self._reports = None
        self._counts = np.zeros((2, count), dtype=np.int64)

        self.dotbots = [SimulatedDotBot(self, i) for i in range(count)]
        self._address_to_index = {a: i for i, a in enumerate(self.addresses)}
        gateway = int(GATEWAY_ADDRESS_DEFAULT, 16)
        self._headers = [
            Header(destination=gateway, source=int(a, 16)) for a in self.addresses
        ]
        self._calibrated = [s.calibrated & 0xFF for s in settings]
        self._dotbot_modes = [s.network_mode for s in settings]
        self._mari = None
        if any(m == SimulatedNetworkMode.MARI for m in self._dotbot_modes):
            self._mari = MariNetworkSimulator(self._network, self.on_frame_received)
            # Mari robots are joined from boot, and advertise at the rate
            # their firmware derives from the node's TX interval
            for index, mode in enumerate(self._dotbot_modes):
                if mode == SimulatedNetworkMode.MARI:
                    self.core.set_min_tx_interval(index, self._mari.min_tx_interval_us)
        # Commands for the robots, (index, packet), from the controller's thread
        self._inbound = queue.SimpleQueue()

        self._gru = {
            i: _load_torch_model(s.gru_model_path, "GRU residual", self.logger)
            for i, s in enumerate(settings)
            if s.gru_model_path is not None
        }
        self._gru = {i: m for i, m in self._gru.items() if m is not None}
        self._gru_buffers = {i: [] for i in self._gru}
        self._battery_models = {
            i: _load_torch_model(s.battery_model_path, "Battery discharge", self.logger)
            for i, s in enumerate(settings)
            if s.battery_model_path is not None
        }
        self._battery_models = {
            i: m for i, m in self._battery_models.items() if m is not None
        }
        self._battery_modelled = np.zeros(count, dtype=bool)
        self._battery_modelled[list(self._battery_models)] = True

        self._boot(headed)
        self.logger.info(
            "DotBot simulator initialized",
            robots=count,
            control_core=self.core.manifest["commit"][:12],
        )

    # --- the clock ------------------------------------------------------

    def start(self):
        self.main_thread.start()
        self.logger.info("DotBot Simulation Started")

    def run(self):
        """Step the fleet every SIMULATOR_STEP_DELTA_T of wall-clock time.

        A step that overruns is followed at once by the next; once the fleet
        is more than MAX_LAG_TICKS behind, simulated time gives up the lag
        rather than catching it up in a burst.
        """
        deadline = time.monotonic()
        while not self._stop_event.is_set():
            self.step()
            deadline += SIMULATOR_STEP_DELTA_T
            delay = deadline - time.monotonic()
            if delay > 0:
                self._stop_event.wait(delay)
            elif -delay > MAX_LAG_TICKS * SIMULATOR_STEP_DELTA_T:
                deadline = time.monotonic()

    def stop(self):
        self.logger.info("Stopping DotBot Simulation...")
        self._stop_event.set()
        if self.main_thread.is_alive():
            self.main_thread.join()

    def step(self):
        """Advance every robot one tick and hand over, before returning, the
        frames due by the end of it."""
        while True:
            try:
                index, packet = self._inbound.get_nowait()
            except queue.Empty:
                break
            self.core.rx(index, packet)
        # Fixes only for the robots whose firmware reads one this tick
        outputs = self._tick(self.visible & self.core.next_fix_due())
        self.ticks += 1
        self.time_elapsed_s += SIMULATOR_STEP_DELTA_T
        self._models_update()
        if self._mari is not None:
            self._mari.now = self.ticks * SIMULATOR_STEP_DELTA_T
        if outputs["advertise"].any():
            indices, packets = self.core.advertisements(self.battery)
            for index, packet in zip(indices.tolist(), packets):
                self._advertise(index, bytearray(packet))
        if self._mari is not None:
            self._mari.deliver()

    def _tick(self, fixes: np.ndarray) -> np.ndarray:
        """One tick of the bodies, then of the firmware reading them."""
        counts = self.plant.step(fixes)
        self._counts += counts
        inputs = self._inputs
        inputs["counts_left"] = counts[0]
        inputs["counts_right"] = counts[1]
        inputs["fix_sequence"] = self.plant.fix_sequence
        inputs["fix_x"] = self.plant.fix_x
        inputs["fix_y"] = self.plant.fix_y
        outputs = self.core.step(inputs)
        self.plant.apply(outputs)
        self._reports = None
        return outputs

    def reports(self) -> np.ndarray:
        """Every robot's control.REPORT, as of the last tick."""
        if self._reports is None:
            self._reports = self.core.reports()
        return self._reports

    # --- boot -----------------------------------------------------------

    def _boot(self, headed: np.ndarray):
        """Before the clock starts: spread the robots' advertising phases, as
        robots switched on one by one have, and seed each robot the world file
        gives a heading with its pose."""
        count = self.plant.count
        self._inputs["elapsed_ticks"] = 1 + np.arange(count) % ADVERTISEMENT_TICKS
        self._tick(np.zeros(count, dtype=bool))
        self._inputs["elapsed_ticks"] = 1
        plant = self.plant
        for index in np.flatnonzero(headed).tolist():
            self.core.seed(
                index, plant.x[index], plant.y[index], plant.heading_deg[index]
            )

    # --- models ---------------------------------------------------------

    def _models_update(self):
        """The battery, and the optional learned residual and battery models."""
        if self._gru:
            reports = self.reports()
            for index, model in self._gru.items():
                self._gru_residual(index, model, reports[index])
        linear = battery_discharge_model(self.time_elapsed_s)
        if not self._battery_models:
            self.battery[:] = linear
            return
        self.battery[~self._battery_modelled] = linear
        import torch

        reports = self.reports()
        for index, model in self._battery_models.items():
            features = torch.tensor(
                [
                    [
                        float(self.plant.pwm[0, index]),
                        float(self.plant.pwm[1, index]),
                        float(self._counts[0, index]),
                        float(self._counts[1, index]),
                        float(reports[index]["control_mode"]),
                    ]
                ],
                dtype=torch.float32,
            )
            try:
                with torch.no_grad():
                    rate = float(model(features)[0, 0])  # mV/s
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Battery model inference failed", error=str(exc))
                continue
            self.battery[index] = max(
                0.0, self.battery[index] + rate * SIMULATOR_STEP_DELTA_T
            )

    def _gru_residual(self, index: int, model, report):
        """Add the GRU's predicted (dx, dy, d_enc_left, d_enc_right) to the truth."""
        buffer = self._gru_buffers[index]
        buffer.append(
            [
                float(self.plant.pwm[0, index]),
                float(self.plant.pwm[1, index]),
                float(self._counts[0, index]),
                float(self._counts[1, index]),
                float(report["direction"]),
                float(self.plant.x[index]),
                float(self.plant.y[index]),
            ]
        )
        del buffer[:-GRU_SEQ_LEN_DEFAULT]
        if len(buffer) < GRU_SEQ_LEN_DEFAULT:
            return
        try:
            import torch

            with torch.no_grad():
                pred = model(torch.tensor([buffer], dtype=torch.float32))
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("GRU inference failed", error=str(exc))
            return
        self.plant.x[index] += float(pred[0, 0])
        self.plant.y[index] += float(pred[0, 1])
        self.plant.add_counts(index, float(pred[0, 2]), float(pred[0, 3]))

    # --- radio ----------------------------------------------------------

    def _advertise(self, index: int, packet: bytearray):
        """Send robot `index`'s advertisement, as its firmware encoded it."""
        # The calibration bitmask is the node's, not the control core's
        packet[1] = self._calibrated[index]
        self._counts[:, index] = 0
        frame = Frame(header=self._headers[index], packet=Packet.from_bytes(packet))
        if self._dotbot_modes[index] == SimulatedNetworkMode.MARI:
            self._mari.schedule_uplink(frame, index)
            return
        if not self._packet_delivered(self._network.pdr):
            self.logger.debug(
                "Packet from DotBot lost in simulation", address=self.addresses[index]
            )
            return
        self.on_frame_received(frame)

    def flush(self):
        """Flush fake serial output."""
        pass

    def _packet_delivered(self, pdr: int) -> bool:
        return random.randint(0, 100) <= pdr

    def write(self, bytes_):
        """Write bytes on the fake serial and deliver the packet to its
        addressee: every robot for the broadcast address, as the firmware's
        DB_FRAME_DST_BROADCAST check does, or only the matching one otherwise."""
        header = Header().from_bytes(bytes_[:FRAME_HEADER_BYTES])
        packet = bytes(bytes_[FRAME_HEADER_BYTES:])
        destination = addr_to_hex(int(header.destination))
        if destination == DOTBOT_ADDRESS_DEFAULT:
            targets = range(len(self.dotbots))
        else:
            index = self._address_to_index.get(destination)
            targets = [index] if index is not None else []
        for index in targets:
            if self._dotbot_modes[index] == SimulatedNetworkMode.MARI:
                self._mari.schedule_downlink(
                    index, functools.partial(self._inbound.put, (index, packet))
                )
                continue
            if not self._packet_delivered(self._network.pdr):
                self.logger.debug(
                    "Packet to DotBot lost in simulation",
                    address=self.addresses[index],
                )
                continue
            self._inbound.put((index, packet))
