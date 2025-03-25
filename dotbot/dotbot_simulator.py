# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Dotbot simulator for the DotBot project."""

import threading
import time
from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, pi, sin, sqrt
from typing import Callable

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    ApplicationType,
    Frame,
    Header,
    PayloadAdvertisement,
    PayloadDotBotSimulatorData,
    PayloadType,
)

R = 1
L = 2
SIMULATOR_STEP_DELTA_T = 0.005


def diff_drive_bot(x_pos_old, y_pos_old, theta_old, v_right, v_left):
    """Execute state space model of a rigid differential drive robot."""
    x_dot = R / 2 * (v_right + v_left) * cos(theta_old - pi) * 50000
    y_dot = R / 2 * (v_right + v_left) * sin(theta_old - pi) * 50000
    theta_dot = R / L * (-v_right + v_left)

    x_pos = x_pos_old + x_dot * SIMULATOR_STEP_DELTA_T
    y_pos = y_pos_old + y_dot * SIMULATOR_STEP_DELTA_T
    theta = (theta_old + theta_dot * SIMULATOR_STEP_DELTA_T) % (2 * pi)

    return x_pos, y_pos, theta


class DotBotSimulatorMode(Enum):
    """Operation mode of the dotbot simulator."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"


@dataclass
class Waypoint:
    """Waypoint class for the dotbot simulator."""

    x: int
    y: int


class DotBotSimulator:
    """Simulator class for the dotbot."""

    def __init__(self, address):
        self.address = address
        self.pos_x = 0.5 * 1e6
        self.pos_y = 0.5 * 1e6
        self.theta = 0

        self.v_left = 0
        self.v_right = 0

        self.waypoint_threshold = 0
        self.waypoints = []
        self.waypoint_index = 0

        self.controller_mode: DotBotSimulatorMode = DotBotSimulatorMode.MANUAL
        self.logger = LOGGER.bind(context=__name__, address=self.address)

    @property
    def header(self):
        return Header(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
        )

    def update(self):
        """State space model update."""
        pos_x_old = self.pos_x
        pos_y_old = self.pos_y
        theta_old = self.theta

        if self.controller_mode == DotBotSimulatorMode.MANUAL:
            self.pos_x, self.pos_y, self.theta = diff_drive_bot(
                pos_x_old, pos_y_old, theta_old, self.v_right, self.v_left
            )
        elif self.controller_mode == DotBotSimulatorMode.AUTOMATIC:
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
                    self.v_left = 0
                    self.v_right = 0
                    self.waypoint_index = 0
                    self.controller_mode = DotBotSimulatorMode.MANUAL
            else:
                robot_angle = self.theta
                angle_to_target = atan2(delta_y, delta_x)
                if robot_angle >= pi:
                    robot_angle = robot_angle - 2 * pi
                # if (angle_to_target < 0):
                #    angle_to_target = 2*pi + angle_to_target

                error_angle = ((angle_to_target - robot_angle + pi) % (2 * pi)) - pi
                self.logger.debug(
                    "Moving to waypoint",
                    robot_angle=robot_angle,
                    angle_to_target=angle_to_target,
                    error_angle=error_angle,
                )

                angular_speed = error_angle * 200
                self.v_left = 100 + angular_speed
                self.v_right = 100 - angular_speed

                if self.v_left > 100:
                    self.v_left = 100
                if self.v_right > 100:
                    self.v_right = 100
                if self.v_left < 0:
                    self.v_left = 0
                if self.v_right < 0:
                    self.v_right = 0

            self.pos_x, self.pos_y, self.theta = diff_drive_bot(
                self.pos_x, self.pos_y, self.theta, self.v_right, self.v_left
            )

        return self.encode_serial_output()

    def advertise(self):
        """Send an adertisement message to the gateway."""
        payload = Frame(
            self.header,
            PayloadAdvertisement(application=ApplicationType.DotBot),
        )
        return hdlc_encode(payload.to_bytes())

    def decode_serial_input(self, frame):
        """Decode the serial input received from the gateway."""
        bytes_ = hdlc_decode(frame)
        if bytes_[1] in [0xFF, 0xFE]:
            return
        frame = Frame().from_bytes(bytes_)

        if self.address == hex(frame.header.destination)[2:]:
            if frame.payload_type == PayloadType.CMD_MOVE_RAW:
                self.controller_mode = DotBotSimulatorMode.MANUAL
                self.v_left = frame.payload.left_y
                self.v_right = frame.payload.right_y

                if self.v_left > 127:
                    self.v_left = self.v_left - 256
                if self.v_right > 127:
                    self.v_right = self.v_right - 256

            elif frame.payload_type == PayloadType.LH2_WAYPOINTS:
                self.controller_mode = DotBotSimulatorMode.MANUAL
                self.waypoint_threshold = frame.payload.threshold * 1000
                self.waypoints = frame.payload.waypoints
                if self.waypoints:
                    self.controller_mode = DotBotSimulatorMode.AUTOMATIC

    def encode_serial_output(self):
        """Encode the dotbot data to be sent to the gateway."""
        frame = Frame(
            self.header,
            PayloadDotBotSimulatorData(
                theta=int(self.theta * 180 / pi + 90),
                pos_x=int(self.pos_x),
                pos_y=int(self.pos_y),
            ),
        )
        return hdlc_encode(frame.to_bytes())


class DotBotSimulatorSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, callback: Callable):
        self.dotbots = [
            DotBotSimulator("1234567890123456"),
            DotBotSimulator("4987654321098765"),
        ]

        self.callback = callback
        super().__init__(daemon=True)
        self.start()
        self.logger = LOGGER.bind(context=__name__)
        self.logger.info("DotBot Simulation Started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        advertising_intervals = [0] * len(self.dotbots)
        for dotbot in self.dotbots:
            for byte in dotbot.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
        time.sleep(0.5)

        while 1:
            for idx, dotbot in enumerate(self.dotbots):
                for byte in dotbot.update():
                    self.callback(byte.to_bytes(length=1, byteorder="little"))
                    time.sleep(0.005)
                advertising_intervals[idx] += 1
                if advertising_intervals[idx] == 100:
                    for byte in dotbot.advertise():
                        self.callback(byte.to_bytes(length=1, byteorder="little"))
                        time.sleep(0.005)
                    advertising_intervals[idx] = 0
            time.sleep(0.02)

    def write(self, bytes_):
        """Write bytes on the fake serial."""
        for dotbot in self.dotbots:
            dotbot.decode_serial_input(bytes_)
