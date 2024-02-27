import threading
import time
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

delta_t = 0.5  # In seconds, used to simulate microcontroller interruptions

class SailBotSim:
    def __init__(self, address):
        self.address = address

        self.wind_angle_real = 30	# global coordinates

        self.direction = 0          # uint16 when sending (should be angles from 0 to 359, verify!)
        self.latitude = 48.832313   # int32 when sending (multiply by 1E6, only six decimals needed)
        self.longitude = 2.412689   # int32 when sending (multiply by 1E6, only six decimals needed)
        self.wind_angle = 0        	# uint when sending (angles from 0 to 359)

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
    
    def state_space_model(self):
        self.latitude  = self.latitude  + self.rudder_slider*1E-6
        self.longitude = self.longitude + self.sail_slider*1E-6
        self.direction = (self.direction + 10) % 360
        self.wind_angle = (-self.direction + self.wind_angle_real) % 360

    def update(self):
        if self.controller == "MANUAL":
            self.state_space_model()
            
        return self.encode_serial_output()

    def decode_serial_input(self, frame):
        payload = ProtocolPayload.from_bytes(hdlc_decode(frame))

        if self.address == hex(payload.header.destination)[2:]:
            if payload.payload_type == PayloadType.CMD_MOVE_RAW:
                self.controller = "MANUAL"
                self.rudder_slider = payload.values.left_x - 256 if payload.values.left_x > 127 else payload.values.left_x
                self.sail_slider = payload.values.right_y - 256 if payload.values.right_y > 127 else payload.values.right_y

    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.SAILBOT_DATA,
            SailBotData(
                int(self.direction),
                int(self.latitude * 1e6),
                int(self.longitude * 1e6),
                int(self.wind_angle),
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