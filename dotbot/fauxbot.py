import threading
import time
from math import atan2, cos, pi, sin, sqrt
from typing import Callable

from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    ApplicationType,
    FauxBotData,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
)

R = 1
L = 2
t_step = 0.01


def diff_drive_bot(x_pos_old, y_pos_old, theta_old, v_right, v_left):
    ## second step - execute state space model of a rigid differential drive robot
    x_dot = R / 2 * (v_right + v_left) * cos(theta_old - pi) * (50000)
    y_dot = R / 2 * (v_right + v_left) * sin(theta_old - pi) * (50000)
    theta_dot = R / L * (-v_right + v_left)

    x_pos = x_pos_old + x_dot * t_step
    y_pos = y_pos_old + y_dot * t_step
    theta = (theta_old + theta_dot * t_step) % (2 * pi)

    return x_pos, y_pos, theta


class FauxBot:
    def __init__(self, address):
        self.address = address
        self.pos_x = 0.5 * 1e6
        self.pos_y = 0.5 * 1e6
        self.theta = 0

        self.v_left = 0
        self.v_right = 0

        self.waypoint_threshold = 0
        self.num_waypoints = 0
        self.waypoints_x = []
        self.waypoints_y = []
        self.waypoint_index = 0

        self.controller = "MANUAL"

    @property
    def header(self):
        return ProtocolHeader(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
            swarm_id=int(SWARM_ID_DEFAULT, 16),
            application=ApplicationType.DotBot,
            version=PROTOCOL_VERSION,
        )

    def update(self):
        pos_x_old = self.pos_x
        pos_y_old = self.pos_y
        theta_old = self.theta

        if self.controller == "MANUAL":
            self.pos_x, self.pos_y, self.theta = diff_drive_bot(
                pos_x_old, pos_y_old, theta_old, self.v_right, self.v_left
            )

        elif self.controller == "AUTOMATIC":
            delta_x = self.pos_x - self.waypoints_x[self.waypoint_index]
            delta_y = self.pos_y - self.waypoints_y[self.waypoint_index]
            distanceToTarget = sqrt(delta_x**2 + delta_y**2)

            # check if we are close enough to the "next" waypoint
            if distanceToTarget < self.waypoint_threshold:
                print("reached one!")
                self.waypoint_index += 1

                # check if there are no more waypoints:
                if self.waypoint_index >= self.num_waypoints:
                    self.v_left = 0
                    self.v_right = 0
                    self.waypoint_index -= 1
                    self.controller = "MANUAL"

            else:
                robotAngle = self.theta
                angleToTarget = atan2(delta_y, delta_x)
                if robotAngle >= pi:
                    robotAngle = robotAngle - 2 * pi
                # if (angleToTarget < 0):
                #    angleToTarget = 2*pi + angleToTarget

                error_angle = ((angleToTarget - robotAngle + pi) % (2 * pi)) - pi
                print(robotAngle, angleToTarget)
                print(error_angle)

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
        payload = ProtocolPayload(
            self.header,
            PayloadType.ADVERTISEMENT,
            Advertisement(),
        )
        return hdlc_encode(payload.to_bytes())

    def parse_serial_input(self, frame):
        payload = ProtocolPayload.from_bytes(hdlc_decode(frame))

        if self.address == hex(payload.header.destination)[2:]:
            if payload.payload_type == PayloadType.CMD_MOVE_RAW:
                self.controller = "MANUAL"
                self.v_left = payload.values.left_y
                self.v_right = payload.values.right_y

                if self.v_left > 127:
                    self.v_left = self.v_left - 256
                if self.v_right > 127:
                    self.v_right = self.v_right - 256

            elif payload.payload_type == PayloadType.LH2_WAYPOINTS:
                self.controller = "AUTOMATIC"
                decoded_frame = hdlc_decode(frame)
                self.num_waypoints = decoded_frame[25]
                self.waypoint_threshold = decoded_frame[26] * 1000

                for i in range(self.num_waypoints):
                    self.waypoints_x.append(
                        int.from_bytes(
                            decoded_frame[27 + 12 * i : 30 + 12 * i], byteorder="little"
                        )
                    )
                    self.waypoints_y.append(
                        int.from_bytes(
                            decoded_frame[31 + 12 * i : 34 + 12 * i], byteorder="little"
                        )
                    )

        # print(self.v_left, self.v_right)

    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.FAUXBOT_DATA,
            FauxBotData(
                int(self.theta * 180 / pi + 90),
                int(self.pos_x),
                int(self.pos_y),
            ),
        )
        return hdlc_encode(payload.to_bytes())


class FauxBotSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, callback: Callable):
        self.fauxbots = [
            FauxBot("1234567890123456"),
            FauxBot("4987654321098765"),
        ]

        self.callback = callback
        super().__init__(daemon=True)
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("FauxBot Simulation Started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        advertising_intervals = [0] * len(self.fauxbots)
        for fauxbot in self.fauxbots:
            # print(fauxbotObject.address)
            for byte in fauxbot.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
                time.sleep(0.001)

        while 1:
            for idx, fauxbot in enumerate(self.fauxbots):
                for byte in fauxbot.update():
                    self.callback(byte.to_bytes(length=1, byteorder="little"))
                    time.sleep(0.001)

                advertising_intervals[idx] += 1
                if advertising_intervals[idx] == 4:
                    for byte in fauxbot.advertise():
                        self.callback(byte.to_bytes(length=1, byteorder="little"))
                        time.sleep(0.001)
                    advertising_intervals[idx] = 0
                # time.sleep(0.01)
            time.sleep(0.01)

    def write(self, bytes_):
        """Write bytes on the fake serial. It is an identical interface to the real gateway."""
        for fauxbot in self.fauxbots:
            fauxbot.parse_serial_input(bytes_)