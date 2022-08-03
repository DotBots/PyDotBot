import os
import sys
import time

from bot_controller.controller import ControllerBase

# Pygame support prompt is annoying, it can be hidden using an environment variable
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame

from bot_controller.protocol import Command, PROTOCOL_VERSION


JOYSTICK_HYSTERERIS_THRES   = 0.09
JOYSTICK_AXIS_COUNT         = 4
REFRESH_PERIOD              = 0.05


class JoystickController(ControllerBase):

    def init(self):
        pygame.init()                       # pygame initialization
        pygame.joystick.init()              # joysticks initialization
        if pygame.joystick.get_count() == 0:
            sys.exit("Error: No joystick connected.\nExiting program...")
        self.joystick = pygame.joystick.Joystick(0)   # instantiation of a joystick
        self.joystick.init()                          # initialization of the joystick
        num_axes = self.joystick.get_numaxes()
        if num_axes < JOYSTICK_AXIS_COUNT:
            sys.exit(f"Not enough axes on your joystick. {num_axes} found, expected at least {JOYSTICK_AXIS_COUNT}.")

    def payload_from_positions(self, left_joystick_x, left_joystick_y, right_joystick_x, right_joystick_y):
        payload  = bytearray()                                                      # init payload
        payload += PROTOCOL_VERSION.to_bytes(1, 'little')                           # protocol version
        payload += int(Command.MOVE_RAW.value).to_bytes(1, 'little')                # command type (move)
        payload += int(left_joystick_x).to_bytes(1, 'little', signed=True)          # left_x
        payload += int(left_joystick_y).to_bytes(1, 'little', signed=True)          # left_y
        payload += int(right_joystick_x).to_bytes(1, 'little', signed=True)         # right_x
        payload += int(right_joystick_y).to_bytes(1, 'little', signed=True)         # right_y
        return payload

    def pos_from_joystick(self):
        pygame.event.pump()                     # queue needs to be pumped
        positions = []
        for axis_idx in range(JOYSTICK_AXIS_COUNT):
            axis = self.joystick.get_axis(axis_idx)
            # dead zones
            if axis_idx % 2:
                axis = -axis
            if -JOYSTICK_HYSTERERIS_THRES < axis <= JOYSTICK_HYSTERERIS_THRES:
                axis = 0.0
            # from [-1;1] to [-127;127]
            positions.append(axis * 127)
        return positions

    def start(self):
        while True:
            # fetch positions from joystick
            pos_lj_x, pos_lj_y, pos_rj_x, pos_rj_y = self.pos_from_joystick()
            payload = self.payload_from_positions(pos_lj_x, pos_lj_y, pos_rj_x, pos_rj_y)   # configure the payload
            self.write(payload)                                                             # write via serial
            time.sleep(REFRESH_PERIOD)                                                      # 50ms delay between each update
