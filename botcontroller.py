import base64
import requests
import pygame
import os
from enum import Enum
import struct
import numpy as np
from bottle import route, run, template, Bottle


DOTBOT_GATEWAY_URL = os.getenv("DOTBOT_GATEWAY_URL", "http://localhost:8080/dotbot")
ACTIVE_KEYS = []


class Command(Enum):
    MOVE_RAW = 0
    RGB_LED = 1


def parse_speeds():
    left_joystick_y = speeds_from_keys()[0]
    right_joystick_x = speeds_from_keys()[1]
    payload = bytearray()                                                   # init payload
    payload += (0).to_bytes(1, 'little')                                    # version 0
    payload += int(Command.MOVE_RAW.value).to_bytes(1, 'little')            # command type (move)
    payload += (0).to_bytes(1, 'little', signed=True)                       # left_x = 0
    payload += int(left_joystick_y).to_bytes(1, 'little', signed=True)      # left_y
    payload += int(right_joystick_x).to_bytes(1, 'little', signed=True)     # right_x
    payload += (0).to_bytes(1, 'little', signed=True)                       # right_y = 0
    send_payload(payload)                                                   # send payload


def send_payload(payload):
    payload_encoded = base64.b64encode(payload).decode()
    command = {"cmd": payload_encoded}
    requests.post(DOTBOT_GATEWAY_URL, json=command)


def speeds_from_keys():
    pygame.event.pump()
    lj_y = ps4.get_axis(1) * 128
    rj_x = ps4.get_axis(2) * 128
    if -0.09 < lj_y <= 0.09:
        lj_y = 0.0
    if -0.09 < rj_x <= 0.09:
        rj_x = 0.0

    return lj_y, rj_x


if __name__ == "__main__":
    pygame.init()
    pygame.joystick.init()
    joystick_count = pygame.joystick.get_count()
    ps4 = pygame.joystick.Joystick(0)
    ps4.init()
    axes = ps4.get_numaxes()

    while True:
        parse_speeds()

