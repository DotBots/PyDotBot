# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot simulator for the DotBot project."""

import ctypes
import heapq
import queue
import random
import threading
import time
from binascii import hexlify
from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, pi, sin, sqrt
from pathlib import Path
from typing import Callable, List, Optional

import toml
from dotbot_utils.protocol import Frame, Header, Packet
from pydantic import BaseModel, Field, model_validator

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.logger import LOGGER
from dotbot.protocol import ControlModeType, PayloadDotBotAdvertisement, PayloadType

Kv = 400  # motor speed constant in RPM
R = 50  # motor reduction ratio
D = 44  # wheel diameter in mm
L = 78  # distance between the two wheels in mm

# Encoder model: counts per mm of wheel travel (must match C-side DB_MM_PER_COUNT)
# mm_per_count = pi * D / (CPR * R)
ENCODER_CPR = 12  # counts per motor shaft revolution
MM_PER_COUNT = (pi * D) / (ENCODER_CPR * R)  # ~0.2618 mm/count

# Control parameters for the automatic mode
MOTOR_SPEED = 60
ANGULAR_SPEED_GAIN = 1.5
REDUCE_SPEED_FACTOR = 0.8
REDUCE_SPEED_ANGLE = 25

SIMULATOR_STEP_DELTA_T = 0.05  # 50 ms

# Battery model parameters
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION = 60 * 60 * 3  # 3 hours in seconds

ADVERTISEMENT_INTERVAL_S = 0.5
SIMULATOR_UPDATE_INTERVAL_S = 0.1

MARI_SLOTFRAME_SIZE = (
    102  # fixed schedule size; slotframe ≈ 126 ms → avg latency ≈ 63 ms
)

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


@dataclass
class Waypoint:
    """Waypoint class for the dotbot simulator."""

    x: int
    y: int


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
    return f"{random.getrandbits(64):016x}"


class SimulatedDotBotSettings(BaseModel):
    address: str = Field(default_factory=_random_address)
    pos_x: int
    pos_y: int
    direction: int = -1000
    calibrated: int = 0xFF
    motor_left_error: float = 0
    motor_right_error: float = 0
    custom_control_loop_library: Path = None
    gru_model_path: Path = None
    battery_model_path: Path = None
    network_mode: SimulatedNetworkMode = SimulatedNetworkMode.DEFAULT


class ControlLoopWaypoint(ctypes.Structure):
    """Mirrors coordinate_t from control_loop.h — used when calling control_loop_set_waypoints."""

    _fields_ = [
        ("x", ctypes.c_uint32),
        ("y", ctypes.c_uint32),
    ]


class RobotControl(ctypes.Structure):
    """Mirrors robot_control_t from control_loop.h.

    Only the stable external I/O boundary is represented here.  All internal
    algorithm state lives in the opaque context managed by the C library.
    Layout must stay in sync with the C struct (no internal padding gaps).
    """

    _fields_ = [
        # Inputs — robot state (4-byte fields first, no padding gaps)
        ("pos_x", ctypes.c_uint32),
        ("pos_y", ctypes.c_uint32),
        ("encoder_left", ctypes.c_int32),  # signed delta counts since last call
        ("encoder_right", ctypes.c_int32),  # signed delta counts since last call
        # Outputs — current target waypoint coordinates (written by C, for telemetry)
        ("waypoint_x", ctypes.c_uint32),
        ("waypoint_y", ctypes.c_uint32),
        # Input — robot heading (2-byte, followed by 1-byte fields — no internal padding)
        ("direction", ctypes.c_int16),
        # Outputs — actuation (written by C)
        ("pwm_left", ctypes.c_int8),
        ("pwm_right", ctypes.c_int8),
        # Outputs — status flags (written by C)
        ("waypoint_reached", ctypes.c_uint8),
        ("all_done", ctypes.c_uint8),
        ("waypoint_idx", ctypes.c_uint8),
    ]


class InitStateToml(BaseModel):
    dotbots: List[SimulatedDotBotSettings]
    network: SimulatedNetworkSettings = SimulatedNetworkSettings()


class DotBotSimulator:
    """Simulator class for the dotbot."""

    def __init__(self, settings: SimulatedDotBotSettings, tx_queue: queue.Queue):
        self.address = settings.address.lower()
        self.pos_x = settings.pos_x
        self.pos_y = settings.pos_y
        self.theta = settings.direction * -1 if settings.direction != -1000 else 0
        self.motor_left_error = settings.motor_left_error
        self.motor_right_error = settings.motor_right_error
        self.custom_control_loop_library = settings.custom_control_loop_library
        self._control_loop_func = self._init_control_loop()
        self.time_elapsed_s = 0

        self.pwm_left = 0
        self.pwm_right = 0
        self.direction = settings.direction

        # Accumulated encoder deltas between control-loop calls (control runs at
        # SIMULATOR_UPDATE_INTERVAL_S, physics at SIMULATOR_STEP_DELTA_T — multiple
        # physics steps per control call)
        self.encoder_left_acc = 0.0
        self.encoder_right_acc = 0.0
        # Last encoder delta actually passed to update_control — advertised to match
        # real-robot telemetry semantics (the value from the most recent control call)
        self._last_encoder_left = 0
        self._last_encoder_right = 0

        self.calibrated = settings.calibrated
        self.waypoint_threshold = 0
        self.waypoints = []
        self.waypoint_index = 0
        self.waypoint_x = 0
        self.waypoint_y = 0

        self.logger = LOGGER.bind(context=__name__, address=self.address)
        self._gru_model = None
        self._gru_buffer: list[list[float]] = (
            []
        )  # rolling window of raw feature vectors
        if settings.gru_model_path is not None:
            self._gru_model = self._load_gru_model(settings.gru_model_path)

        self._battery_model = None
        self.battery_voltage: float = float(INITIAL_BATTERY_VOLTAGE)
        if settings.battery_model_path is not None:
            self._battery_model = self._load_battery_model(settings.battery_model_path)

        self._lock = threading.Lock()
        self.tx_queue = tx_queue
        self.queue = queue.Queue()
        self.advertise_thread = threading.Thread(target=self.advertise, daemon=True)
        self.control_thread = threading.Thread(target=self.control_thread, daemon=True)
        self.rx_thread = threading.Thread(target=self.rx_frame, daemon=True)
        self.main_thread = threading.Thread(target=self.update_state, daemon=True)
        self.controller_mode: ControlModeType = ControlModeType.MANUAL
        self._stop_event = threading.Event()
        self.logger.info(
            "DotBot simulator initialized",
            pos_x=self.pos_x,
            pos_y=self.pos_y,
            direction=self.direction,
            theta=self.theta,
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

    def start(self):
        self.rx_thread.start()
        self.advertise_thread.start()
        self.control_thread.start()
        self.main_thread.start()
        self.logger.info("DotBot simulator started")

    @property
    def header(self):
        return Header(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
        )

    def diff_drive_model_update(self, dt=SIMULATOR_STEP_DELTA_T):
        """State space model update."""
        pos_x_old = self.pos_x
        pos_y_old = self.pos_y
        theta_old = self.theta

        # Compute each wheel's real speed considering the motor error and the minimum PWM to move
        v_left_real = wheel_speed_from_pwm(self.pwm_left) * (1 - self.motor_left_error)
        v_right_real = wheel_speed_from_pwm(self.pwm_right) * (
            1 - self.motor_right_error
        )

        V = (v_right_real + v_left_real) / 2
        w = (v_right_real - v_left_real) / L
        x_dot = V * cos(theta_old * pi / 180 - pi / 2)
        y_dot = V * sin(theta_old * pi / 180 + pi / 2)
        dx = x_dot * dt
        dy = y_dot * dt

        self.pos_x = pos_x_old + dx
        self.pos_y = pos_y_old + dy
        self.theta = (theta_old + w * dt * 180 / pi) % 360

        if sqrt(dx**2 + dy**2):
            self.direction = int(-1 * atan2(dx, dy) * 180 / pi) % 360
            if self.direction > 180:
                self.direction -= 360
            elif self.direction < -180:
                self.direction += 360

        # Accumulate encoder counts for this physics step
        if self.controller_mode == ControlModeType.AUTO:
            self.encoder_left_acc += v_left_real * SIMULATOR_STEP_DELTA_T / MM_PER_COUNT
            self.encoder_right_acc += (
                v_right_real * SIMULATOR_STEP_DELTA_T / MM_PER_COUNT
            )

        # Update GRU feature buffer with the post-step state
        if self._gru_model is not None:
            self._gru_buffer.append(
                [
                    float(self.pwm_left),
                    float(self.pwm_right),
                    float(self.encoder_left_acc),
                    float(self.encoder_right_acc),
                    float(self.direction),
                    float(self.pos_x),
                    float(self.pos_y),
                ]
            )
            # Keep only as many steps as needed to avoid unbounded growth
            if len(self._gru_buffer) > GRU_SEQ_LEN_DEFAULT:
                self._gru_buffer.pop(0)
            res_x, res_y, res_enc_l, res_enc_r = self._gru_residual()
            self.pos_x += res_x
            self.pos_y += res_y
            if self.controller_mode == ControlModeType.AUTO:
                self.encoder_left_acc += res_enc_l
                self.encoder_right_acc += res_enc_r

        self.time_elapsed_s += dt
        if self._battery_model is not None:
            try:
                import torch

                # Encoders are only reported by the real hardware in AUTO mode;
                # mirror that here so the battery model sees consistent inputs.
                in_auto = self.controller_mode == ControlModeType.AUTO
                enc_left = float(self.encoder_left_acc) if in_auto else 0.0
                enc_right = float(self.encoder_right_acc) if in_auto else 0.0
                features = torch.tensor(
                    [
                        [
                            float(self.pwm_left),
                            float(self.pwm_right),
                            enc_left,
                            enc_right,
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

        self.logger.debug(
            "State updated",
            pos_x=int(self.pos_x),
            pos_y=int(self.pos_y),
            theta=int(self.theta),
            direction=int(self.direction),
            pwm_left=int(self.pwm_left),
            pwm_right=int(self.pwm_right),
        )

    def update_state(self):
        """Update the state of the dotbot simulator."""
        while True:
            with self._lock:
                self.diff_drive_model_update()
            is_stopped = self._stop_event.wait(SIMULATOR_STEP_DELTA_T)
            if is_stopped:
                break

    def _init_control_loop(self) -> callable:
        """Initialize the control loop, potentially loading a custom control loop library."""
        if self.custom_control_loop_library is not None:
            lib = ctypes.CDLL(self.custom_control_loop_library)
            self.custom_control_loop_library = lib

            lib.control_loop_alloc.argtypes = []
            lib.control_loop_alloc.restype = ctypes.c_void_p

            lib.control_loop_free.argtypes = [ctypes.c_void_p]
            lib.control_loop_free.restype = None

            lib.control_loop_set_waypoints.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ControlLoopWaypoint),
                ctypes.c_uint8,
                ctypes.c_uint32,
            ]
            lib.control_loop_set_waypoints.restype = None

            lib.update_control.argtypes = [
                ctypes.POINTER(RobotControl),
                ctypes.c_void_p,
            ]
            lib.update_control.restype = None

            self._control_ctx = lib.control_loop_alloc()
            self.custom_robot_control = RobotControl()
            return self._control_loop_custom
        else:
            return self._control_loop_default

    def _control_loop_custom(self):
        """Control loop using a custom control loop library."""
        self.custom_robot_control.pos_x = int(self.pos_x)
        self.custom_robot_control.pos_y = int(self.pos_y)
        self.custom_robot_control.direction = self.direction
        self._last_encoder_left = int(self.encoder_left_acc)
        self._last_encoder_right = int(self.encoder_right_acc)
        self.custom_robot_control.encoder_left = self._last_encoder_left
        self.custom_robot_control.encoder_right = self._last_encoder_right
        self.encoder_left_acc = 0
        self.encoder_right_acc = 0

        self.custom_control_loop_library.update_control(
            ctypes.byref(self.custom_robot_control),
            self._control_ctx,
        )

        self.pwm_left = self.custom_robot_control.pwm_left
        self.pwm_right = self.custom_robot_control.pwm_right
        self.waypoint_index = self.custom_robot_control.waypoint_idx
        self.waypoint_x = self.custom_robot_control.waypoint_x
        self.waypoint_y = self.custom_robot_control.waypoint_y

        self.logger.info(
            "Custom loop",
            pwm_left=self.pwm_left,
            pwm_right=self.pwm_right,
            direction=self.direction,
            encoder_left=int(self.custom_robot_control.encoder_left),
            encoder_right=int(self.custom_robot_control.encoder_right),
            waypoint_index=self.custom_robot_control.waypoint_idx,
            waypoint_x=self.custom_robot_control.waypoint_x,
            waypoint_y=self.custom_robot_control.waypoint_y,
            waypoint_reached=self.custom_robot_control.waypoint_reached,
            all_done=self.custom_robot_control.all_done,
        )

        if self.custom_robot_control.all_done:
            self.logger.info("All waypoints completed")
            self.waypoint_index = 0
            self.waypoint_x = 0
            self.waypoint_y = 0
            self.controller_mode = ControlModeType.MANUAL
            self.encoder_right_acc = 0
            self.encoder_left_acc = 0

    def _control_loop_default(self):
        delta_x = self.waypoints[self.waypoint_index].pos_x - self.pos_x
        delta_y = self.waypoints[self.waypoint_index].pos_y - self.pos_y
        distance_to_target = sqrt(delta_x**2 + delta_y**2)

        # check if we are close enough to the "next" waypoint
        if distance_to_target < self.waypoint_threshold:
            self.logger.info("Waypoint reached", waypoint_index=self.waypoint_index)
            self.waypoint_index += 1
            # check if there are no more waypoints:
            if self.waypoint_index >= len(self.waypoints):
                self.logger.info(
                    "Last waypoint reached", waypoint_index=self.waypoint_index
                )
                self.pwm_left = 0
                self.pwm_right = 0
                self.waypoint_index = 0
                self.waypoint_x = 0
                self.waypoint_y = 0
                self.controller_mode = ControlModeType.MANUAL
                self.encoder_right_acc = 0
                self.encoder_left_acc = 0
                return

        self.waypoint_x = int(self.waypoints[self.waypoint_index].pos_x)
        self.waypoint_y = int(self.waypoints[self.waypoint_index].pos_y)

        angle_to_target = -1 * atan2(delta_x, delta_y) * 180 / pi
        robot_angle = self.direction
        if robot_angle >= 180:
            robot_angle -= 360
        elif robot_angle < -180:
            robot_angle += 360

        error_angle = angle_to_target - robot_angle
        if error_angle >= 180:
            error_angle -= 360
        elif error_angle < -180:
            error_angle += 360

        speed_reduction_factor: float = 1.0
        if distance_to_target < self.waypoint_threshold * 2:
            speed_reduction_factor = REDUCE_SPEED_FACTOR
        if error_angle > REDUCE_SPEED_ANGLE or error_angle < -REDUCE_SPEED_ANGLE:
            speed_reduction_factor = REDUCE_SPEED_FACTOR

        angular_speed = (error_angle / 180) * MOTOR_SPEED * ANGULAR_SPEED_GAIN
        self.pwm_left = MOTOR_SPEED * speed_reduction_factor + angular_speed
        self.pwm_right = MOTOR_SPEED * speed_reduction_factor - angular_speed

        self.logger.info(
            "Loop update",
            robot_angle=int(robot_angle),
            angle_to_target=int(angle_to_target),
            error_angle=int(error_angle),
            angular_speed=int(angular_speed),
            pwm_left=int(self.pwm_left),
            pwm_right=int(self.pwm_right),
            theta=int(self.theta),
            waypoint=f"{self.waypoint_index}/{len(self.waypoints)}",
        )

    def control_thread(self):
        """Control thread to update the state of the dotbot simulator."""
        while self._stop_event.is_set() is False:
            if self.controller_mode == ControlModeType.AUTO:
                with self._lock:
                    self._control_loop_func()
            is_stopped = self._stop_event.wait(SIMULATOR_UPDATE_INTERVAL_S)
            if is_stopped:
                break

    def advertise(self):
        """Send an advertisement message to the gateway."""
        while self._stop_event.is_set() is False:
            payload = Frame(
                header=self.header,
                packet=Packet.from_payload(
                    PayloadDotBotAdvertisement(
                        calibrated=self.calibrated,
                        direction=self.direction,
                        pos_x=int(self.pos_x) if self.pos_x >= 0 else 0,
                        pos_y=int(self.pos_y) if self.pos_y >= 0 else 0,
                        battery=int(self.battery_voltage),
                        pwm_left=int(self.pwm_left),
                        pwm_right=int(self.pwm_right),
                        mode=int(self.controller_mode),
                        encoder_left=self._last_encoder_left,
                        encoder_right=self._last_encoder_right,
                        waypoint_x=int(self.waypoint_x),
                        waypoint_y=int(self.waypoint_y),
                        waypoint_idx=int(self.waypoint_index),
                    )
                ),
            )
            self.tx_queue.put_nowait(payload)
            is_stopped = self._stop_event.wait(ADVERTISEMENT_INTERVAL_S)
            if is_stopped:
                break

    def rx_frame(self):
        """Decode the serial input received from the gateway."""

        while self._stop_event.is_set() is False:
            frame = self.queue.get()
            if frame is None:
                break
            with self._lock:
                if self.address == hex(frame.header.destination)[2:]:
                    if frame.payload_type == PayloadType.CMD_MOVE_RAW:
                        self.controller_mode = ControlModeType.MANUAL
                        self.waypoint_index = 0
                        self.waypoint_x = 0
                        self.waypoint_y = 0
                        self.pwm_left = frame.packet.payload.left_y
                        self.pwm_right = frame.packet.payload.right_y
                        if self.pwm_left > 127:
                            self.pwm_left = self.pwm_left - 256
                        if self.pwm_right > 127:
                            self.pwm_right = self.pwm_right - 256
                        self.logger.info(
                            "RAW command received",
                            pwm_left=self.pwm_left,
                            pwm_right=self.pwm_right,
                        )
                    elif frame.payload_type == PayloadType.LH2_WAYPOINTS:
                        self.waypoint_threshold = frame.packet.payload.threshold
                        self.waypoints = frame.packet.payload.waypoints
                        self.waypoint_index = 0
                        self.encoder_left_acc = 0.0
                        self.encoder_right_acc = 0.0
                        if hasattr(self, "_control_ctx"):
                            n = len(self.waypoints)
                            WaypointArray = ControlLoopWaypoint * n
                            waypoint_arr = WaypointArray(
                                *[
                                    ControlLoopWaypoint(x=int(w.pos_x), y=int(w.pos_y))
                                    for w in self.waypoints
                                ]
                            )
                            self.custom_control_loop_library.control_loop_set_waypoints(
                                self._control_ctx,
                                waypoint_arr,
                                n,
                                int(self.waypoint_threshold),
                            )
                        self.logger.info(
                            "Waypoints received",
                            threshold=self.waypoint_threshold,
                            waypoints=self.waypoints,
                        )
                        if self.waypoints:
                            self.controller_mode = ControlModeType.AUTO
                        else:
                            self.pwm_left = 0
                            self.pwm_right = 0
                            self.controller_mode = ControlModeType.MANUAL

    def stop(self):
        self.logger.info(f"Stopping DotBot {self.address} simulator...")
        self._stop_event.set()
        self.queue.put_nowait(None)  # unblock the rx_thread if waiting on the queue
        self.advertise_thread.join()
        self.control_thread.join()
        self.rx_thread.join()
        self.main_thread.join()
        if hasattr(self, "_control_ctx"):
            self.custom_control_loop_library.control_loop_free(self._control_ctx)
            self._control_ctx = None


class MariNetworkSimulator:
    """TSCH slot-based network simulator modelling the Mari link layer."""

    def __init__(self, settings: SimulatedNetworkSettings, on_frame_received: Callable):
        self._settings = settings
        self._on_frame_received = on_frame_received
        self._heap: list = []
        self._seq = 0
        self._cond = threading.Condition()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join()

    def _slot_delay_s(self, dotbot_index: int, slot_shift: int = 0) -> float:
        slotframe_duration_s = (
            MARI_SLOTFRAME_SIZE * self._settings.slot_duration_ms / 1000
        )
        slot_pos = (dotbot_index + slot_shift) % MARI_SLOTFRAME_SIZE
        slot_offset_s = slot_pos * self._settings.slot_duration_ms / 1000
        phase = time.monotonic() % slotframe_duration_s
        return (slot_offset_s - phase) % slotframe_duration_s

    def _enqueue(self, delay_s: float, fn: Callable):
        delivery = time.monotonic() + delay_s
        with self._cond:
            heapq.heappush(self._heap, (delivery, self._seq, fn))
            self._seq += 1
            self._cond.notify()

    def schedule_uplink(self, frame, dotbot_index: int):
        if random.randint(0, 100) > self._settings.uplink_pdr:
            return
        delay = self._slot_delay_s(dotbot_index) + self._settings.mqtt_latency_ms / 1000
        self._enqueue(delay, lambda: self._on_frame_received(frame))

    def schedule_downlink(
        self, bytes_: bytes, dotbot: "DotBotSimulator", dotbot_index: int
    ):
        if random.randint(0, 100) > self._settings.downlink_pdr:
            return
        frame = Frame.from_bytes(bytes_)
        # Downlink slots are in the second half of the frame — distinct from uplink slots
        delay = (
            self._slot_delay_s(dotbot_index, slot_shift=MARI_SLOTFRAME_SIZE // 2)
            + self._settings.mqtt_latency_ms / 1000
        )
        self._enqueue(delay, lambda: dotbot.queue.put_nowait(frame))

    def _run(self):
        with self._cond:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if self._heap:
                    deadline, _, fn = self._heap[0]
                    if deadline <= now:
                        heapq.heappop(self._heap)
                        self._cond.release()
                        try:
                            fn()
                        finally:
                            self._cond.acquire()
                        continue
                    wait = deadline - now
                else:
                    wait = None
                self._cond.wait(timeout=wait)


class DotBotSimulatorCommunicationInterface:
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, on_frame_received: Callable, simulator_init_state: str):
        self.queue = queue.Queue()
        self.on_frame_received = on_frame_received
        self._stp_event = threading.Event()
        self.main_thread = threading.Thread(target=self.run, daemon=True)
        init_state = InitStateToml(**toml.load(simulator_init_state))
        self._network = init_state.network
        self.dotbots = [
            DotBotSimulator(
                settings=dotbot_settings,
                tx_queue=self.queue,
            )
            for dotbot_settings in init_state.dotbots
        ]
        self._dotbot_modes = [s.network_mode for s in init_state.dotbots]
        self._address_to_index = {d.address: i for i, d in enumerate(self.dotbots)}
        self._mari = None
        if any(m == SimulatedNetworkMode.MARI for m in self._dotbot_modes):
            self._mari = MariNetworkSimulator(self._network, self.on_frame_received)

        self.logger = LOGGER.bind(context=__name__)

    def start(self):
        for dotbot in self.dotbots:
            dotbot.start()
        if self._mari is not None:
            self._mari.start()
        self.main_thread.start()
        self.logger.info("DotBot Simulation Started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        while self._stp_event.is_set() is False:
            frame = self.queue.get()
            if frame is None:
                break
            self.handle_dotbot_frame(frame)

    def stop(self):
        self.logger.info("Stopping DotBot Simulation...")
        self._stp_event.set()
        self.queue.put_nowait(None)  # unblock the run thread if waiting on the queue
        for dotbot in self.dotbots:
            dotbot.stop()
        if self._mari is not None:
            self._mari.stop()
        self.main_thread.join()

    def flush(self):
        """Flush fake serial output."""
        pass

    def _packet_delivered(self, pdr: int) -> bool:
        return random.randint(0, 100) <= pdr

    def handle_dotbot_frame(self, frame):
        """Send bytes to the fake serial, similar to the real gateway."""
        addr = hex(frame.header.source)[2:]
        index = self._address_to_index.get(addr, 0)
        if self._dotbot_modes[index] == SimulatedNetworkMode.MARI:
            self._mari.schedule_uplink(frame, index)
            return
        if not self._packet_delivered(self._network.pdr):
            self.logger.info(
                f"Packet from DotBot {hexlify(int(frame.header.source).to_bytes(8, 'big')).decode()} lost in simulation"
            )
            return
        self.on_frame_received(frame)

    def write(self, bytes_):
        """Write bytes on the fake serial."""
        for index, dotbot in enumerate(self.dotbots):
            if self._dotbot_modes[index] == SimulatedNetworkMode.MARI:
                self._mari.schedule_downlink(bytes_, dotbot, index)
                continue
            if not self._packet_delivered(self._network.pdr):
                self.logger.info(
                    f"Packet to DotBot {dotbot.address} lost in simulation"
                )
                continue
            dotbot.queue.put_nowait(Frame.from_bytes(bytes_))
