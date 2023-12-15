from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode, hdlc_decode
from dotbot.protocol import ProtocolPayload, PayloadType, FauxBotData, PROTOCOL_VERSION, ProtocolHeader, ApplicationType, Advertisement
from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from math import cos, sin

R = 1
L = 1
t_step = 1

def diff_drive_bot(x_pos_old, y_pos_old, theta_old, v_right, v_left):
    
    ## second step - execute state space model of a rigid differential drive robot
    x_dot       = R/2 * (v_right + v_left) * cos(theta_old) * (1/100)
    y_dot       = R/2 * (v_right + v_left) * sin(theta_old) * (1/100)
    theta_dot   = R/L * (v_right - v_left)

    x_pos       = x_pos_old + x_dot * t_step
    y_pos       = y_pos_old + y_dot * t_step
    theta       = theta_dot * t_step
    
    return x_pos, y_pos, theta
    
    
    
class FauxBot():

    def __init__(self, address):
        self.address = address
        self.pos_x = 0.25*1e6
        self.pos_y = 0.25*1e6
        self.theta = 1
        
        self.v_left = 0
        self.v_right = 0
    
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
        self.pos_x, self.pos_y, self.theta = diff_drive_bot(self.pos_x, self.pos_y, self.theta, self.v_right, self.v_left)
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
        if (payload.payload_type == PayloadType.CMD_MOVE_RAW):
            self.v_left = payload.values.left_y
            self.v_right = payload.values.right_y
    
    def encode_serial_output(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.FAUXBOT_DATA,
            FauxBotData(
                int(self.theta),
                int(self.pos_x),
                int(self.pos_y),
            ),
        )
        return hdlc_encode(payload.to_bytes())
