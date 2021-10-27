import logging
import serial
import serial.tools.list_ports
from serial.serialutil import SerialException
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


class DotBot:
    def __init__(self, mac, id):
        self.mac = mac
        self.internal_id = id   
        self.last_update = None
        self.location = None

class Gateway(metaclass=Singleton):
    # Response types
    ACK = '\x31'
    NDB = '\x32'
    RDB = '\x33'
    NOT = '\x34'
    CON = '\x01'

    # Request types
    START = '\x00\x00\x00'
    TWIST = '\x30'

    class _Decorators:
        @classmethod
        def _command_decorator(cls, command):
            def command_wrapper(self, *args):
                try:
                    if self.dk_connected:
                        with self.command_lock:
                            return command(self, *args)
                    else:
                        return False
                
                except serial.SerialTimeoutException:
                    return False
            return command_wrapper

    def __init__(self, port=None, baud=115200):
        self.port = port
        self.baud = baud
        
        self.dk_connected = False
        self.dotbots = {}
        self.conn_timeout = 5
        
        self.command_lock = threading.RLock()
        self.connection_check_daemon = threading.Thread(target=self._check_connection, daemon=True)
        self.ser = SerialportHandler(port, baudrate=baud) # this may failed if USB not connected, is a problem?
        
        self.connect()
        self.connection_check_daemon.start()

    def connect(self):
        with self.command_lock:
            # wait for the port to appears in the available ports list
            i = 0
            while not self.port in self._get_ports():
                if i % 10 == 0: # every 5 seconds print a warning
                    log.warning(f"Connecting DK port, waiting for port '{self.port}'... ")
                    i = 0
                i = i + 1
                time.sleep(0.5)

            while not self.dk_connected:
                try:
                    self.open() # open the port
                    log.info(f"Sending START message to DK at port {self.port} ... ")
                    self._write(self.START.encode("utf-8", "little")) # write and START message
                    self.dk_connected = self._wait_conn_msg() # wait for the response of DK
                    time.sleep(0.5)

                except SerialException:
                    log.warning(f"Couldn't connect to DK at port {self.port}. Retrying ... ")

    def open(self):
        if self.ser.is_open():
            log.warning("Port already open, quitting.")
            return
        self.ser.open()

    def close(self):
        if not self.ser.is_open():
            log.warning("Port already closed, quitting.")
            return
        self.ser.close()

    def _get_ports(self):
        return  [tuple(p)[0] for p in list(serial.tools.list_ports.grep("JLink"))]

    def _wait_conn_msg(self):
        conn_msg = self._read(timeout=self.conn_timeout)
        
        if conn_msg and conn_msg[0] == self.CON:
            dotbots_len = int((len(conn_msg) - 1 ) / 7)
            log.info(f"DK connected successfully:  Dotbots connected {dotbots_len}")
            
            for i in range(dotbots_len):
                dot_index = 1 + i * 7
                dotbot_dk_id = ord(conn_msg[dot_index])
                dotbot_mac = ':'.join([f'{ord(i):02X}' for i in conn_msg[dot_index+1: dot_index + 7]]) # this may should be replaced by struct.unpacked
                self.dotbots[dotbot_mac] = DotBot(dotbot_mac, dotbot_dk_id)
                log.info(f"DotBot Connected - id: {dotbot_dk_id} - mac: {dotbot_mac} ")
            return True

        else:
            log.error(f"DK at port {self.port} didn't respond to START message")
            return False

    def _check_connection(self):
        while True:
            while self.port in self._get_ports():
                time.sleep(3) # sleep 3 seconds then check again
            
            self.dk_connected = False
            log.warning("DK disconnected, trying to connect again... ")
            self._reconnect()
            time.sleep(3)

    def _reconnect(self):
        self.ser.ser.reset_input_buffer()
        self.ser.ser.reset_output_buffer()
        self.close()
        self.dotbots = {}
        self.connect()
        return True 

    def _write(self, command):
        if not self.ser.is_open():
            log.warning("Port closed, quitting.")
            return False

        try:
            self.ser.write(command)
        
        except serial.SerialTimeoutException:
            log.warning(f"SerialTimeout! Couldn't write command {command}")
            return False

        log.info(f"Write command: {command}")
        
        return True

    def _read(self, timeout=0):
        if not self.ser.is_open():
            log.warning("Port closed, quitting.")
            return None
        
        original_timeout = self.ser.ser.timeout
        self.ser.ser.timeout = timeout
        
        msg = self.ser.read_frame()
        
        self.ser.ser.timeout = original_timeout
        return msg

    def _wait_ack(self, timeout=0):
        return self._read(timeout=timeout) == self.ACK

    @_Decorators._command_decorator
    def command_move(self, linear, angular, id="0"):
        if not id in self.dotbots:
            log.info(f"Can't move Dotbot {id}: not connected")
            return False
            
        serial_cmd = Gateway.compute_pwm(linear, angular)

        id = self.get_dotbot_id(id)
        wrote = self._write( b'\x01' + id.to_bytes(1, "little") + serial_cmd)

        log.info(f"Twist request to dotbot {id}")
        return self._wait_ack(1) if wrote else False

    @_Decorators._command_decorator
    def command_led(self, switch, color, id="0"): # TODO: blink option for specific id
        # with self.command_lock:
        pass # TODO: implement - send command to gateway with fix size header

    def get_status(self, id="0"):
        with self.command_lock:
            return self._read() # TODO: implement - send command to gateway with fix size header

    def continuous_status_read(self, id="0"):
        while True:
            with self.command_lock:
                result = self._read()

                if result:
                    self.parse_message(result)
            
            time.sleep(0.5)


    def parse_message(self, msg):
    
        if not len(msg) > 0: return

        msg_type = msg[0]
        
        if msg_type == self.ACK:
            log.info("ACK received")

        if msg_type == self.NOT and msg[1] == '\x00':
            for i in range(2, len(msg), 7):
                dotbot_mac = ':'.join([f'{ord(i):02X}' for i in msg[(i+6):i:-1]])
                dotbot_dk_id = ord(msg[i])
                self.dotbots[dotbot_mac] = DotBot(dotbot_mac, dotbot_dk_id)
                log.info(f"DotBot Connected - mac: {dotbot_mac} id: {dotbot_dk_id}")
        
        elif msg_type == self.NDB or msg_type == self.RDB:
            dotbot_mac = ':'.join([f'{ord(i):02X}' for i in msg[2:]])
            dotbot_dk_id = ord(msg[1])
        
            if msg_type == self.NDB:
                self.dotbots[dotbot_mac] = DotBot(dotbot_mac, dotbot_dk_id)
                log.info(f"DotBot Connected - mac: {dotbot_mac} id: {dotbot_dk_id}")
            
            else:
                if dotbot_mac in self.dotbots:
                    del self.dotbots[dotbot_mac]
                log.info(f"DotBot Disconnected - mac: {dotbot_mac} id: {dotbot_dk_id}")

    def get_dotbots(self):
        return list(self.dotbots.keys())

    def get_dotbot_id(self, mac):
        return self.dotbots[mac].internal_id

    @staticmethod
    def compute_pwm(linear, angular, version="v2", max_pwm=100):

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
            pwm_struct = b''.join([struct.pack("<H", pwm16) for pwm16 in pwmL + pwmR])

            return pwm_struct # TODO: add header with ID
