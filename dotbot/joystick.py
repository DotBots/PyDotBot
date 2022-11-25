"""Module implementing a joystick Dotbot controller."""
# pylint: disable=attribute-defined-outside-init

import asyncio
import os
import sys

from dotbot.controller import ControllerBase
from dotbot.protocol import PayloadType, ProtocolPayload, CommandMoveRaw

# Pygame support prompt is annoying, it can be hidden using an environment variable
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402, pylint: disable=wrong-import-order, wrong-import-position


JOYSTICK_HYSTERERIS_THRES = 0.09
JOYSTICK_AXIS_COUNT = 4
REFRESH_PERIOD = 0.05
NULL_POSITION = [0.0, 0.0, 0.0, 0.0]


class JoystickController(ControllerBase):
    """A Dotbot controller for a joystick interface."""

    def init(self):
        """Initialize the joystick controller."""
        pygame.init()  # pylint: disable=no-member
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
        self.previous_positions = NULL_POSITION

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

    async def start(self):
        """Starts to read continuously joystick positions."""
        while True:
            # fetch positions from joystick
            positions = self.pos_from_joystick()
            if positions != NULL_POSITION or self.previous_positions != NULL_POSITION:
                self.send_payload(
                    ProtocolPayload(
                        self.header,
                        PayloadType.CMD_MOVE_RAW,
                        CommandMoveRaw(*positions),
                    )
                )
            self.previous_positions = positions
            await asyncio.sleep(REFRESH_PERIOD)  # 50ms delay between each update
