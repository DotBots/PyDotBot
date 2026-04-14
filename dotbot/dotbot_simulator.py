# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot simulator for the DotBot project."""

import ctypes
import queue
import random
import threading
from binascii import hexlify
from dataclasses import dataclass
from math import atan2, cos, pi, sin, sqrt
from pathlib import Path
from typing import Callable, List

import toml
from dotbot_utils.protocol import Frame, Header, Packet
from pydantic import BaseModel

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.logger import LOGGER
from dotbot.protocol import ControlModeType, PayloadDotBotAdvertisement, PayloadType

Kv = 400  # motor speed constant in RPM
R = 50  # motor reduction ratio
D = 50  # wheel diameter in mm
L = 70  # distance between the two wheels in mm
MIN_PWM_TO_MOVE = 40  # minimum PWM value to overcome static friction and start moving

# Encoder model: counts per mm of wheel travel (must match C-side DB_MM_PER_COUNT)
# mm_per_count = pi * D / (CPR * R)
ENCODER_CPR = 12  # counts per motor shaft revolution
MM_PER_COUNT = (pi * D) / (ENCODER_CPR * R)  # ~0.2618 mm/count

# Control parameters for the automatic mode
MOTOR_SPEED = 60
ANGULAR_SPEED_GAIN = 2
REDUCE_SPEED_FACTOR = 0.8
REDUCE_SPEED_ANGLE = 25
DIRECTION_THRESHOLD = 50  # threshold to update the direction (50mm)

SIMULATOR_STEP_DELTA_T = 0.02  # 20 ms

# Battery model parameters
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION = 60 * 60 * 3  # 3 hours in seconds

ADVERTISEMENT_INTERVAL_S = 0.5
SIMULATOR_UPDATE_INTERVAL_S = 0.1

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
    """Simple battery discharge model."""
    t = min(time_elapsed_s / MAX_BATTERY_DURATION, 1.0)
    nonlinear_t = t**1.3
    voltage = int(INITIAL_BATTERY_VOLTAGE * (1 - nonlinear_t))
    if voltage < 0:
        voltage = 0
    return voltage


def wheel_speed_from_pwm(pwm: float) -> float:
    """Convert a PWM value to a wheel speed in mm/s."""
    if abs(pwm) < MIN_PWM_TO_MOVE:
        return 0.0
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


class SimulatedDotBotSettings(BaseModel):
    address: str
    pos_x: int
    pos_y: int
    direction: int = -1000
    calibrated: int = 0xFF
    motor_left_error: float = 0
    motor_right_error: float = 0
    custom_control_loop_library: Path = None
    gru_model_path: Path = None
    battery_model_path: Path = None


class RobotControl(ctypes.Structure):
    _fields_ = [
        # Inputs — robot state (all 4-byte fields first, no padding gaps)
        ("pos_x", ctypes.c_uint32),
        ("pos_y", ctypes.c_uint32),
        (
            "encoder_left",
            ctypes.c_int32,
        ),  # signed delta counts since last call; 0 if unavailable
        (
            "encoder_right",
            ctypes.c_int32,
        ),  # signed delta counts since last call; 0 if unavailable
        # Inputs — current waypoint (4-byte fields)
        ("waypoint_x", ctypes.c_uint32),
        ("waypoint_y", ctypes.c_uint32),
        ("waypoint_threshold", ctypes.c_uint32),
        # 2-byte + two 1-byte fields pack cleanly into 4 bytes
        ("direction", ctypes.c_int16),
        ("waypoints_length", ctypes.c_uint8),
        ("waypoint_idx", ctypes.c_uint8),
        # Outputs — actuation + status flags (all 1-byte)
        ("pwm_left", ctypes.c_int8),
        ("pwm_right", ctypes.c_int8),
        ("waypoint_reached", ctypes.c_uint8),  # set to 1 by C when waypoint reached
        ("all_done", ctypes.c_uint8),  # set to 1 by C when batch complete
    ]


class SimulatedNetworkSettings(BaseModel):
    pdr: int = 100


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

        self.calibrated = settings.calibrated
        self.waypoint_threshold = 0
        self.waypoints = []
        self.waypoint_index = 0
        self.waypoint_x = 0
        self.waypoint_y = 0

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
        self.logger = LOGGER.bind(context=__name__, address=self.address)
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

    def _gru_residual(self) -> tuple[float, float]:
        """Return (dx_residual, dy_residual) predicted by the GRU, or (0, 0)."""
        if self._gru_model is None or len(self._gru_buffer) < GRU_SEQ_LEN_DEFAULT:
            return 0.0, 0.0
        try:
            import torch

            seq = self._gru_buffer[-GRU_SEQ_LEN_DEFAULT:]
            x = torch.tensor([seq], dtype=torch.float32)  # (1, seq_len, n_features)
            with torch.no_grad():
                pred = self._gru_model(x)  # (1, 2)
            return float(pred[0, 0]), float(pred[0, 1])
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("GRU inference failed", error=str(exc))
            return 0.0, 0.0

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

        # Accumulate encoder counts for this physics step
        self.encoder_left_acc += v_left_real * SIMULATOR_STEP_DELTA_T / MM_PER_COUNT
        self.encoder_right_acc += v_right_real * SIMULATOR_STEP_DELTA_T / MM_PER_COUNT

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
            res_x, res_y = self._gru_residual()
            self.pos_x += res_x
            self.pos_y += res_y

        if self._battery_model is not None:
            try:
                import torch

                features = torch.tensor(
                    [
                        [
                            float(self.pwm_left),
                            float(self.pwm_right),
                            float(self.encoder_left_acc),
                            float(self.encoder_right_acc),
                        ]
                    ],
                    dtype=torch.float32,
                )
                with torch.no_grad():
                    rate = float(self._battery_model(features)[0, 0])  # mV/s
                self.battery_voltage = max(0.0, self.battery_voltage + rate * dt)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Battery model inference failed", error=str(exc))

        self.logger.debug(
            "State updated",
            pos_x=int(self.pos_x),
            pos_y=int(self.pos_y),
            theta=int(self.theta),
            direction=int(self.direction),
            pwm_left=int(self.pwm_left),
            pwm_right=int(self.pwm_right),
        )
        self.time_elapsed_s += dt

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
            self.custom_control_loop_library = ctypes.CDLL(
                self.custom_control_loop_library
            )
            self.custom_control_loop_library.update_control.argtypes = [
                ctypes.POINTER(RobotControl)
            ]
            self.custom_control_loop_library.update_control.restype = None
            self.custom_robot_control = RobotControl()
            self.custom_robot_control.waypoint_idx = 0
            return self._control_loop_custom
        else:
            return self._control_loop_default

    def _control_loop_custom(self):
        """Control loop using a custom control loop library."""
        idx = self.custom_robot_control.waypoint_idx
        n = len(self.waypoints)

        # Safety guard: C should have set all_done on the previous call, but
        # protect against an inconsistent state before indexing the waypoints list.
        if idx >= n:
            self.logger.warning("waypoint_idx out of bounds, resetting", idx=idx, n=n)
            self.pwm_left = 0
            self.pwm_right = 0
            self.custom_robot_control.waypoint_idx = 0
            self.waypoint_index = 0
            self.waypoint_x = 0
            self.waypoint_y = 0
            self.controller_mode = ControlModeType.MANUAL
            return

        self.custom_robot_control.pos_x = int(self.pos_x)
        self.custom_robot_control.pos_y = int(self.pos_y)
        self.custom_robot_control.encoder_left = int(self.encoder_left_acc)
        self.custom_robot_control.encoder_right = int(self.encoder_right_acc)
        self.encoder_left_acc -= int(self.encoder_left_acc)
        self.encoder_right_acc -= int(self.encoder_right_acc)
        self.custom_robot_control.direction = self.direction
        self.custom_robot_control.waypoints_length = n
        self.custom_robot_control.waypoint_x = int(self.waypoints[idx].pos_x)
        self.custom_robot_control.waypoint_y = int(self.waypoints[idx].pos_y)
        self.custom_robot_control.waypoint_threshold = int(self.waypoint_threshold)

        self.custom_control_loop_library.update_control(
            ctypes.byref(self.custom_robot_control)
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
            waypoints_length=self.custom_robot_control.waypoints_length,
            waypoint_x=self.custom_robot_control.waypoint_x,
            waypoint_y=self.custom_robot_control.waypoint_y,
            waypoint_reached=self.custom_robot_control.waypoint_reached,
            all_done=self.custom_robot_control.all_done,
        )

        if self.custom_robot_control.all_done:
            self.logger.info("All waypoints completed")
            self.custom_robot_control.waypoint_idx = 0
            self.waypoint_index = 0
            self.waypoint_x = 0
            self.waypoint_y = 0
            self.controller_mode = ControlModeType.MANUAL

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
                        battery=(
                            int(self.battery_voltage)
                            if self._battery_model is not None
                            else battery_discharge_model(self.time_elapsed_s)
                        ),
                        pwm_left=int(self.pwm_left),
                        pwm_right=int(self.pwm_right),
                        mode=int(self.controller_mode),
                        encoder_left=int(self.encoder_left_acc),
                        encoder_right=int(self.encoder_right_acc),
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
                        if hasattr(self, "custom_robot_control"):
                            self.custom_robot_control.waypoint_idx = 0
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


class DotBotSimulatorCommunicationInterface:
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, on_frame_received: Callable, simulator_init_state_path: str):
        self.queue = queue.Queue()
        self.on_frame_received = on_frame_received
        self._stp_event = threading.Event()
        self.main_thread = threading.Thread(target=self.run, daemon=True)
        init_state = InitStateToml(**toml.load(simulator_init_state_path))
        self.network_pdr = init_state.network.pdr
        self.dotbots = [
            DotBotSimulator(
                settings=dotbot_settings,
                tx_queue=self.queue,
            )
            for dotbot_settings in init_state.dotbots
        ]

        self.logger = LOGGER.bind(context=__name__)

    def start(self):
        for dotbot in self.dotbots:
            dotbot.start()
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
        self.main_thread.join()

    def flush(self):
        """Flush fake serial output."""
        pass

    def _packet_delivered(self):
        return random.randint(0, 100) <= self.network_pdr

    def handle_dotbot_frame(self, frame):
        """Send bytes to the fake serial, similar to the real gateway."""
        if self._packet_delivered() is False:
            self.logger.info(
                f"Packet from DotBot {hexlify(int(frame.header.source).to_bytes(8, 'big')).decode()} lost in simulation"
            )
            return
        self.on_frame_received(frame)

    def write(self, bytes_):
        """Write bytes on the fake serial."""
        for dotbot in self.dotbots:
            if self._packet_delivered() is False:
                self.logger.info(
                    f"Packet to DotBot {dotbot.address} lost in simulation"
                )
                continue
            dotbot.queue.put_nowait(Frame.from_bytes(bytes_))
