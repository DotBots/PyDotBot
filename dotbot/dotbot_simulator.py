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
import math
import queue
import random
import threading
import time
from enum import Enum, IntEnum
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
    kinematics,
)
from dotbot.area import Area
from dotbot.logger import LOGGER
from dotbot.protocol import (
    AXLE_UNKNOWN,
    DIRECTION_NONE,
    ControlModeType,
    PayloadCommandWheelVelocity,
    PayloadControlMode,
    PayloadDotBotAdvertisement,
    PayloadType,
    WaypointsAbortReason,
    WaypointsStatus,
)
from dotbot.robots import robot_geometry
from dotbot.sim import core as control
from dotbot.sim.plant import WHEEL_TAU_S, FleetPlant
from dotbot.site import Site
from dotbot.steering import (
    LEVER_ARM_EFFECTIVE_MM,
    PERIOD_TICKS,
    Completion,
    Output,
    Pose,
    PoseStatus,
    Steering,
    SteeringConf,
    SteeringState,
    forward,
    path_from_payload,
    track_effective_mm,
    wrap180,
)

_GEOMETRY = robot_geometry()

Kv = 700  # motor speed constant in RPM
R = _GEOMETRY.gear_ratio  # motor reduction ratio
D = _GEOMETRY.wheel_diameter_mm
L = _GEOMETRY.track_mm  # distance between the two wheels in mm
ENCODER_CPR = _GEOMETRY.encoder_cpr  # counts per motor shaft revolution
MM_PER_COUNT = _GEOMETRY.mm_per_count

SIMULATOR_STEP_DELTA_T = 0.01  # one app tick, 10 ms
TICKS_PER_POSITION = 10  # a new LH2 fix every 100 ms
TICKS_PER_TIMEOUT = 20
# ~500 ms without a raw or wheel velocity command stops the wheels
TIMEOUT_STOP_TICKS = 52

WHEEL_SPEED_MAX_MM_S = 700
MAX_SPEED_MIN_MM_S = 20
MAX_SPEED_MAX_MM_S = 700

# The duty the advertisement reports for a wheel speed: the wheel loop's
# running feedforward line
PWM_RUN = 32.0
PWM_PER_MM_S = 0.097

# Pose estimator life cycle (DotBot-libs drv/pose_estimator.h)
ESTIMATOR_SEED_FIXES = 3
ESTIMATOR_ACQUIRE_MM = 40.0
ESTIMATOR_TIMEOUT_TICKS = 100

# Battery model parameters
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION = 60 * 60 * 3  # 3 hours in seconds

ADVERTISEMENT_INTERVAL_S = 0.5
# How far the live clock may fall behind the wall before it stops catching up
MAX_LAG_TICKS = 10
ADVERTISEMENT_TICKS = round(ADVERTISEMENT_INTERVAL_S / SIMULATOR_STEP_DELTA_T)

# Robots the world file gives a heading acquire it before the clock starts,
# driving straight out and back
PREROLL_SPEED_MM_S = 100
PREROLL_MAX_TICKS = 300
PREROLL_SETTLE_TICKS = 60
# Direct driving stops without a command for ~0.5 s, so it is repeated sooner
COMMAND_REPEAT_TICKS = 20

# Version, type, destination and source
FRAME_HEADER_BYTES = 18

MARI_SLOTFRAME_SIZE = (
    102  # fixed schedule size; slotframe ≈ 126 ms → avg latency ≈ 63 ms
)

# Where a world file's unpositioned robots go. `arena` is the area name the
# rest of the CLI already defaults to (`--points` resolves `arena:corners`).
PLACEMENT_AREA_DEFAULT = "arena"
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


def battery_discharge_model(time_elapsed_s: float) -> int:
    """Linear discharge over MAX_BATTERY_DURATION (supercapacitor idle model)."""
    t = min(time_elapsed_s / MAX_BATTERY_DURATION, 1.0)
    return max(0, int(INITIAL_BATTERY_VOLTAGE * (1 - t)))


def wheel_speed_from_pwm(pwm: float) -> float:
    """Convert a PWM value to a wheel speed in mm/s."""
    if pwm > 100:
        pwm = 100
    if pwm < -100:
        pwm = -100
    return pwm * D * Kv / (R * 127)


def pwm_from_wheel_speed(speed_mm_s: float) -> int:
    """The duty the wheel loop drives a wheel speed with."""
    if speed_mm_s == 0:
        return 0
    duty = min(100.0, PWM_RUN + PWM_PER_MM_S * abs(speed_mm_s))
    return int(math.copysign(duty, speed_mm_s))


def _lround(value: float) -> int:
    """C lroundf: halves away from zero."""
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


class DriveMode(IntEnum):
    """Who writes the motors, as the app's drive_mode_t."""

    IDLE = 0
    RAW = 1
    VELOCITY = 2
    WAYPOINT = 3


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
    `place_dotbots`. A `direction` is the robot's heading and starts its
    estimator tracking; without one the robot faces +y and starts with no
    heading, as a real robot does from boot.
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


class DotBotSimulator:
    """One simulated robot running the sandbox dotbot app."""

    def __init__(
        self,
        settings: SimulatedDotBotSettings,
        tx_queue: queue.Queue,
        steering_conf: SteeringConf = SteeringConf(),
    ):
        self.address = settings.address.upper()
        # Truth: the axle midpoint and the heading, 0 facing +y, clockwise
        self.pos_x = float(settings.pos_x or 0)
        self.pos_y = float(settings.pos_y or 0)
        has_heading = settings.direction != DIRECTION_NONE
        self.heading_deg = wrap180(float(settings.direction)) if has_heading else 0.0
        self.motor_left_error = settings.motor_left_error
        self.motor_right_error = settings.motor_right_error
        self.lh2_noise_mm = settings.lh2_noise_mm
        self.time_elapsed_s = 0.0
        self.ticks = 0

        # Wheels: actual speeds, and the wheel loop's setpoints
        self.v_left = 0.0
        self.v_right = 0.0
        self.setpoint_left = 0.0
        self.setpoint_right = 0.0
        self.pwm_left = 0
        self.pwm_right = 0
        self.drive_mode = DriveMode.IDLE
        self._last_command_tick = 0
        # Wheel travel not yet reported in an advertisement, in counts
        self._encoder_left = 0.0
        self._encoder_right = 0.0

        # Estimator life cycle; its pose, when it has one, is the truth
        self.lh2_visible = True
        self.estimator_status = (
            PoseStatus.TRACKING if has_heading else PoseStatus.SEEDING
        )
        self._chain_count = 0
        self._chain_x = 0.0
        self._chain_y = 0.0
        self._ticks_since_accept = 0
        self._last_fix: Optional[Tuple[float, float]] = None

        self.steering = Steering(steering_conf)
        self._steering_brake = False
        self.batch_id = 0
        self._abort_reason = WaypointsAbortReason.STOP

        self.calibrated = settings.calibrated

        self.logger = LOGGER.bind(context=__name__, address=self.address)
        self._gru_model = None
        self._gru_buffer: list[list[float]] = []
        if settings.gru_model_path is not None:
            self._gru_model = self._load_gru_model(settings.gru_model_path)

        self._battery_model = None
        self.battery_voltage: float = float(INITIAL_BATTERY_VOLTAGE)
        if settings.battery_model_path is not None:
            self._battery_model = self._load_battery_model(settings.battery_model_path)

        self.tx_queue = tx_queue
        self.queue = queue.Queue()
        self.logger.info(
            "DotBot simulator initialized",
            pos_x=self.pos_x,
            pos_y=self.pos_y,
            heading=self.heading_deg if has_heading else None,
        )

    def _load_gru_model(self, path: Path):
        """Load a TorchScript GRU residual model from *path*."""
        try:
            import torch  # imported lazily — not required when model is unused

            model = torch.jit.load(str(path), map_location="cpu")
            model.eval()
            self.logger.info("GRU residual model loaded", path=str(path))
            return model
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "Failed to load GRU model", path=str(path), error=str(exc)
            )
            return None

    def _load_battery_model(self, path: Path):
        """Load a TorchScript battery discharge model from *path*."""
        try:
            import torch  # imported lazily — not required when model is unused

            model = torch.jit.load(str(path), map_location="cpu")
            model.eval()
            self.logger.info("Battery discharge model loaded", path=str(path))
            return model
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "Failed to load battery model", path=str(path), error=str(exc)
            )
            return None

    def _gru_residual(self) -> tuple[float, float, float, float]:
        """Return (dx, dy, d_enc_left, d_enc_right) predicted by the GRU, or zeros."""
        if self._gru_model is None or len(self._gru_buffer) < GRU_SEQ_LEN_DEFAULT:
            return 0.0, 0.0, 0.0, 0.0
        try:
            import torch

            seq = self._gru_buffer[-GRU_SEQ_LEN_DEFAULT:]
            x = torch.tensor([seq], dtype=torch.float32)  # (1, seq_len, n_features)
            with torch.no_grad():
                pred = self._gru_model(x)  # (1, 4)
            return (
                float(pred[0, 0]),
                float(pred[0, 1]),
                float(pred[0, 2]),
                float(pred[0, 3]),
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("GRU inference failed", error=str(exc))
            return 0.0, 0.0, 0.0, 0.0

    @property
    def header(self):
        return Header(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
        )

    # --- Truth and the plant ------------------------------------------------

    @property
    def controller_mode(self) -> ControlModeType:
        """The advertisement's mode: AUTO while a batch is in progress."""
        return ControlModeType.AUTO if self.steering.active else ControlModeType.MANUAL

    @property
    def direction(self) -> int:
        """The advertised heading: the estimator's while it tracks, else
        DIRECTION_NONE."""
        if self.estimator_status != PoseStatus.TRACKING:
            return DIRECTION_NONE
        heading = _lround(self.heading_deg)
        return heading - 360 if heading >= 180 else heading

    @property
    def photodiode(self) -> Tuple[float, float]:
        fx, fy = forward(self.heading_deg)
        return (
            self.pos_x + LEVER_ARM_EFFECTIVE_MM * fx,
            self.pos_y + LEVER_ARM_EFFECTIVE_MM * fy,
        )

    def _move_body(self, dl: float, dr: float):
        """Move the truth by a travel of each wheel, in mm."""
        d = (dl + dr) / 2.0
        dtheta = (dl - dr) / track_effective_mm(dl, dr) * 180.0 / math.pi
        fx, fy = forward(self.heading_deg + dtheta / 2.0)
        self.pos_x += d * fx
        self.pos_y += d * fy
        self.heading_deg = wrap180(self.heading_deg + dtheta)

    def diff_drive_model_update(self, dt=SIMULATOR_STEP_DELTA_T):
        """Move open loop on the reported duties alone, with no wheel lag.

        What the controller's twin of a real robot runs on.
        """
        v_left = wheel_speed_from_pwm(self.pwm_left) * (1 - self.motor_left_error)
        v_right = wheel_speed_from_pwm(self.pwm_right) * (1 - self.motor_right_error)
        self._move_body(v_left * dt, v_right * dt)
        self._models_update(dt)

    def _wheel_targets(self) -> Tuple[float, float]:
        if self._steering_brake:
            return 0.0, 0.0
        if self.drive_mode == DriveMode.RAW:
            # Open-loop duty: the motor error shows in the wheel speeds
            return (
                wheel_speed_from_pwm(self.pwm_left) * (1 - self.motor_left_error),
                wheel_speed_from_pwm(self.pwm_right) * (1 - self.motor_right_error),
            )
        return self.setpoint_left, self.setpoint_right

    def _wheel_service(self, dt: float):
        target_left, target_right = self._wheel_targets()
        gain = 1.0 - math.exp(-dt / WHEEL_TAU_S)
        v_left = self.v_left + gain * (target_left - self.v_left)
        v_right = self.v_right + gain * (target_right - self.v_right)
        dl = (self.v_left + v_left) / 2.0 * dt
        dr = (self.v_right + v_right) / 2.0 * dt
        self.v_left, self.v_right = v_left, v_right
        if abs(self.v_left) < 0.1 and target_left == 0:
            self.v_left = 0.0
        if abs(self.v_right) < 0.1 and target_right == 0:
            self.v_right = 0.0
        self._encoder_left += dl / MM_PER_COUNT
        self._encoder_right += dr / MM_PER_COUNT
        self._move_body(dl, dr)
        if self.drive_mode != DriveMode.RAW:
            if self._steering_brake:
                self.pwm_left = self.pwm_right = 0
            else:
                self.pwm_left = pwm_from_wheel_speed(self.setpoint_left)
                self.pwm_right = pwm_from_wheel_speed(self.setpoint_right)

    # --- Estimator ------------------------------------------------------

    def kidnap(self, x_mm: float, y_mm: float, heading_deg: float):
        """Move the robot by hand: the estimator loses its heading until
        motion re-acquires it."""
        self.pos_x, self.pos_y = float(x_mm), float(y_mm)
        self.heading_deg = wrap180(float(heading_deg))
        self.estimator_status = PoseStatus.SEEDING
        self._chain_count = 0

    def _estimator_predict(self):
        self._ticks_since_accept += 1
        if (
            self.estimator_status == PoseStatus.TRACKING
            and self._ticks_since_accept > ESTIMATOR_TIMEOUT_TICKS
        ):
            self.estimator_status = PoseStatus.LOST

    def _estimator_update(self, x: float, y: float):
        """A chain of fixes seeds the pose once the photodiode has moved
        ESTIMATOR_ACQUIRE_MM from the first of them; any later fix is accepted."""
        if self.estimator_status != PoseStatus.SEEDING:
            self.estimator_status = PoseStatus.TRACKING
            self._ticks_since_accept = 0
            return
        if self._chain_count == 0:
            self._chain_x, self._chain_y = x, y
            self._chain_count = 1
            return
        self._chain_count += 1
        travel = math.hypot(x - self._chain_x, y - self._chain_y)
        if self._chain_count >= ESTIMATOR_SEED_FIXES and travel >= ESTIMATOR_ACQUIRE_MM:
            self.estimator_status = PoseStatus.TRACKING
            self._ticks_since_accept = 0
            self._chain_count = 0

    def _position_poll(self):
        if not self.lh2_visible:
            return
        x, y = self.photodiode
        if self.lh2_noise_mm > 0:
            x += random.gauss(0, self.lh2_noise_mm)
            y += random.gauss(0, self.lh2_noise_mm)
        self._last_fix = (x, y)
        self._estimator_update(x, y)
        self.steering.fix(x, y)

    def _pose(self) -> Pose:
        return Pose(self.estimator_status, self.pos_x, self.pos_y, self.heading_deg)

    # --- The app's tick -------------------------------------------------

    def tick(self):
        """One 10 ms tick of the app, and of the plant under it."""
        self.ticks += 1
        self._wheel_service(SIMULATOR_STEP_DELTA_T)
        self._estimator_predict()
        if self.ticks % TICKS_PER_POSITION == 0:
            self._position_poll()
        if self.ticks % PERIOD_TICKS == 0 and self.drive_mode == DriveMode.WAYPOINT:
            out = Output()
            self.steering.step(self._pose(), PERIOD_TICKS, out)
            self._steering_apply(out)
        if self.drive_mode == DriveMode.WAYPOINT:
            out = Output()
            if self.steering.poll(self._pose(), out):
                self._steering_apply(out)
        if self.ticks % TICKS_PER_TIMEOUT == 0:
            self._timeout_check()
        self._models_update(SIMULATOR_STEP_DELTA_T)

    def _steering_apply(self, out: Output):
        if out.brake:
            if not self._steering_brake:
                self.setpoint_left = self.setpoint_right = 0.0
                self._steering_brake = True
            return
        self._steering_brake = False
        # Past the wheel limit, both wheels give up the excess, so the turn is kept
        left, right = out.left_mm_s, out.right_mm_s
        excess = max(abs(left), abs(right)) - WHEEL_SPEED_MAX_MM_S
        if excess > 0:
            shift = excess if left + right >= 0 else -excess
            left -= shift
            right -= shift
        limit = WHEEL_SPEED_MAX_MM_S
        self.setpoint_left = max(-limit, min(limit, left))
        self.setpoint_right = max(-limit, min(limit, right))

    def _timeout_check(self):
        if (
            self.drive_mode not in (DriveMode.IDLE, DriveMode.WAYPOINT)
            and self.ticks - self._last_command_tick > TIMEOUT_STOP_TICKS
        ):
            self._drive_stop()

    def _enter_drive_mode(self, mode: DriveMode):
        if mode != DriveMode.WAYPOINT:
            self.steering.stop()
        self._steering_brake = False
        self.drive_mode = mode
        self.setpoint_left = self.setpoint_right = 0.0

    def _drive_stop(self):
        self._enter_drive_mode(DriveMode.IDLE)
        self.pwm_left = self.pwm_right = 0

    def _note_abort(self, reason: WaypointsAbortReason):
        if self.steering.active:
            self._abort_reason = reason

    def _models_update(self, dt: float):
        """The optional learned residual and battery models."""
        if self._gru_model is not None:
            self._gru_buffer.append(
                [
                    float(self.pwm_left),
                    float(self.pwm_right),
                    float(self._encoder_left),
                    float(self._encoder_right),
                    float(self.direction),
                    float(self.pos_x),
                    float(self.pos_y),
                ]
            )
            if len(self._gru_buffer) > GRU_SEQ_LEN_DEFAULT:
                self._gru_buffer.pop(0)
            res_x, res_y, res_enc_l, res_enc_r = self._gru_residual()
            self.pos_x += res_x
            self.pos_y += res_y
            self._encoder_left += res_enc_l
            self._encoder_right += res_enc_r

        self.time_elapsed_s += dt
        if self._battery_model is not None:
            try:
                import torch

                features = torch.tensor(
                    [
                        [
                            float(self.pwm_left),
                            float(self.pwm_right),
                            float(self._encoder_left),
                            float(self._encoder_right),
                            float(int(self.controller_mode)),
                        ]
                    ],
                    dtype=torch.float32,
                )
                with torch.no_grad():
                    rate = float(self._battery_model(features)[0, 0])  # mV/s
                self.battery_voltage = max(0.0, self.battery_voltage + rate * dt)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Battery model inference failed", error=str(exc))
        else:
            self.battery_voltage = battery_discharge_model(self.time_elapsed_s)

    # --- Radio ----------------------------------------------------------

    def advertisement(self) -> PayloadDotBotAdvertisement:
        """The app's advertisement, taking the encoder counts it reports."""
        steering = self.steering
        if self.estimator_status == PoseStatus.TRACKING:
            position = self.photodiode
        else:
            position = self._last_fix or (0.0, 0.0)
        encoder_left = int(self._encoder_left)
        encoder_right = int(self._encoder_right)
        self._encoder_left -= encoder_left
        self._encoder_right -= encoder_right
        waypoint_x = waypoint_y = 0
        if steering.state != SteeringState.IDLE:
            waypoint_x = _lround(steering.target.x_mm)
            waypoint_y = _lround(steering.target.y_mm)
        status, reason = {
            Completion.IN_PROGRESS: (WaypointsStatus.IN_PROGRESS, 0),
            Completion.ARRIVED: (WaypointsStatus.ARRIVED, 0),
            Completion.FAILED: (WaypointsStatus.FAILED, int(steering.fail)),
            Completion.ABORTED: (WaypointsStatus.ABORTED, int(self._abort_reason)),
        }.get(steering.completion, (WaypointsStatus.NONE, 0))
        axle_x = axle_y = AXLE_UNKNOWN
        if (
            self.estimator_status == PoseStatus.TRACKING
            and 0 <= self.pos_x < AXLE_UNKNOWN
            and 0 <= self.pos_y < AXLE_UNKNOWN
        ):
            axle_x, axle_y = _lround(self.pos_x), _lround(self.pos_y)
        return PayloadDotBotAdvertisement(
            calibrated=self.calibrated,
            direction=self.direction,
            pos_x=max(0, _lround(position[0])),
            pos_y=max(0, _lround(position[1])),
            battery=int(self.battery_voltage),
            pwm_left=int(self.pwm_left),
            pwm_right=int(self.pwm_right),
            mode=int(self.controller_mode),
            encoder_left=encoder_left,
            encoder_right=encoder_right,
            waypoint_x=waypoint_x,
            waypoint_y=waypoint_y,
            waypoint_idx=steering.index,
            waypoints_status=int(status),
            waypoints_reason=reason,
            batch_id=self.batch_id,
            max_speed_10mm=_lround(steering.v_max_mm_s / 10.0),
            axle_x=axle_x,
            axle_y=axle_y,
            report=True,
        )

    def _advertisement_frame(self) -> Frame:
        return Frame(
            header=self.header, packet=Packet.from_payload(self.advertisement())
        )

    def handle_payload(self, payload_type: PayloadType, payload):
        """Apply one command, as the app's _rx_process()."""
        if payload_type in (
            PayloadType.CMD_MOVE_RAW,
            PayloadType.CMD_WHEEL_VELOCITY,
            PayloadType.LH2_WAYPOINTS,
        ):
            self._last_command_tick = self.ticks
        if payload_type == PayloadType.CMD_MOVE_RAW:
            left, right = payload.left_y, payload.right_y
            left = left - 256 if left > 127 else left
            right = right - 256 if right > 127 else right
            self._note_abort(WaypointsAbortReason.DIRECT)
            self._enter_drive_mode(DriveMode.RAW)
            self.pwm_left = int(100 * (left / 127))
            self.pwm_right = int(100 * (right / 127))
            self.logger.debug(
                "RAW command received", pwm_left=self.pwm_left, pwm_right=self.pwm_right
            )
        elif payload_type == PayloadType.CMD_WHEEL_VELOCITY:
            if self.drive_mode != DriveMode.VELOCITY:
                self._note_abort(WaypointsAbortReason.DIRECT)
                self._enter_drive_mode(DriveMode.VELOCITY)
            limit = WHEEL_SPEED_MAX_MM_S
            self.setpoint_left = max(-limit, min(limit, payload.left_mm_s))
            self.setpoint_right = max(-limit, min(limit, payload.right_mm_s))
            self.logger.debug(
                "Wheel velocity command received",
                left_mm_s=payload.left_mm_s,
                right_mm_s=payload.right_mm_s,
            )
        elif payload_type == PayloadType.LH2_WAYPOINTS:
            path, batch_id = path_from_payload(payload)
            # A resent batch the robot already has, its advertisement not yet heard
            if batch_id != 0 and batch_id == self.batch_id:
                return
            self.batch_id = batch_id
            self.logger.info(
                "Waypoints received",
                batch_id=batch_id,
                threshold=path.threshold_mm,
                count=path.count,
            )
            if path.count == 0:
                self._note_abort(WaypointsAbortReason.STOP)
                self._drive_stop()
                return
            if self.drive_mode != DriveMode.WAYPOINT:
                self._enter_drive_mode(DriveMode.WAYPOINT)
            self._steering_brake = False
            self.steering.set_path(path)
        elif payload_type == PayloadType.CMD_MAX_SPEED:
            v = payload.max_speed_mm_s
            if v != 0:
                v = max(MAX_SPEED_MIN_MM_S, min(MAX_SPEED_MAX_MM_S, v))
            self.steering.set_max_speed(float(v))
        elif payload_type == PayloadType.CONTROL_MODE:
            self._note_abort(WaypointsAbortReason.CONTROL_MODE)
            self._drive_stop()
        elif payload_type == PayloadType.CMD_RGB_LED:
            pass
        else:
            self.logger.warning(
                "Unhandled payload type", payload_type=f"0x{int(payload_type):02X}"
            )

    def receive(self):
        """Apply the frames the gateway has queued for this robot, as the
        app's radio_callback() does: accept its own address or the broadcast
        one, drop anything else."""
        while not self.queue.empty():
            frame = self.queue.get_nowait()
            destination = addr_to_hex(int(frame.header.destination))
            if destination in (self.address, DOTBOT_ADDRESS_DEFAULT):
                self.handle_payload(frame.payload_type, frame.packet.payload)

    def step(self, phase: int = 0):
        """One tick: the frames received since the last step, the tick, and
        the advertisement when `phase` ticks past an advertising interval."""
        self.receive()
        previous = self.steering.state
        self.tick()
        if self.steering.state != previous:
            self.logger.debug(
                "Steering state",
                state=self.steering.state.name,
                index=self.steering.index,
            )
        if (self.ticks + phase) % ADVERTISEMENT_TICKS == 0:
            self.tx_queue.put_nowait(self._advertisement_frame())


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


def placement_area(site: Optional[Site] = None) -> Area:
    """The rectangle a world file's unpositioned robots are spread over.

    The site's `arena` area, else its first declared area, else its whole
    extent, else a 2 x 2 m square at the frame origin for a site that
    measures neither.
    """
    if site is not None:
        area = site.areas.get(PLACEMENT_AREA_DEFAULT)
        if area is not None:
            return area
        for first in site.areas.values():
            return first
        if site.extent is not None:
            return site.extent
    side = PLACEMENT_EXTENT_DEFAULT_MM
    return Area(0, 0, side, side)


def grid_positions(area: Area, count: int) -> List[Tuple[int, int]]:
    """`count` points on the cell centres of a grid covering `area`, row-major.

    Deterministic, so the same world file and site always produce the same
    fleet layout.
    """
    if count <= 0:
        return []
    cols = ceil(sqrt(count))
    rows = ceil(count / cols)
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

    @property
    def controller_mode(self) -> ControlModeType:
        return ControlModeType(int(self.report["control_mode"]))


def _command(payload) -> bytes:
    return bytes(Packet.from_payload(payload).to_bytes())


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
        simulator_init_state: str,
        site: Optional[Site] = None,
    ):
        self.on_frame_received = on_frame_received
        self.ticks = 0
        self.time_elapsed_s = 0.0
        self._stop_event = threading.Event()
        self.main_thread = threading.Thread(target=self.run, daemon=True)
        self.logger = LOGGER.bind(context=__name__)
        init_state = InitStateToml(
            **toml.load(resolve_init_state_path(simulator_init_state))
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
        outputs = self._tick(self.visible)
        self.ticks += 1
        self.time_elapsed_s += SIMULATOR_STEP_DELTA_T
        self._models_update()
        if self._mari is not None:
            self._mari.now = self.ticks * SIMULATOR_STEP_DELTA_T
        for index in np.flatnonzero(outputs["advertise"]):
            self._advertise(int(index))
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
        robots switched on one by one have, and let each robot the world file
        gives a heading acquire it."""
        count = self.plant.count
        self._inputs["elapsed_ticks"] = 1 + np.arange(count) % ADVERTISEMENT_TICKS
        self._tick(np.zeros(count, dtype=bool))
        self._inputs["elapsed_ticks"] = 1
        if headed.any():
            self._acquire_headings(np.flatnonzero(headed))
        for index in range(count):
            self.core.advertisement(index, 0)
        self._counts[:] = 0

    def _acquire_headings(self, robots: np.ndarray):
        """Drive `robots` straight out until their estimators track, then back
        to where they started. Only they get fixes meanwhile."""
        fixes = np.zeros(self.plant.count, dtype=bool)
        fixes[robots] = True
        out = _command(
            PayloadCommandWheelVelocity(
                left_mm_s=PREROLL_SPEED_MM_S, right_mm_s=PREROLL_SPEED_MM_S
            )
        )
        back = _command(
            PayloadCommandWheelVelocity(
                left_mm_s=-PREROLL_SPEED_MM_S, right_mm_s=-PREROLL_SPEED_MM_S
            )
        )
        stop = _command(PayloadControlMode())
        plant = self.plant
        start_x, start_y = plant.x[robots].copy(), plant.y[robots].copy()
        fx, fy = kinematics.forward(plant.heading_deg[robots])

        def tracking():
            status = self.reports()["estimator_status"][robots]
            return status == control.PoseStatus.TRACKING

        for tick in range(PREROLL_MAX_TICKS):
            if tracking().all():
                break
            if tick % COMMAND_REPEAT_TICKS == 0:
                for index in robots:
                    self.core.rx(int(index), out)
            self._tick(fixes)
        # Each one brakes once its braking run-on would end it at its start
        moving = np.ones(len(robots), dtype=bool)
        for tick in range(2 * PREROLL_MAX_TICKS):
            if not moving.any():
                break
            if tick % COMMAND_REPEAT_TICKS == 0:
                for index in robots[moving]:
                    self.core.rx(int(index), back)
            self._tick(fixes)
            speed = plant.speed[:, robots].mean(axis=0)
            ahead = (plant.x[robots] - start_x) * fx + (plant.y[robots] - start_y) * fy
            arrived = moving & (ahead + speed * WHEEL_TAU_S <= 0)
            for index in robots[arrived]:
                self.core.rx(int(index), stop)
            moving &= ~arrived
        for _ in range(PREROLL_SETTLE_TICKS):
            self._tick(fixes)
        missed = robots[~tracking()]
        if missed.size:
            self.logger.warning(
                "Simulated robots started without a heading",
                addresses=[self.addresses[i] for i in missed],
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

    def _advertise(self, index: int):
        """Send robot `index`'s advertisement, as its firmware encodes it."""
        packet = self.core.advertisement(index, int(self.battery[index]))
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
