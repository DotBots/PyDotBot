import serial
import shutil
import struct
import os
import time
import numpy as np

# TODO: use logger instead of print statements

class Gateway:

    def __init__(self, port="COM4", baud=115200, open=True):
        self.ser = serial.Serial(port, baudrate=baud)
        if open:
            self.open()

    def open(self):
        if self.ser.isOpen():
            print("Port already open, quitting.") # TODO: logger warning
            return
        self.ser.open()

    def close(self):
        if not self.ser.isOpen():
            print("Port already closed, quitting.") # TODO: logger warning
            return
        self.ser.close()

    def dotbot_serial(self, command):
        if not self.ser.isOpen():
            print("Port closed, quitting.") # TODO: logger warning
            return False
        self.ser.write(command) # TODO: check if write is successful (also ack from dotbot)

        return True

    @staticmethod
    def translate_cmd_vel(linear, angular, version="v2", max_pwm=100):
        """
        :param linear:
        :param angular:
        :return:
        """
        if version == "v1": # Discrete control
            conversion_map = [
                # W, 0, E
                [7, 2, 6], # S
                [3, 0, 4], # 0
                [8, 1, 5], # N
            ]

            lin_idx, ang_idx = np.sign(linear) + 1, np.sign(angular) + 1

            return conversion_map[lin_idx][ang_idx]
        elif version == "v2": # Continuous PWM control (range 0 to 100) or 127?
            # Compute PWM inputs
            mag_vec = np.array([linear - angular, linear + angular])
            mag_max = max(abs(mag_vec.min()), abs(mag_vec.max()))
            mag_vec /= max(1, mag_max)

            L, R = max_pwm * mag_vec

            pwmL, pwmR = [0, 0], [0, 0] # 2 channel PWM (https://www.ti.com/lit/ds/symlink/drv8833.pdf)
            pwmL[int(L < 0)] = int(abs(L))
            pwmR[int(-R < 0)] = int(abs(R))

            print(pwmL, pwmR)

            # Pack into struct
            pwm_struct = b''.join([struct.pack("<H", pwm16) for pwm16 in pwmL + pwmR])

            return pwm_struct

    def command_move(self, linear, angular):
        serial_cmd = Gateway.translate_cmd_vel(linear, angular)
        print(serial_cmd)
        return self.dotbot_serial(serial_cmd)

    def command_led(self, switch, color):
        pass

