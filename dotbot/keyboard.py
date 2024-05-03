# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module implementing a keyboard Dotbot controller."""

import asyncio
import sys
from dataclasses import dataclass
from enum import Enum

import click

try:
    from pynput import keyboard
except ImportError:
    # On the CI, pynput cannot be imported because of missing X server. Mock
    # the pynput keyboard instead
    from unittest import mock

    keyboard = mock.MagicMock()

from dotbot import (
    CONTROLLER_HOSTNAME_DEFAULT,
    CONTROLLER_PORT_DEFAULT,
    DOTBOT_ADDRESS_DEFAULT,
    pydotbot_version,
)
from dotbot.logger import LOGGER, setup_logging
from dotbot.models import DotBotMoveRawCommandModel, DotBotRgbLedCommandModel
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient

DOTBOT_APPLICATION_DEFAULT = "dotbot"
APPLICATION_TYPE_MAP = {
    "dotbot": ApplicationType.DotBot,
    "sailbot": ApplicationType.SailBot,
}
DIR_KEYS = [
    keyboard.Key.up,
    keyboard.Key.down,
    keyboard.Key.left,
    keyboard.Key.right,
]
COLOR_KEYS = ["r", "g", "b", "y", "p", "w", "n"]


class MotorSpeeds(Enum):
    """Levels used for motor speeds."""

    NORMAL = 84
    BOOST = 100
    SUPERBOOST = 127


def rgb_from_key(key):
    """Compute the RGB values from a key.

    >>> rgb_from_key("r")
    [255, 0, 0]
    >>> rgb_from_key("g")
    [0, 255, 0]
    >>> rgb_from_key("b")
    [0, 0, 255]
    >>> rgb_from_key("y")
    [255, 255, 0]
    >>> rgb_from_key("p")
    [255, 0, 255]
    >>> rgb_from_key("w")
    [255, 255, 255]
    >>> rgb_from_key("n")
    [0, 0, 0]
    >>> rgb_from_key("a")
    [0, 0, 0]
    >>> rgb_from_key("-")
    [0, 0, 0]
    """
    if key == "r":
        result = [255, 0, 0]
    elif key == "g":
        result = [0, 255, 0]
    elif key == "b":
        result = [0, 0, 255]
    elif key == "y":
        result = [255, 255, 0]
    elif key == "p":
        result = [255, 0, 255]
    elif key == "w":
        result = [255, 255, 255]
    else:  # n
        result = [0, 0, 0]
    return result


class KeyboardEventType(Enum):
    """Supported types of keyboard events."""

    PRESSED = 0
    RELEASED = 1


@dataclass
class KeyboardEvent:
    """Data class that handles data of a keyboard event."""

    type_: KeyboardEventType
    key: keyboard.Key


class KeyboardController:
    """Dotbot controller for a keyboard interface."""

    def __init__(self, hostname, port, https, dotbot_address, application):
        """Initializes the keyboard controller."""
        self.api = RestClient(hostname, port, https)
        self.dotbots = []
        self.dotbot_address = dotbot_address
        self.application = APPLICATION_TYPE_MAP[application]
        self.previous_speeds = (0, 0)
        self.active_keys = []
        self.event_queue = asyncio.Queue()
        self._logger = LOGGER.bind(context=__name__)
        self._logger.info("Controller initialized")

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

    async def update_active_keys(self):
        """Coroutine used to handle keyboard events asynchronously."""
        event_loop = asyncio.get_event_loop()

        def on_press(key):
            """Callback called on each keyboard key press event."""
            if key in self.active_keys:
                return
            event_loop.call_soon_threadsafe(
                self.event_queue.put_nowait,
                KeyboardEvent(KeyboardEventType.PRESSED, key),
            )
            self._logger.debug("key pressed", key=key)

        def on_release(key):
            """Callback called on each keyboard key release event."""
            if key not in self.active_keys:
                return
            event_loop.call_soon_threadsafe(
                self.event_queue.put_nowait,
                KeyboardEvent(KeyboardEventType.RELEASED, key),
            )
            self._logger.debug("key released", key=key)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        while 1:
            event = await self.event_queue.get()
            if event.type_ == KeyboardEventType.RELEASED:
                while event.key in self.active_keys:
                    self.active_keys.remove(event.key)
            if event.type_ == KeyboardEventType.PRESSED:
                if hasattr(event.key, "char") and event.key.char in COLOR_KEYS:
                    red, green, blue = rgb_from_key(event.key.char)
                    self._logger.info("color pressed", red=red, green=green, blue=blue)
                    await self.api.send_rgb_led_command(
                        self.active_dotbot,
                        DotBotRgbLedCommandModel(red=red, green=green, blue=blue),
                    )
                if event.key not in self.active_keys:
                    self.active_keys.append(event.key)

    def speeds_from_keys(self):  # pylint: disable=too-many-return-statements
        """Computes the left/right wheels speeds from current key pressed."""
        if any(key in self.active_keys for key in DIR_KEYS):
            speed = MotorSpeeds.NORMAL
            if keyboard.Key.ctrl in self.active_keys:
                speed = MotorSpeeds.BOOST
                if keyboard.Key.alt in self.active_keys:
                    speed = MotorSpeeds.SUPERBOOST
            if (
                keyboard.Key.up in self.active_keys
                and keyboard.Key.left in self.active_keys
            ):
                return speed.value * 0.75, speed.value
            if (
                keyboard.Key.up in self.active_keys
                and keyboard.Key.right in self.active_keys
            ):
                return speed.value, speed.value * 0.75
            if (
                keyboard.Key.down in self.active_keys
                and keyboard.Key.left in self.active_keys
            ):
                return -speed.value * 0.75, -speed.value
            if (
                keyboard.Key.down in self.active_keys
                and keyboard.Key.right in self.active_keys
            ):
                return -speed.value, -speed.value * 0.75
            if keyboard.Key.up in self.active_keys:
                return speed.value, speed.value
            if keyboard.Key.down in self.active_keys:
                return -speed.value, -speed.value
            if keyboard.Key.left in self.active_keys:
                return 0, speed.value
            if keyboard.Key.right in self.active_keys:
                return speed.value, 0
        return 0, 0

    async def refresh_speeds(self):
        """Refresh the motor speeds and send an update if needed."""
        left_speed, right_speed = self.speeds_from_keys()
        if (left_speed, right_speed) != (0, 0) or self.previous_speeds != (0, 0):
            self._logger.info("refresh speeds", left=left_speed, right=right_speed)
            await self.api.send_move_raw_command(
                self.active_dotbot,
                self.application,
                DotBotMoveRawCommandModel(
                    left_x=0, left_y=left_speed, right_x=0, right_y=right_speed
                ),
            )
        self.previous_speeds = (left_speed, right_speed)
        await asyncio.sleep(0.05)

    async def fetch_active_dotbots(self):
        while 1:
            self.dotbots = await self.api.fetch_active_dotbots()
            await asyncio.sleep(1)

    async def start(self):
        """Starts to continuously listen on keyboard key press/release events."""
        asyncio.create_task(self.fetch_active_dotbots())
        asyncio.create_task(self.update_active_keys())
        while 1:
            await self.refresh_speeds()


@click.command()
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
def main(hostname, port, https, dotbot_address, application, log_level):
    """DotBot keyboard controller."""
    print(f"Welcome to the DotBots keyboard interface (version: {pydotbot_version()}).")
    setup_logging(None, log_level, ["console"])
    keyboard_controller = KeyboardController(
        hostname,
        port,
        https,
        dotbot_address,
        application,
    )
    try:
        asyncio.run(keyboard_controller.start())
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
