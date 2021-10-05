import logging
import serial
import shutil
import struct
import os
import time
import numpy as np
import threading
import multiprocessing as mp

from dotbot.datastructures import Singleton
from dotbot.orchestrator.openhdlc.openserial import SerialportHandler

# TODO: use logger instead of print statements
logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class Gateway(metaclass=Singleton):
    ACK = '\x31'

    def __init__(self, port=None, baud=115200, ack=True):
        self.port = port
        self.baud = baud

        self.ack = ack

        self.command_lock = threading.Lock()
        self.ser = SerialportHandler(port, baudrate=baud)
        self.open()

    def open(self):
        if self.ser.is_open():
            print("Port already open, quitting.") # TODO: logger warning
            return
        self.ser.open()

    def close(self):
        if not self.ser.is_open():
            print("Port already closed, quitting.") # TODO: logger warning
            return
        self.ser.close()

    def _write(self, command):
        if not self.ser.is_open():
            print("Port closed, quitting.") # TODO: logger warning
            return False

        self.ser.write(command)
        log.info(f"write command: {command}")
        
        return True

    def _read(self, timeout=0):
        if not self.ser.is_open():
            print("Port closed, quitting.") # TODO: logger warning
            return None
        
        original_timeout = self.ser.ser.timeout
        self.ser.ser.timeout = timeout
        
        msg = self.ser.read_frame()
        
        self.ser.ser.timeout = original_timeout
        return msg

    def _wait_ack(self, timeout=0):
        return self._read(timeout=timeout)  == self.ACK

    def command_move(self, linear, angular, id="0"): # TODO: incorporate ID and also fixed size header
        with self.command_lock:
            serial_cmd = Gateway.compute_pwm(linear, angular, id=id)
            wrote = self._write(serial_cmd)
            ack = self._wait_ack(1) if (wrote and self.ack) else (not self.ack)
            return ack

    def command_led(self, switch, color, id="0"): # TODO: blink option for specific id
        with self.command_lock:
            pass # TODO: implement - send command to gateway with fix size header

    def get_status(self, id="0"):
        with self.command_lock:
            return self._read() # TODO: implement - send command to gateway with fix size header

    @staticmethod
    def compute_pwm(linear, angular, id="0", version="v2", max_pwm=100):
        """
        :param linear:
        :param angular:
        :return:
        """
        if version == "v1":  # Discrete control
            conversion_map = [
                # W, 0, E
                [7, 2, 6],  # S
                [3, 0, 4],  # 0
                [8, 1, 5],  # N
            ]

            lin_idx, ang_idx = np.sign(linear) + 1, np.sign(angular) + 1

            return conversion_map[lin_idx][ang_idx]
        elif version == "v2":  # Continuous PWM control (range 0 to 100) or 127?
            # Compute PWM inputs
            mag_vec = np.array([linear - angular, linear + angular])
            mag_max = max(abs(mag_vec.min()), abs(mag_vec.max()))
            mag_vec /= max(1, mag_max)

            L, R = max_pwm * mag_vec

            pwmL, pwmR = [0, 0], [0, 0]  # 2 channel PWM (https://www.ti.com/lit/ds/symlink/drv8833.pdf)
            pwmL[int(L < 0)] = int(abs(L))
            pwmR[int(R < 0)] = int(abs(R))

            print(pwmL, pwmR)

            # Pack into struct
            pwm_struct = b'\x01' + b''.join([struct.pack("<H", pwm16) for pwm16 in pwmL + pwmR])

            return pwm_struct # TODO: add header with ID

    def continuous_status_read(self, id="0"):
        while True:
            
            with self.command_lock:
                result = self._read()
                if result:
                    log.info(f"Continous read: {result} - {type(result)}")
                    # rst = result.replace(b'[START][LH]', b'').replace(b'[END][LH]', b'')
                    # print([hex(rst[i+1])[2:] + hex(rst[i])[2:] for i in range(0, len(rst) - 2, 2)])
                    # print([int(hex(rst[i+1])[2:] + hex(rst[i])[2:], 16) for i in range(0, len(rst) - 2, 2)])
            
            time.sleep(0.5)
