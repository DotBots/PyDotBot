import threading
import time
from typing import Callable
import math
from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    ApplicationType,
    SailBotData,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
)

delta_t = 0.01  # seconds, used to simulate microcontroller interruptions

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
        self.wind_angle = 0.  # [rad]
        self.wind_speed = 0.  # [m/s]   	

        self.direction = math.pi / 2  # [rad]        
        self.x, self.y = self.convert_geographical_to_cartesian(self.latitude, self.longitude)
        self.v = 0.     # speed [m/s]
        self.w = 0.     # angular velocity [rad/s]

        # inputs
        self.rudder_in = 0    # rudder slider
        self.sail_in = 0      # sail slider


        self.controller = "MANUAL"

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
        self.x += 0.1 * self.rudder_in
        self.y += 0.1 * self.sail_in
        self.latitude, self.longitude  = self.convert_cartesian_to_geographical(self.x, self.y)

        self.direction = (self.direction + math.pi / 36) % (math.pi * 2)
        self.wind_angle = (self.wind_angle - math.pi / 10) % (math.pi * 2)

    def state_space_model(self):
        # define model parameters
        p1 = 0.03  # drift coefficient [-]
        p2 = 40    # tangential friction [kgs^−1]
        p3 = 6000  # angular friction [kgm]
        p4 = 200   # sail lift [kgs^−1]
        p5 = 1500  # rudder lift [kgs^−1]
        p6 = 0.5   # distance to sail CoE [m]
        p7 = 0.5   # distance to mast [m]
        p8 = 2     # distance to rudder [m]
        p9 = 300   # mass of boat [kg]
        p10 = 400  # moment of inertia [kgm^2]
        p11 = 0.2  # rudder break coefficient [-]

        # convert to radians
        rudder_in_rad = self.map_slider(self.rudder_in, -math.pi/6, math.pi/6)
        sail_in_rad = self.map_slider(self.sail_in, -math.pi/2, math.pi/2)

        # get apparent wind speed and angle, f(v,heading,true_wind)
        self.true2apparent_wind()

        # rudder and sail forces
        g_r = p5 * self.v**2 * math.sin(rudder_in_rad)
        g_s = p4 * self.wind_speed * math.sin(sail_in_rad - self.wind_angle)

        # state-space model
        x_dot = self.v * math.cos(self.direction) + p1 * self.true_wind_speed * math.cos(self.true_wind_angle)
        y_dot = self.v * math.sin(self.direction) + p1 * self.true_wind_speed * math.sin(self.true_wind_angle)
        direction_dot = self.w
        v_dot = (g_s * math.sin(sail_in_rad) - g_r * p11 * math.sin(rudder_in_rad) - p2 * self.v**2) / p9
        w_dot = (g_s * (p6 - p7 * math.cos(sail_in_rad)) - g_r * p8 * math.cos(rudder_in_rad) - p3 * self.w * self.v) / p10 

        # Update state-space variables and apparent wind angle
        self.x += x_dot * delta_t
        self.y += y_dot * delta_t
        self.direction += direction_dot * delta_t
        self.v += v_dot * delta_t
        self.w += w_dot * delta_t

        # Get latitude and longitude from cartesian coordinates
        self.latitude, self.longitude  = self.convert_cartesian_to_geographical(self.x, self.y)


    def true2apparent_wind(self):
        Wc_aw = (self.true_wind_speed * math.cos(self.true_wind_angle - self.direction) - self.v,
                 self.true_wind_speed * math.sin(self.true_wind_angle - self.direction))

        self.wind_speed = math.sqrt(Wc_aw[0]**2 + Wc_aw[1]**2)
        self.wind_angle = math.atan2(Wc_aw[1], Wc_aw[0])

    def map_slider(self, value, target_min, target_max):
        slider_min, slider_max = -127, 127
        return target_min + (target_max - target_min) * (value - slider_min) / (slider_max - slider_min)

    def update(self):
        if self.controller == "MANUAL":
            # self.state_space_model()
            self.debug_mode()
            
        return self.encode_serial_output()

    def decode_serial_input(self, frame):
        payload = ProtocolPayload.from_bytes(hdlc_decode(frame))

        if self.address == hex(payload.header.destination)[2:]:
            if payload.payload_type == PayloadType.CMD_MOVE_RAW:
                self.controller = "MANUAL"
                self.rudder_in = payload.values.left_x - 256 if payload.values.left_x > 127 else payload.values.left_x
                self.sail_in = payload.values.right_y - 256 if payload.values.right_y > 127 else payload.values.right_y

    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.SAILBOT_DATA,
            SailBotData(
                ( 90 - int(math.degrees(self.direction)) )% 360,
                int(self.latitude * 1e6),
                int(self.longitude * 1e6),
                ( -int(math.degrees(self.wind_angle)) ) % 360,
                int( math.degrees(self.map_slider(self.rudder_in, -math.pi/6, math.pi/6)) ),
                int( math.degrees(self.map_slider(self.sail_in, -math.pi/5.2, math.pi/5.2)) ),
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

    def convert_cartesian_to_geographical(self, x, y):
        latitude = ((((y * 0.180) / math.pi) / self.earth_radius_km) + self.origin_coord_lat)
        longitude = ((((x * 0.180) / math.pi / self.cos_phi_0) / self.earth_radius_km) + self.origin_coord_lon)

        return latitude, longitude

    def convert_geographical_to_cartesian(self, latitude, longitude):
        x = ((longitude - self.origin_coord_lon) * self.earth_radius_km * self.cos_phi_0 * math.pi) / 0.180
        y = ((latitude - self.origin_coord_lat) * self.earth_radius_km * math.pi) / 0.180

        return x, y


class SailBotSimSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, callback: Callable):
        self.sailbots = [
            SailBotSim("1234567890123456"),
        ]

        self.callback = callback
        super().__init__(daemon=True) # Automatically close when the main program exits
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("SailBot Simulation Started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        for sailbot in self.sailbots:
            for byte in sailbot.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))

        next_time = time.time() + delta_t

        while True:
            current_time = time.time()  # Simulate microcontroller clock interruptions
            if current_time >= next_time:
                for sailbot in self.sailbots:
                    for byte in sailbot.update():
                        self.callback(byte.to_bytes(length=1, byteorder="little"))

                next_time = current_time + delta_t

    def write(self, bytes_):
        """Write bytes on the fake serial. It is an identical interface to the real gateway."""
        for sailbot in self.sailbots:
            sailbot.decode_serial_input(bytes_)