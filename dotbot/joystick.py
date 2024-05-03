# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module implementing a joystick Dotbot controller."""

# pylint: disable=attribute-defined-outside-init

import asyncio
import os
import sys

import click

from dotbot import (
    CONTROLLER_HOSTNAME_DEFAULT,
    CONTROLLER_PORT_DEFAULT,
    DOTBOT_ADDRESS_DEFAULT,
    pydotbot_version,
)
from dotbot.logger import LOGGER, setup_logging
from dotbot.models import DotBotMoveRawCommandModel
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient

# Pygame support prompt is annoying, it can be hidden using an environment variable
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402, pylint: disable=wrong-import-order, wrong-import-position

JOYSTICK_HYSTERERIS_THRES = 0.09
JOYSTICK_AXIS_COUNT = 4
REFRESH_PERIOD = 0.05
NULL_POSITION = [0.0, 0.0, 0.0, 0.0]

DOTBOT_APPLICATION_DEFAULT = "sailbot"
APPLICATION_TYPE_MAP = {
    "dotbot": ApplicationType.DotBot,
    "sailbot": ApplicationType.SailBot,
}


class JoystickController:
    """A Dotbot controller for a joystick interface."""

    def __init__(
        self, joystick_index, hostname, port, https, dotbot_address, application
    ):
        """Initialize the joystick controller."""
        self.api = RestClient(hostname, port, https)
        self.dotbots = []
        self.dotbot_address = dotbot_address
        self.application = APPLICATION_TYPE_MAP[application]
        pygame.init()  # pylint: disable=no-member
        pygame.joystick.init()  # joysticks initialization
        self._logger = LOGGER.bind(context=__name__)
        if pygame.joystick.get_count() < joystick_index + 1:
            self._logger.error("No joystick connected")
            sys.exit("Error: No joystick connected.\nExiting program...")
        self.joystick = pygame.joystick.Joystick(
            joystick_index
        )  # instantiation of a joystick
        self.joystick.init()  # initialization of the joystick
        num_axes = self.joystick.get_numaxes()
        if num_axes < JOYSTICK_AXIS_COUNT:
            self._logger.error("Not enough axes")
            sys.exit(
                f"Not enough axes on your joystick. {num_axes} found, expected at least {JOYSTICK_AXIS_COUNT}."
            )
        self.previous_positions = NULL_POSITION
        self._logger.info("Controller initialized", num_axes=num_axes)

    @property
    def active_dotbot(self):
        _active_dotbot = self.dotbot_address
        if _active_dotbot == DOTBOT_ADDRESS_DEFAULT:
            if self.dotbots and self.dotbots[0]["status"] == 0:
                _active_dotbot = self.dotbots[0]["address"]
            else:
                self._logger.info("No active DotBot")
                return
        elif _active_dotbot not in [dotbot["address"] for dotbot in self.dotbots]:
            self._logger.info("Active DotBot not available")
            return
        return _active_dotbot

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

    async def fetch_active_dotbots(self):
        while 1:
            self.dotbots = await self.api.fetch_active_dotbots()
            await asyncio.sleep(1)

    async def start(self):
        """Starts to read continuously joystick positions."""
        asyncio.create_task(self.fetch_active_dotbots())
        while True:
            # fetch positions from joystick
            positions = self.pos_from_joystick()
            if positions != NULL_POSITION or self.previous_positions != NULL_POSITION:
                self._logger.info("refresh positions", positions=positions)
                await self.api.send_move_raw_command(
                    self.active_dotbot,
                    self.application,
                    DotBotMoveRawCommandModel(
                        left_x=int(positions[0]),
                        left_y=int(positions[1]),
                        right_x=int(positions[2]),
                        right_y=int(positions[3]),
                    ),
                )
            self.previous_positions = positions
            await asyncio.sleep(REFRESH_PERIOD)  # 50ms delay between each update


@click.command()
@click.option(
    "-j",
    "--joystick",
    type=int,
    default=0,
    help="Index of the joystick to use. Defaults to 0",
)
@click.option(
    "-h",
    "--hostname",
    type=str,
    default=CONTROLLER_HOSTNAME_DEFAULT,
    help="Hostname of the controller. Defaults to 'localhost'",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=CONTROLLER_PORT_DEFAULT,
    help=f"HTTP port. Defaults to '{CONTROLLER_PORT_DEFAULT}'",
)
@click.option(
    "-s",
    "--https",
    is_flag=True,
    default=False,
    help="Use HTTPS protocol instead of HTTP",
)
@click.option(
    "-d",
    "--dotbot-address",
    type=str,
    default=DOTBOT_ADDRESS_DEFAULT,
    help=f"Address in hex of the DotBot to control. Defaults to {DOTBOT_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "-a",
    "--application",
    type=click.Choice(["dotbot", "sailbot"]),
    default=DOTBOT_APPLICATION_DEFAULT,
    help=f"Application to control. Defaults to {DOTBOT_APPLICATION_DEFAULT}",
)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"]),
    default="info",
    help="Logging level. Defaults to info",
)
def main(joystick, hostname, port, https, dotbot_address, application, log_level):
    """DotBot joystick controller."""
    print(f"Welcome to the DotBots joystick interface (version: {pydotbot_version()}).")
    setup_logging(None, log_level, ["console"])
    joystick_controller = JoystickController(
        joystick,
        hostname,
        port,
        https,
        dotbot_address,
        application,
    )
    try:
        asyncio.run(joystick_controller.start())
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
