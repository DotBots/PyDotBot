import base64
from enum import Enum
import os
import pygame
import requests
import time


DOTBOT_GATEWAY_URL = os.getenv("DOTBOT_GATEWAY_URL", "http://127.0.0.1:8080/dotbot")


class Command(Enum):
    MOVE_RAW = 0
    RGB_LED = 1


def parse_speeds(left_joystick_x, left_joystick_y, right_joystick_x, right_joystick_y):
    payload = bytearray()                                                       # init payload
    payload += (0).to_bytes(1, 'little')                                        # version 0
    payload += int(Command.MOVE_RAW.value).to_bytes(1, 'little')                # command type (move)
    payload += int(left_joystick_x).to_bytes(1, 'little', signed=True)          # left_x
    payload += int(left_joystick_y).to_bytes(1, 'little', signed=True)          # left_y
    payload += int(right_joystick_x).to_bytes(1, 'little', signed=True)         # right_x
    payload += int(right_joystick_y).to_bytes(1, 'little', signed=True)         # right_y
    return payload


def send_payload(payload):
    payload_encoded = base64.b64encode(payload).decode()                        # configure the payload
    command = {"cmd": payload_encoded}                                          # configure the command for the payload
    requests.post(DOTBOT_GATEWAY_URL, json=command)                             # send the request over HTTP


def speeds_from_joysticks():
    pygame.event.pump()             # queue needs to be pumped
    lj_x = ps4.get_axis(0)
    lj_y = - ps4.get_axis(1)
    rj_x = ps4.get_axis(2)
    rj_y = - ps4.get_axis(3)

    # dead zones
    if -0.09 < lj_x <= 0.09:
        lj_x = 0.0
    if -0.09 < lj_y <= 0.09:
        lj_y = 0.0
    if -0.09 < rj_x <= 0.09:
        rj_x = 0.0
    if -0.09 < rj_y <= 0.09:
        rj_y = 0.0

    lj_x = lj_x * 127                   # from [-1;1] to [-127;127]
    lj_y = lj_y * 127
    rj_x = rj_x * 127
    rj_y = rj_y * 127
    return lj_x, lj_y, rj_x, rj_y


if __name__ == "__main__":
    pygame.init()
    pygame.joystick.init()
    ps4 = pygame.joystick.Joystick(0)
    ps4.init()
    while True:
        (speed_lj_x, speed_lj_y, speed_rj_x, speed_rj_y) = speeds_from_joysticks()  # fetch positions from joysticks
        payload = parse_speeds(speed_lj_x, speed_lj_y, speed_rj_x, speed_rj_y)      # configure the payload
        send_payload(payload)                                                       # send the payload
        time.sleep(0.05)                                                            # 50ms delay between each update
