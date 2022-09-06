"""Module implementing a keyboard Dotbot controller."""

import time

from enum import Enum

from pynput import keyboard

from bot_controller.protocol import Command, PROTOCOL_VERSION
from bot_controller.controller import ControllerBase


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


class KeyboardController(ControllerBase):
    """Dotbot controller for a keyboard interface."""

    def init(self):
        """Initializes the keyboard controller."""
        self.active_keys = []
        self.listener = keyboard.Listener(
            on_press=self.on_press, on_release=self.on_release
        )

    def on_press(self, key):
        """Callback called on each keyboard key press event."""
        if key in self.active_keys:
            return
        if hasattr(key, "char") and key.char in COLOR_KEYS:
            red, green, blue = rgb_from_key(key.char)
            payload = bytearray()
            payload += PROTOCOL_VERSION.to_bytes(1, "little")
            payload += int(Command.RGB_LED.value).to_bytes(1, "little")
            payload += int(red).to_bytes(1, "little")
            payload += int(green).to_bytes(1, "little")
            payload += int(blue).to_bytes(1, "little")
            self.write(payload)
            return
        self.active_keys.append(key)

    def on_release(self, key):
        """Callback called on each keyboard key release event."""
        if key not in self.active_keys:
            return
        self.active_keys.remove(key)

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

    def start(self):
        """Starts to continuously listen on keyboard key press/release events."""
        self.listener.start()
        while 1:
            left_speed, right_speed = self.speeds_from_keys()
            payload = bytearray()
            payload += PROTOCOL_VERSION.to_bytes(1, "little")
            payload += int(Command.MOVE_RAW.value).to_bytes(1, "little")
            payload += (0).to_bytes(1, "little", signed=True)
            payload += int(left_speed).to_bytes(1, "little", signed=True)
            payload += (0).to_bytes(1, "little", signed=True)
            payload += int(right_speed).to_bytes(1, "little", signed=True)
            self.write(payload)
            time.sleep(0.05)
