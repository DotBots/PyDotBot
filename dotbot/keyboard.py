"""Module implementing a keyboard Dotbot controller."""

import asyncio

from dataclasses import dataclass
from enum import Enum

try:
    from pynput import keyboard
except ImportError:
    # On the CI, pynput cannot be imported because of missing X server. Mock
    # the pynput keyboard instead
    from unittest import mock

    keyboard = mock.MagicMock()

from dotbot.protocol import (
    PayloadType,
    ProtocolPayload,
    CommandMoveRaw,
    CommandRgbLed,
)
from dotbot.controller import ControllerBase


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


class KeyboardController(ControllerBase):
    """Dotbot controller for a keyboard interface."""

    def init(self):
        # pylint: disable=attribute-defined-outside-init
        """Initializes the keyboard controller."""
        self.previous_speeds = (0, 0)
        self.active_keys = []
        self.event_queue = asyncio.Queue()

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

        def on_release(key):
            """Callback called on each keyboard key release event."""
            if key not in self.active_keys:
                return
            event_loop.call_soon_threadsafe(
                self.event_queue.put_nowait,
                KeyboardEvent(KeyboardEventType.RELEASED, key),
            )

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        while 1:
            event = await self.event_queue.get()
            if event.type_ == KeyboardEventType.RELEASED:
                self.active_keys.remove(event.key)
            if event.type_ == KeyboardEventType.PRESSED:
                if hasattr(event.key, "char") and event.key.char in COLOR_KEYS:
                    red, green, blue = rgb_from_key(event.key.char)
                    self.send_payload(
                        ProtocolPayload(
                            self.header,
                            PayloadType.CMD_RGB_LED,
                            CommandRgbLed(red, green, blue),
                        )
                    )
                    continue
                self.active_keys.append(event.key)
            self.refresh_speeds()

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

    def refresh_speeds(self):
        """Refresh the motor speeds and send an update if needed."""
        left_speed, right_speed = self.speeds_from_keys()
        if (left_speed, right_speed) != (0, 0) or self.previous_speeds != (0, 0):
            self.send_payload(
                ProtocolPayload(
                    self.header,
                    PayloadType.CMD_MOVE_RAW,
                    CommandMoveRaw(0, left_speed, 0, right_speed),
                )
            )
        # pylint: disable=attribute-defined-outside-init
        self.previous_speeds = (left_speed, right_speed)

    async def start(self):
        """Starts to continuously listen on keyboard key press/release events."""
        asyncio.create_task(self.update_active_keys())
        while 1:
            self.refresh_speeds()
            await asyncio.sleep(0.05)
