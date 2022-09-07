"""Module implementing a joystick Dotbot controller."""

import os
import sys
import time

from bot_controller.controller import ControllerBase
from bot_controller.protocol import move_raw_command

# Pygame support prompt is annoying, it can be hidden using an environment variable
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402, pylint: disable=wrong-import-order, wrong-import-position


JOYSTICK_HYSTERERIS_THRES = 0.09
JOYSTICK_AXIS_COUNT = 4
REFRESH_PERIOD = 0.05


class JoystickController(ControllerBase):
    """A Dotbot controller for a joystick interface."""

    def init(self):
        """Initialize the joystick controller."""
        # pylint: disable=no-member
        pygame.init()  # pygame initialization
        pygame.joystick.init()  # joysticks initialization
        if pygame.joystick.get_count() == 0:
            sys.exit("Error: No joystick connected.\nExiting program...")
        self.joystick = pygame.joystick.Joystick(0)  # instantiation of a joystick
        self.joystick.init()  # initialization of the joystick
        num_axes = self.joystick.get_numaxes()
        if num_axes < JOYSTICK_AXIS_COUNT:
            sys.exit(
                f"Not enough axes on your joystick. {num_axes} found, expected at least {JOYSTICK_AXIS_COUNT}."
            )

    def pos_from_joystick(self):
        """Fetch positions of the joystick."""
        pygame.event.pump()  # queue needs to be pumped
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
        """Starts to read continuously joystick positions."""
        while True:
            # fetch positions from joystick
            pos_lj_x, pos_lj_y, pos_rj_x, pos_rj_y = self.pos_from_joystick()
            command = move_raw_command(pos_lj_x, pos_lj_y, pos_rj_x, pos_rj_y)
            self.write(command)  # write via serial
            time.sleep(REFRESH_PERIOD)  # 50ms delay between each update
