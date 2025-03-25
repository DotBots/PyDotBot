# SPDX-FileCopyrightText: 2024-present Inria
# SPDX-FileCopyrightText: 2024-present Diego Badillo <diego.badillo@sansano.usm.cl>
# SPDX-FileCopyrightText: 2024-present Mališa Vučinić <malisa.vucinic@inria.fr>
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Sailbot simulator for the DotBot project."""

import math
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from numpy import clip

from dotbot import GATEWAY_ADDRESS_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    ApplicationType,
    Frame,
    Header,
    PayloadAdvertisement,
    PayloadSailBotData,
    PayloadType,
)

SIM_DELTA_T = 0.01  # second
CONTROL_DELTA_T = 1  # second

RUDDER_ANGLE_MAX = (-math.pi / 6, math.pi / 6)
SAIL_ANGLE_MAX = (0, math.pi / 2)

# constants
EARTH_RADIUS_KM = 6371
ORIGIN_COORD_LAT = 48.825908
ORIGIN_COORD_LON = 2.406433
COS_PHI_0 = 0.658139837


def cartesian2geographical(x, y):
    """Converts cartesian coordinates to geographical coordinates."""

    latitude = (((y * 0.180) / math.pi) / EARTH_RADIUS_KM) + ORIGIN_COORD_LAT
    longitude = (
        ((x * 0.180) / math.pi / COS_PHI_0) / EARTH_RADIUS_KM
    ) + ORIGIN_COORD_LON

    return latitude, longitude


def geographical2cartesian(latitude, longitude):
    """Converts geographical coordinates to cartesian coordinates."""

    x = ((longitude - ORIGIN_COORD_LON) * EARTH_RADIUS_KM * COS_PHI_0 * math.pi) / 0.180
    y = ((latitude - ORIGIN_COORD_LAT) * EARTH_RADIUS_KM * math.pi) / 0.180

    return (x, y)


class SailBotSimulatorMode(Enum):
    """Operation mode of the sailbot simulator."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"


@dataclass
class Point:
    """Point class for the sailbot simulator."""

    x: float
    y: float


class SailBotSimulatorLineClass:
    """Simulator zig-zag routine helper class."""

    def __init__(self, point: Point, angle_radians):
        # calculate coefficients for Ax + By + C = 0
        self.A = -math.tan(angle_radians)
        self.B = 1
        self.C = (math.tan(angle_radians) * point.x) - point.y

    def distance2point(self, point: Point):
        """Returns the distance from the point to the line."""
        return abs((self.A * point.x) + (self.B * point.y) + self.C) / math.sqrt(
            self.A**2 + self.B**2
        )

    def line_side(self, point: Point):
        """Am I on the left or the right?."""
        d = (self.A * point.x) + (self.B * point.y) + self.C
        return d >= 0


class SailBotSimulator:
    """Simulator class for the sailbot."""

    def __init__(self, address):
        self.address = address

        self.true_wind_speed = 4  # [m/s]
        self.true_wind_angle = 0.34906  # [rad] (20 degrees)

        # initializations
        self.latitude = 48.832313
        self.longitude = 2.412689
        self.app_wind_angle = 0.0  # [rad]
        self.app_wind_speed = 0.0  # [m/s]

        self.direction = math.pi / 2  # [rad]
        self.x, self.y = geographical2cartesian(self.latitude, self.longitude)
        self.v = 0.0  # speed [m/s]
        self.w = 0.0  # angular velocity [rad/s]

        # inputs received by controller
        self.rudder_slider = 0  # rudder slider
        self.sail_slider = 0  # sail slider

        self.operation_mode: SailBotSimulatorMode = SailBotSimulatorMode.MANUAL

        # autonomous mode initialisations
        self.waypoint_threshold = 0
        self.waypoints = []
        self.next_waypoint = 0
        self.zigzag_flag = False

        self.logger = LOGGER.bind(context=__name__)

    @property
    def header(self):
        return Header(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
        )

    def _update_state_space_model(self, rudder_in_rad, sail_length_in_rad):
        # define model parameters
        p1 = 0.03  # drift coefficient [-]
        p2 = 40  # tangential friction [kgs^−1]
        p3 = 6000  # angular friction [kgm]
        p4 = 200  # sail lift [kgs^−1]
        p5 = 1500  # rudder lift [kgs^−1]
        p6 = 0.5  # distance to sail CoE [m]
        p7 = 0.5  # distance to mast [m]
        p8 = 2  # distance to rudder [m]
        p9 = 300  # mass of boat [kg]
        p10 = 400  # moment of inertia [kgm^2]
        p11 = 0.2  # rudder break coefficient [-]

        # get apparent wind speed and angle, f(v,heading,true_wind)
        self._true2apparent_wind()

        # map mainsheet length to actual sail angle
        sail_in_rad = self._mainsheet2sail_angle(
            sail_length_in_rad, self.app_wind_angle
        )

        # rudder and sail forces
        g_r = p5 * self.v**2 * math.sin(rudder_in_rad)
        g_s = p4 * self.app_wind_speed * math.sin(sail_in_rad - self.app_wind_angle)

        # state-space model
        x_dot = self.v * math.cos(
            self.direction
        ) + p1 * self.true_wind_speed * math.cos(self.true_wind_angle)
        y_dot = self.v * math.sin(
            self.direction
        ) + p1 * self.true_wind_speed * math.sin(self.true_wind_angle)
        direction_dot = self.w
        v_dot = (
            g_s * math.sin(sail_in_rad)
            - g_r * p11 * math.sin(rudder_in_rad)
            - p2 * self.v**2
        ) / p9
        w_dot = (
            g_s * (p6 - p7 * math.cos(sail_in_rad))
            - g_r * p8 * math.cos(rudder_in_rad)
            - p3 * self.w * self.v
        ) / p10

        # update state-space variables and apparent wind angle using Euler's method
        self.x += x_dot * SIM_DELTA_T
        self.y += y_dot * SIM_DELTA_T
        self.direction += direction_dot * SIM_DELTA_T
        self.v += v_dot * SIM_DELTA_T
        self.w += w_dot * SIM_DELTA_T

        # get latitude and longitude from cartesian coordinates
        self.latitude, self.longitude = cartesian2geographical(self.x, self.y)

    def _true2apparent_wind(self):
        Wc_aw = (
            self.true_wind_speed * math.cos(self.true_wind_angle - self.direction)
            - self.v,
            self.true_wind_speed * math.sin(self.true_wind_angle - self.direction),
        )

        self.app_wind_speed = math.sqrt(Wc_aw[0] ** 2 + Wc_aw[1] ** 2)
        self.app_wind_angle = math.atan2(Wc_aw[1], Wc_aw[0])

    def _map_slider(self, value, target_min, target_max):
        slider_min, slider_max = -128, 128
        return target_min + (target_max - target_min) * (value - slider_min) / (
            slider_max - slider_min
        )

    def _mainsheet2sail_angle(self, sail_in_length_rad, app_wind_angle):
        if math.cos(app_wind_angle) + math.cos(sail_in_length_rad) > 0:
            # sail is tight
            sail_out_rad = -math.copysign(sail_in_length_rad, math.sin(app_wind_angle))
        else:
            # sail is loose
            sail_out_rad = math.pi + app_wind_angle

        sail_out_rad = (sail_out_rad + math.pi) % (2 * math.pi) - math.pi
        return sail_out_rad

    def simulation_update(self):
        """Updates the state-space model every SIM_DELTA_T seconds convert to radians."""

        rudder_in_rad = self._map_slider(
            self.rudder_slider, RUDDER_ANGLE_MAX[0], RUDDER_ANGLE_MAX[1]
        )
        sail_length_in_rad = self._map_slider(
            self.sail_slider, SAIL_ANGLE_MAX[0], SAIL_ANGLE_MAX[1]
        )

        self._update_state_space_model(rudder_in_rad, sail_length_in_rad)

        return self.encode_serial_output()

    def control_loop_update(self):
        """Control loop for the sailbot in automatic mode."""

        if not self.waypoints:
            return
        self.logger.debug("Loop update")
        logger = self.logger.bind(
            next_waypoint=self.next_waypoint,
            waypoint_threshold=self.waypoint_threshold,
            waypoints=self.waypoints,
        )
        logger.debug("Loop start")

        # update control inputs if in automatic mode
        if self.next_waypoint >= len(self.waypoints):
            logger.debug("Finished!")
            self.waypoints = []
            self.next_waypoint = 0
            self.zigzag_flag = False
            self.operation_mode = SailBotSimulatorMode.MANUAL
            return

        # convert current position and next waypoint to cartesian
        current_x, current_y = geographical2cartesian(self.latitude, self.longitude)
        next_geo = self.waypoints[self.next_waypoint]
        next_x, next_y = geographical2cartesian(
            next_geo.latitude / 1e6, next_geo.longitude / 1e6
        )

        # check if current position is within the threshold
        distance2target = math.sqrt(
            (next_x - current_x) ** 2 + (next_y - current_y) ** 2
        )
        if distance2target < self.waypoint_threshold:
            self.next_waypoint += 1
            self.zigzag_flag = False
            return

        # compute angle between current position and target
        angle2target = math.atan2(next_y - current_y, next_x - current_x)
        angle2target %= 2 * math.pi
        true_wind = self.true_wind_angle % (2 * math.pi)

        # check if to get there, we have to sail against the wind
        in_irons_angle = 0.8  # radians

        upper_bound_irons = (true_wind + math.pi + in_irons_angle) % (2 * math.pi)
        lower_bound_irons = (true_wind + math.pi - in_irons_angle) % (2 * math.pi)

        detected_irons = False

        if lower_bound_irons > upper_bound_irons:
            if angle2target < upper_bound_irons or angle2target > lower_bound_irons:
                detected_irons = True
        else:
            if angle2target < upper_bound_irons and angle2target > lower_bound_irons:
                detected_irons = True

        if detected_irons:
            if self.zigzag_flag is False:
                logger.debug("In irons! Starting zig-zag routine")
                self.zigzag_flag = True

                # initialise zig zag parameters
                self.zigzag_width = 15  # meters
                self.zigzag_dir = False  # where to start zig-zagging (can be improved by choosing the shortest path)
                self.line2target = SailBotSimulatorLineClass(
                    Point(current_x, current_y), angle2target
                )

            # already zig-zagging!
            if (
                self.line2target.distance2point(Point(current_x, current_y))
                > self.zigzag_width
            ):
                self.zigzag_dir = self.line2target.line_side(
                    Point(current_x, current_y)
                )

            # redefine reference heading
            angle2target = upper_bound_irons if self.zigzag_dir else lower_bound_irons

        else:
            # return to normal mode
            self.zigzag_flag = False

        # calculate error between angle2target and current heading
        error_heading2target = angle2target - self.direction
        error_heading2target = (error_heading2target + math.pi) % (
            2 * math.pi
        ) - math.pi

        # map error to rudder angle (proportional controller)
        Kp = -256 / math.pi  # control proportional constant
        self.rudder_slider = int(clip(error_heading2target * Kp, -128, 127))

        # linear map apparent wind angle to sail opening
        app_wind_angle = (self.app_wind_angle + math.pi) % (2 * math.pi) - math.pi
        sail_length = ((SAIL_ANGLE_MAX[0] - SAIL_ANGLE_MAX[1]) / math.pi) * abs(
            app_wind_angle
        ) + SAIL_ANGLE_MAX[1]
        self.sail_slider = int(clip(sail_length * 512 / math.pi - 128, -128, 127))

        logger = self.logger.bind(
            rudder_slider=self.rudder_slider,
            sail_slider=self.sail_slider,
            zigzag_flag=self.zigzag_flag,
        )
        logger.debug("Loop end")

    def decode_serial_input(self, frame):
        """Decode the serial input received from the gateway."""
        bytes_ = hdlc_decode(frame)
        if bytes_[1] in [0xFF, 0xFE]:
            return
        frame = Frame().from_bytes(bytes_)
        frame = Frame().from_bytes(hdlc_decode(frame))

        if self.address == hex(frame.header.destination)[2:]:
            if frame.payload_type == PayloadType.CMD_MOVE_RAW:
                self.rudder_slider = (
                    frame.payload.left_x - 256
                    if frame.payload.left_x > 127
                    else frame.payload.left_x
                )
                self.sail_slider = (
                    frame.payload.right_y - 256
                    if frame.payload.right_y > 127
                    else frame.payload.right_y
                )

            if frame.payload_type == PayloadType.GPS_WAYPOINTS:
                self.operation_mode = SailBotSimulatorMode.MANUAL
                self.waypoint_threshold = frame.payload.threshold
                self.waypoints = frame.payload.waypoints
                if self.waypoints:
                    self.operation_mode = SailBotSimulatorMode.AUTOMATIC

    def encode_serial_output(self):
        """Encode the sailbot data to be sent to the gateway."""

        payload = PayloadSailBotData(
            direction=(90 - int(math.degrees(self.direction))) % 360,
            latitude=int(self.latitude * 1e6),
            longitude=int(self.longitude * 1e6),
            wind_angle=(-int(math.degrees(self.app_wind_angle))) % 360,
            rudder_angle=int(
                math.degrees(
                    self._map_slider(
                        self.rudder_slider, RUDDER_ANGLE_MAX[0], RUDDER_ANGLE_MAX[1]
                    )
                )
            ),
            sail_angle=int(
                math.degrees(
                    self._map_slider(
                        self.sail_slider, SAIL_ANGLE_MAX[0], SAIL_ANGLE_MAX[1]
                    )
                )
            ),
        )
        frame = Frame(header=self.header, payload=payload)
        return hdlc_encode(frame.to_bytes())

    def advertise(self):
        """Send an adertisement message to the gateway."""
        frame = Frame(
            header=self.header,
            payload=PayloadAdvertisement(application=ApplicationType.SailBot),
        )
        return hdlc_encode(frame.to_bytes())


class SailBotSimulatorSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots."""

    def __init__(self, callback: Callable):
        self.sailbots = [
            SailBotSimulator("1234567890123456"),
        ]

        self.callback = callback
        super().__init__(daemon=True)  # automatically close when the main program exits
        self.start()
        self.logger = LOGGER.bind(context=__name__)
        self.logger.info("SailBot simulation started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        for sailbot in self.sailbots:
            for byte in sailbot.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))

        next_sim_time = time.time() + SIM_DELTA_T
        next_control_time = time.time() + CONTROL_DELTA_T
        updates = [bytearray()] * len(self.sailbots)
        updates_interval = 0
        while True:
            current_time = time.time()
            # update simulation every SIM_DELTA_T seconds
            if current_time >= next_sim_time:
                for idx, sailbot in enumerate(self.sailbots):
                    updates[idx] = sailbot.simulation_update()
                next_sim_time = current_time + SIM_DELTA_T
            if updates_interval >= 10:
                for update in updates:
                    for byte in update:
                        self.callback(byte.to_bytes(length=1, byteorder="little"))
                        time.sleep(0.001)
                updates_interval = 0
            updates_interval += 1

            # update control inputs every CONTROL_DELTA_T seconds
            if current_time >= next_control_time:
                for sailbot in self.sailbots:
                    if sailbot.operation_mode == SailBotSimulatorMode.AUTOMATIC:
                        sailbot.control_loop_update()

                next_control_time = current_time + CONTROL_DELTA_T
            time.sleep(0.02)

    def write(self, bytes_):
        """Write bytes on the fake serial, similar to the real gateway."""
        for sailbot in self.sailbots:
            sailbot.decode_serial_input(bytes_)
