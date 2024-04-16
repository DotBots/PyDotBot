import math
import threading
import time
from typing import Callable

from numpy import clip

from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    ApplicationType,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
    SailBotData,
)

sim_delta_t = 0.01  # second
control_delta_t = 1  # second

max_rudder_angle = (-math.pi / 6, math.pi / 6)
max_sail_angle = (0, math.pi / 2)


class SailBotSim:
    def __init__(self, address):
        self.address = address

        # constants
        self.earth_radius_km = 6371
        self.origin_coord_lat = 48.825908
        self.origin_coord_lon = 2.406433
        self.cos_phi_0 = 0.658139837

        self.true_wind_speed = 4  # [m/s]
        self.true_wind_angle = 0.34906  # [rad] (20 degrees)

        # initialisations
        self.latitude = 48.832313
        self.longitude = 2.412689
        self.app_wind_angle = 0.0  # [rad]
        self.app_wind_speed = 0.0  # [m/s]

        self.direction = math.pi / 2  # [rad]
        (self.x, self.y) = self.geographical2cartesian(self.latitude, self.longitude)
        self.v = 0.0  # speed [m/s]
        self.w = 0.0  # angular velocity [rad/s]

        # inputs received by controller
        self.rudder_slider = 0  # rudder slider
        self.sail_slider = 0  # sail slider

        self.operation_mode = "MANUAL"

        # autonomous mode initialisations
        self.waypoint_threshold = 0
        self.num_waypoints = 0
        self.waypoints = []
        self.next_waypoint = 0
        self.zigzag_flag = False

    @property
    def header(self):
        return ProtocolHeader(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
            swarm_id=int(SWARM_ID_DEFAULT, 16),
            application=ApplicationType.SailBot,
            version=PROTOCOL_VERSION,
        )

    def debug_mode(self):
        # mode for testing GUI, inputs and outputs
        self.direction = (self.direction + math.pi / 18) % (math.pi * 2)
        self.app_wind_angle = (self.app_wind_angle - math.pi / 28) % (math.pi * 2)

    def state_space_model(self, rudder_in_rad, sail_length_in_rad):
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
        self.true2apparent_wind()

        # map mainsheet length to actual sail angle
        sail_in_rad = self.mainsheet2sail_angle(sail_length_in_rad, self.app_wind_angle)

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
        self.x += x_dot * sim_delta_t
        self.y += y_dot * sim_delta_t
        self.direction += direction_dot * sim_delta_t
        self.v += v_dot * sim_delta_t
        self.w += w_dot * sim_delta_t

        # get latitude and longitude from cartesian coordinates
        (self.latitude, self.longitude) = self.cartesian2geographical(self.x, self.y)

    def true2apparent_wind(self):
        Wc_aw = (
            self.true_wind_speed * math.cos(self.true_wind_angle - self.direction)
            - self.v,
            self.true_wind_speed * math.sin(self.true_wind_angle - self.direction),
        )

        self.app_wind_speed = math.sqrt(Wc_aw[0] ** 2 + Wc_aw[1] ** 2)
        self.app_wind_angle = math.atan2(Wc_aw[1], Wc_aw[0])

    def map_slider(self, value, target_min, target_max):
        slider_min, slider_max = -128, 128
        return target_min + (target_max - target_min) * (value - slider_min) / (
            slider_max - slider_min
        )

    def mainsheet2sail_angle(self, sail_in_length_rad, app_wind_angle):
        if math.cos(app_wind_angle) + math.cos(sail_in_length_rad) > 0:
            # sail is tight
            sail_out_rad = -math.copysign(sail_in_length_rad, math.sin(app_wind_angle))
        else:
            # sail is loose
            sail_out_rad = math.pi + app_wind_angle

        sail_out_rad = (sail_out_rad + math.pi) % (2 * math.pi) - math.pi
        return sail_out_rad

    def simulation_update(self):
        # update state-space model every sim_delta_t seconds
        # convert to radians
        rudder_in_rad = self.map_slider(
            self.rudder_slider, max_rudder_angle[0], max_rudder_angle[1]
        )
        sail_length_in_rad = self.map_slider(
            self.sail_slider, max_sail_angle[0], max_sail_angle[1]
        )

        self.state_space_model(rudder_in_rad, sail_length_in_rad)
        # self.debug_mode()

        return self.encode_serial_output()

    def control_loop_update(self):
        if not self.waypoints:
            return
        print(f"next waypoint: {self.next_waypoint}")
        print(f"waypoint threshold: {self.waypoint_threshold}")
        print(f"waypoint list: {self.waypoints}")

        # update control inputs if in automatic mode
        if self.next_waypoint >= len(self.waypoints):
            print("Finished!")
            self.waypoints = []
            self.next_waypoint = 0
            self.zigzag_flag = False
            self.operation_mode = "MANUAL"
            return

        # convert current position and next waypoint to cartesian
        current_xy = self.geographical2cartesian(self.latitude, self.longitude)
        next_geo = self.waypoints[self.next_waypoint]
        next_xy = self.geographical2cartesian(next_geo[0], next_geo[1])

        # check if current position is within the threshold
        distance2target = math.sqrt(
            (next_xy[0] - current_xy[0]) ** 2 + (next_xy[1] - current_xy[1]) ** 2
        )
        if distance2target < self.waypoint_threshold:
            self.next_waypoint += 1
            self.zigzag_flag = False
            return

        # compute angle between current position and target
        angle2target = math.atan2(
            next_xy[1] - current_xy[1], next_xy[0] - current_xy[0]
        )
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
                print("In irons! Starting zig-zag routine")
                self.zigzag_flag = True

                # initialise zig zag parameters
                self.zigzag_width = 15  # meters
                self.zigzag_dir = False  # where to start zig-zagging (can be improved by choosing the shortest path)
                self.line2target = self.lineClass(current_xy, angle2target)

            # already zig-zagging!
            if self.line2target.distance2point(current_xy) > self.zigzag_width:
                self.zigzag_dir = self.line2target.line_side(current_xy)

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
        sail_length = ((max_sail_angle[0] - max_sail_angle[1]) / math.pi) * abs(
            app_wind_angle
        ) + max_sail_angle[1]
        self.sail_slider = int(clip(sail_length * 512 / math.pi - 128, -128, 127))

        print(f"rudder slider: {self.rudder_slider}")
        print(f"sail slider: {self.sail_slider}")
        print(f"zig-zagging: {self.zigzag_flag}")

        return

    # zig-zag routine helper class
    class lineClass:
        def __init__(self, point, angle_radians):
            x, y = point
            # calculate coefficients for Ax + By + C = 0
            self.A = -math.tan(angle_radians)
            self.B = 1
            self.C = (math.tan(angle_radians) * x) - y

        def distance2point(self, point):
            x0, y0 = point
            # return the distance from the point to the line
            return abs((self.A * x0) + (self.B * y0) + self.C) / math.sqrt(
                self.A**2 + self.B**2
            )

        def line_side(self, point):
            # am I on the left or the right?
            x0, y0 = point
            d = (self.A * x0) + (self.B * y0) + self.C
            return d >= 0

    def decode_serial_input(self, frame):
        payload = ProtocolPayload.from_bytes(hdlc_decode(frame))

        if self.address == hex(payload.header.destination)[2:]:
            if payload.payload_type == PayloadType.CMD_MOVE_RAW:
                self.rudder_slider = (
                    payload.values.left_x - 256
                    if payload.values.left_x > 127
                    else payload.values.left_x
                )
                self.sail_slider = (
                    payload.values.right_y - 256
                    if payload.values.right_y > 127
                    else payload.values.right_y
                )

            if payload.payload_type == PayloadType.GPS_WAYPOINTS:
                self.operation_mode = "AUTOMATIC"
                payload = ProtocolPayload.from_bytes(hdlc_decode(frame))
                self.waypoint_threshold = payload.values.threshold
                self.waypoints = payload.values.waypoints
                self.num_waypoints = len(self.waypoints)

    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.SAILBOT_DATA,
            SailBotData(
                (90 - int(math.degrees(self.direction))) % 360,
                int(self.latitude * 1e6),
                int(self.longitude * 1e6),
                (-int(math.degrees(self.app_wind_angle))) % 360,
                int(
                    math.degrees(
                        self.map_slider(
                            self.rudder_slider, max_rudder_angle[0], max_rudder_angle[1]
                        )
                    )
                ),
                int(
                    math.degrees(
                        self.map_slider(
                            self.sail_slider, max_sail_angle[0], max_sail_angle[1]
                        )
                    )
                ),
            ),
        )
        return hdlc_encode(payload.to_bytes())

    def advertise(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.ADVERTISEMENT,
            Advertisement(),
        )
        return hdlc_encode(payload.to_bytes())

    def cartesian2geographical(self, x, y):
        latitude = (
            ((y * 0.180) / math.pi) / self.earth_radius_km
        ) + self.origin_coord_lat
        longitude = (
            ((x * 0.180) / math.pi / self.cos_phi_0) / self.earth_radius_km
        ) + self.origin_coord_lon

        return latitude, longitude

    def geographical2cartesian(self, latitude, longitude):
        x = (
            (longitude - self.origin_coord_lon)
            * self.earth_radius_km
            * self.cos_phi_0
            * math.pi
        ) / 0.180
        y = (
            (latitude - self.origin_coord_lat) * self.earth_radius_km * math.pi
        ) / 0.180

        return (x, y)


# bidirectional serial interface to control simulated robots
class SailBotSimSerialInterface(threading.Thread):
    def __init__(self, callback: Callable):
        self.sailbots = [
            SailBotSim("1234567890123456"),
        ]

        self.callback = callback
        super().__init__(daemon=True)  # automatically close when the main program exits
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("SailBot simulation started")

    def run(self):
        # listen continuously at each byte received on the fake serial interface
        for sailbot in self.sailbots:
            for byte in sailbot.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))

        next_sim_time = time.time() + sim_delta_t
        next_control_time = time.time() + control_delta_t

        while True:
            current_time = time.time()
            # update simulation every sim_delta_t seconds
            if current_time >= next_sim_time:
                for sailbot in self.sailbots:
                    for byte in sailbot.simulation_update():
                        self.callback(byte.to_bytes(length=1, byteorder="little"))

                next_sim_time = current_time + sim_delta_t

            # update control inputs every control_delta_t seconds
            if current_time >= next_control_time:
                for sailbot in self.sailbots:
                    if sailbot.operation_mode == "AUTOMATIC":
                        sailbot.control_loop_update()

                next_control_time = current_time + control_delta_t

    def write(self, bytes_):
        # write bytes on the fake serial, similar to the real gateway
        for sailbot in self.sailbots:
            sailbot.decode_serial_input(bytes_)
