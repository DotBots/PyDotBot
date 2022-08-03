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
    NORMAL = 84
    BOOST = 100
    SUPERBOOST = 127


def rgb_from_key(key):
    if key == "r":
        return 255, 0, 0
    elif key == "g":
        return 0, 255, 0
    elif key == "b":
        return 0, 0, 255
    elif key == "y":
        return 255, 255, 0
    elif key == "p":
        return 255, 0, 255
    elif key == "w":
        return 255, 255, 255
    else:  # n
        return 0, 0, 0


class KeyboardController(ControllerBase):

    def init(self):
        self.active_keys = []
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)

    def on_press(self, key):
        if key in self.active_keys:
            return
        if hasattr(key, "char") and key.char in COLOR_KEYS:
            r, g, b = rgb_from_key(key.char)
            payload = bytearray()
            payload += PROTOCOL_VERSION.to_bytes(1, 'little')
            payload += int(Command.RGB_LED.value).to_bytes(1, 'little')
            payload += int(r).to_bytes(1, 'little')
            payload += int(g).to_bytes(1, 'little')
            payload += int(b).to_bytes(1, 'little')
            self.write(payload)
            return
        self.active_keys.append(key)

    def on_release(self, key):
        if key not in self.active_keys:
            return
        self.active_keys.remove(key)

    def speeds_from_keys(self):
        if any(key in self.active_keys for key in DIR_KEYS):
            speed = MotorSpeeds.NORMAL
            if keyboard.Key.ctrl in self.active_keys:
                speed = MotorSpeeds.BOOST
                if keyboard.Key.alt in self.active_keys:
                    speed = MotorSpeeds.SUPERBOOST
            if keyboard.Key.up in self.active_keys and keyboard.Key.left in self.active_keys:
                return speed.value * 0.75, speed.value
            elif keyboard.Key.up in self.active_keys and keyboard.Key.right in self.active_keys:
                return speed.value, speed.value * 0.75
            elif keyboard.Key.down in self.active_keys and keyboard.Key.left in self.active_keys:
                return -speed.value * 0.75, -speed.value
            elif keyboard.Key.down in self.active_keys and keyboard.Key.right in self.active_keys:
                return -speed.value, -speed.value * 0.75
            elif keyboard.Key.up in self.active_keys:
                return speed.value, speed.value
            elif keyboard.Key.down in self.active_keys:
                return -speed.value, -speed.value
            elif keyboard.Key.left in self.active_keys:
                return 0, speed.value
            elif keyboard.Key.right in self.active_keys:
                return speed.value, 0
        return 0, 0

    def start(self):
        self.listener.start()
        while 1:
            left_speed, right_speed = self.speeds_from_keys()
            payload = bytearray()
            payload += PROTOCOL_VERSION.to_bytes(1, 'little')
            payload += int(Command.MOVE_RAW.value).to_bytes(1, 'little')
            payload += (0).to_bytes(1, 'little', signed=True)
            payload += int(left_speed).to_bytes(1, 'little', signed=True)
            payload += (0).to_bytes(1, 'little', signed=True)
            payload += int(right_speed).to_bytes(1, 'little', signed=True)
            self.write(payload)
            time.sleep(0.05)
