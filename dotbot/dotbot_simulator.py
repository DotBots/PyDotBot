# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot simulator for the DotBot project."""

import queue
import random
import threading
from binascii import hexlify
from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, pi, sin, sqrt
from typing import Callable, List

import toml
from dotbot_utils.protocol import Frame, Header, Packet
from pydantic import BaseModel

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.logger import LOGGER
from dotbot.protocol import PayloadDotBotAdvertisement, PayloadType

Kv = 400  # motor speed constant in RPM
r = 50  # motor reduction ratio
R = 25  # wheel radius in mm
L = 70  # distance between the two wheels in mm
MIN_PWM_TO_MOVE = 30  # minimum PWM value to overcome static friction and start moving

# Control parameters for the automatic mode
MOTOR_SPEED = 60
ANGULAR_SPEED_GAIN = 1.2
REDUCE_SPEED_FACTOR = 0.7
REDUCE_SPEED_ANGLE = 25

SIMULATOR_STEP_DELTA_T = 0.02  # 20 ms

# Battery model parameters
INITIAL_BATTERY_VOLTAGE = 3000  # mV
MAX_BATTERY_DURATION = 300  # 5 minutes

ADVERTISEMENT_INTERVAL_S = 0.5
SIMULATOR_UPDATE_INTERVAL_S = 0.1


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
    if pwm < MIN_PWM_TO_MOVE:
        return 0.0
    return pwm * R * Kv / (r * 127)


class DotBotSimulatorMode(Enum):
    """Operation mode of the dotbot simulator."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"


@dataclass
class Waypoint:
    """Waypoint class for the dotbot simulator."""

    x: int
    y: int


class SimulatedDotBotSettings(BaseModel):
    address: str
    pos_x: int
    pos_y: int
    theta: float
    calibrated: int = 0xFF
    motor_left_error: float = 0
    motor_right_error: float = 0


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
        self.theta = settings.theta
        self.motor_left_error = settings.motor_left_error
        self.motor_right_error = settings.motor_right_error
        self.time_elapsed_s = 0

        self.pwm_left = 0
        self.pwm_right = 0

        self.calibrated = settings.calibrated
        self.waypoint_threshold = 0
        self.waypoints = []
        self.waypoint_index = 0

        self._lock = threading.Lock()
        self.tx_queue = tx_queue
        self.queue = queue.Queue()
        self.advertise_thread = threading.Thread(target=self.advertise, daemon=True)
        self.control_thread = threading.Thread(target=self.control_thread, daemon=True)
        self.rx_thread = threading.Thread(target=self.rx_frame, daemon=True)
        self.main_thread = threading.Thread(target=self.update_state, daemon=True)
        self.controller_mode: DotBotSimulatorMode = DotBotSimulatorMode.MANUAL
        self.logger = LOGGER.bind(context=__name__, address=self.address)
        self._stop_event = threading.Event()
        self.rx_thread.start()
        self.advertise_thread.start()
        self.control_thread.start()
        self.main_thread.start()

    @property
    def header(self):
        return Header(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
        )

    def _diff_drive_model_update(self, dt: float):
        """State space model update."""
        pos_x_old = self.pos_x
        pos_y_old = self.pos_y
        theta_old = self.theta

        if self.pwm_left > 100:
            self.pwm_left = 100
        if self.pwm_right > 100:
            self.pwm_right = 100
        if self.pwm_left < 0:
            self.pwm_left = 0
        if self.pwm_right < 0:
            self.pwm_right = 0

        # Compute each wheel's real speed considering the motor error and the minimum PWM to move
        v_left_real = wheel_speed_from_pwm(self.pwm_left) * (1 - self.motor_left_error)
        v_right_real = wheel_speed_from_pwm(self.pwm_right) * (
            1 - self.motor_right_error
        )

        V = (v_left_real + v_right_real) / 2
        w = (v_left_real - v_right_real) / L
        x_dot = V * cos(theta_old - pi)
        y_dot = V * sin(theta_old - pi)

        self.pos_x = pos_x_old + x_dot * SIMULATOR_STEP_DELTA_T
        self.pos_y = pos_y_old + y_dot * SIMULATOR_STEP_DELTA_T
        self.theta = (theta_old + w * SIMULATOR_STEP_DELTA_T) % (2 * pi)

        self.logger.debug(
            "State updated",
            pos_x=self.pos_x,
            pos_y=self.pos_y,
            theta=self.theta,
            pwm_left=self.pwm_left,
            pwm_right=self.pwm_right,
            v_left_real=v_left_real,
            v_right_real=v_right_real,
        )
        self.time_elapsed_s += dt

    def update_state(self):
        """Update the state of the dotbot simulator."""
        while True:
            with self._lock:
                self._diff_drive_model_update(SIMULATOR_STEP_DELTA_T)
                is_stopped = self._stop_event.wait(SIMULATOR_STEP_DELTA_T)
                if is_stopped:
                    break

    def _compute_automatic_control(self):
        if self.controller_mode != DotBotSimulatorMode.AUTOMATIC:
            return

        delta_x = self.pos_x - self.waypoints[self.waypoint_index].pos_x
        delta_y = self.pos_y - self.waypoints[self.waypoint_index].pos_y
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
                self.controller_mode = DotBotSimulatorMode.MANUAL
        else:
            robot_angle = self.theta
            angle_to_target = atan2(delta_y, delta_x)
            if robot_angle >= pi:
                robot_angle = robot_angle - 2 * pi

            error_angle = ((angle_to_target - robot_angle + pi) % (2 * pi)) - pi
            self.logger.info(
                "Moving to waypoint",
                robot_angle=robot_angle,
                angle_to_target=angle_to_target,
                error_angle=error_angle,
            )

            speed_reduction_factor: float = 1.0
            if distance_to_target < self.waypoint_threshold * 2:
                speed_reduction_factor = REDUCE_SPEED_FACTOR

            if error_angle > REDUCE_SPEED_ANGLE or error_angle < -REDUCE_SPEED_ANGLE:
                speed_reduction_factor = REDUCE_SPEED_FACTOR

            angular_speed = error_angle * MOTOR_SPEED * ANGULAR_SPEED_GAIN
            self.pwm_left = MOTOR_SPEED * speed_reduction_factor + angular_speed
            self.pwm_right = MOTOR_SPEED * speed_reduction_factor - angular_speed

        self.logger.info(
            "Control loop update",
            v_left=self.pwm_left,
            v_right=self.pwm_right,
            theta=self.theta,
        )

    def control_thread(self):
        """Control thread to update the state of the dotbot simulator."""
        while self._stop_event.is_set() is False:
            with self._lock:
                self._compute_automatic_control()
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
                        direction=int(self.theta * 180 / pi + 90),
                        pos_x=int(self.pos_x) if self.pos_x >= 0 else 0,
                        pos_y=int(self.pos_y) if self.pos_y >= 0 else 0,
                        pos_z=0,
                        battery=battery_discharge_model(self.time_elapsed_s),
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
                        self.controller_mode = DotBotSimulatorMode.MANUAL
                        self.pwm_left = frame.packet.payload.left_y
                        self.pwm_right = frame.packet.payload.right_y
                        self.logger.info(
                            "RAW command received",
                            v_left=self.pwm_left,
                            v_right=self.pwm_right,
                        )

                        if self.pwm_left > 127:
                            self.pwm_left = self.pwm_left - 256
                        if self.pwm_right > 127:
                            self.pwm_right = self.pwm_right - 256

                    elif frame.payload_type == PayloadType.LH2_WAYPOINTS:
                        self.pwm_left = 0
                        self.pwm_right = 0
                        self.controller_mode = DotBotSimulatorMode.MANUAL
                        self.waypoint_threshold = frame.packet.payload.threshold
                        self.waypoints = frame.packet.payload.waypoints
                        self.logger.info(
                            "Waypoints received",
                            threshold=self.waypoint_threshold,
                            waypoints=self.waypoints,
                        )
                        if self.waypoints:
                            self.controller_mode = DotBotSimulatorMode.AUTOMATIC

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

        self.main_thread.start()
        self.logger = LOGGER.bind(context=__name__)
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
