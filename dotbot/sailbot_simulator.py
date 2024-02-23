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
    SailBotData,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
)

t_step = 0.01



class SailSim:
    def __init__(self, address):
        self.address = address

        self.direction = 40
        self.latitude = 48.832313766146896
        self.longitude = 2.4126897594949184
        self.wind_angle = 30    # uint angles from 0 to 359
        # gps_position=DotBotGPSPosition(latitude=48.832313766146896, longitude=2.4126897594949184)

        self.rudder_slider = 0
        self.sail_slider = 0

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
    
    def diff_drive_bot(self, rudder, sail):
        # si tengo tiempo, editar esta función. Podría solo llamar a self
        # for now, just move sailbot proportionally, and increase direction
        latitude  = self.latitude  + rudder*1E-2
        longitude = self.longitude + sail*1E-2
        direction = (self.direction + 1) % 360

        return latitude, longitude, direction

    def update(self):
        if self.controller == "MANUAL":
            self.latitude, self.longitude, self.direction = self.diff_drive_bot(
                self.v_right, self.v_left
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
                # see line 227 sailbot app
                self.rudder_slider = payload.values.left_x
                self.sail_slider = payload.values.right_y

        print(self.rudder_slider, self.sail_slider)

    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.SAILBOT_DATA,
            SailBotData(
                int(self.direction),
                int(self.latitude),
                int(self.longitude * 1e6),
                int(self.wind_angle * 1e6),
            ),
        )
        return hdlc_encode(payload.to_bytes())


class SailSimSerialInterface(threading.Thread):
    """Bidirectional serial interface to control simulated robots"""

    def __init__(self, callback: Callable):
        self.sailsims = [
            SailSim("1234567890123456"),
        ]

        self.callback = callback
        super().__init__(daemon=True)
        self.start()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("SailBot Simulation Started")

    def run(self):
        """Listen continuously at each byte received on the fake serial interface."""
        advertising_intervals = [0] * len(self.sailsims)
        for sailsim in self.sailsims:
            # print(fauxbotObject.address)
            for byte in sailsim.advertise():
                self.callback(byte.to_bytes(length=1, byteorder="little"))
                time.sleep(0.001)

        while 1:
            for idx, sailsim in enumerate(self.sailsims):
                for byte in sailsim.update():
                    self.callback(byte.to_bytes(length=1, byteorder="little"))
                    time.sleep(0.001)

                advertising_intervals[idx] += 1
                if advertising_intervals[idx] == 4:
                    for byte in sailsim.advertise():
                        self.callback(byte.to_bytes(length=1, byteorder="little"))
                        time.sleep(0.001)
                    advertising_intervals[idx] = 0
            time.sleep(0.01)

    def write(self, bytes_):
        """Write bytes on the fake serial. It is an identical interface to the real gateway."""
        for sailbot in self.sailsims:
            sailbot.parse_serial_input(bytes_)