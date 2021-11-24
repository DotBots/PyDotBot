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
import sys 

from dotbot.datastructures import Singleton
from dotbot.orchestrator.openhdlc.openserial import SerialportHandler
from dotbot.orchestrator.dotbot import DotBot
# TODO: use logger instead of print statements
logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

class Gateway(metaclass=Singleton):
    '''
    This class is used to represent the Gateway/Orchestrator connection. 

    The main task of this class is to keep track of the connected DotBots and bidirectional communicate with them 
    through the DK Gateway (through serial connection). 
    
    It's a singleton class, multiple instances in the same process are the same instance (even in different threads).
    This is a way of keeping this instance consistent in the different threads of a flask server.

    '''
    # Response types
    ACK_0 = 0x30
    ACK = 0x31
    NDB = 0x32
    RDB = 0x33
    NOT = 0x34
    CON = 0x01

    # Request types
    START = (0x00, 0x00, 0x00)
    TWIST = 0x30

    _MAX_ACK = 2 ** ( 8 * struct.calcsize("H"))

    class _Decorators:
        '''
        This class contains decorators associated to the Gateway Class

        '''
        @classmethod
        def _command_decorator(cls, command):
            '''
            Decorator to command request to Gateway. 
            This decorator assure that the dotbot to whom the command is target is connected. 
            Also to create the ack code and wait for the acknowledgment.
            '''
            def command_wrapper(self, *args, **kwargs):
                '''
                This wraps commands, commands return False if it fails to be delivered, True otherwise.
                '''
                
                try:
                    if self.dk_connected:
                        dot_id = kwargs.pop("id")

                        if not dot_id in self.dotbots:
                            log.warning(f"Can't command Dotbot [{dot_id}] not connected")
                            return False
                        dot = self.dotbots[dot_id]
                        if dot.is_ready():
                            log.debug("waiting for lock to write ..... ")
                            with self.command_lock:
                                ack_code = self._get_ack_code()
                                cmd = command(self, **kwargs, dotbot=dot, ack_code=ack_code)
                                self._write(cmd)
                            return dot.wait_ack(ack_code)
                        else:
                            return False
                    else:
                        return False
                
                except serial.SerialTimeoutException:
                    return False
            return command_wrapper

    def __init__(self, port=None, baud=115200):
        '''
        Parameters
        ----------

        port: str
            SerialPort to connect. If None or if the default port is not available it will search
            for any available port with a connected DK
        baud: int
            Baudrate to use
        '''

        self.port = port
        self.baud = baud
        
        # Dotbots Vars
        self.dk_connected = False
        self.dotbots = {}
        self.dotbots_mac = {}
        self.conn_timeout = 5
        
        self.command_lock = threading.RLock()
        self.connection_check_daemon = threading.Thread(target=self._check_connection, daemon=True)

        ports = self._get_ports()
        if not self.port in ports:
            if len(ports) > 0:
                log.warning(f"Default Port {self.port} is not available but we will try using {ports[0]} ... ")
                self.port = ports[0]
            else:
                log.error(f"Default Port {self.port} is not available and there isn't another candidate. Check if DK is connected and relaunch.  Quitting...")
                sys.exit(-1)
        
        self.ser = SerialportHandler(self.port, baudrate=self.baud) # this may failed if USB not connected, is a problem?
        
        self.connect()
        self.connection_check_daemon.start()
        self._ack_code = 300

    def connect(self):
        '''
        Method to connect to a DK-Gateway. 
        It waits to the port to be available and then open a serial connection to it,
        once the connection is open, it sends a START message to initialize the DK and to get 
        the already connected DotBots. 
        '''

        with self.command_lock:
            while not self.dk_connected:
                i = 0
                # wait for the port to appears in the available ports list
                while not self.port in self._get_ports():
                    if i % 10 == 0: # every 5 seconds print a warning
                        log.warning(f"Connecting DK, waiting for port '{self.port}'... \n")
                        i = 0
                    i = i + 1
                    time.sleep(0.5)

                # when the port is available try to connect, sending a START msg
                try:
                    if self.ser.is_open():
                        self.close()

                    self.open() # open the port
                    log.info(f"Sending START message to DK at port {self.port} ... ")
                    self._write(self.START) # write and START message
                    self.dk_connected = self._wait_conn_msg() # wait for the response of DK

                except (SerialException, serial.SerialTimeoutException):
                    pass

                finally:
                    if not self.dk_connected:
                        time.sleep(0.5)
                        log.warning(f"Couldn't connect to DK at port {self.port}. Retrying ... \n")

    def open(self):
        '''
        Open the serial connection
        '''

        if self.ser.is_open():
            log.warning("Port already open, quitting.")
            return
        self.ser.open()

    def close(self):
        '''
        Close the serial connection
        '''
        if not self.ser.is_open():
            log.warning("Port already closed, quitting.")
            return
        self.ser.close()

    def _get_ports(self):
        '''
        Get the ports where an DK is connected.
        Note: This is specific to JLink DK.
        '''
        return [tuple(p)[0] for p in list(serial.tools.list_ports.grep("JLink"))]

    def _wait_conn_msg(self):
        '''
        This method waits for the START connection message response.
        Once the message arrives, it adds the connected DotBots to the list of DotBots and then response True.
        It waits until self.conn_timeout is reached, in which case it responds False.

        Returns
        -------
        bool
            True if the connection message is received, False if timeout is reached.
        '''
        conn_msg = self._read(timeout=self.conn_timeout)
        
        if conn_msg and conn_msg[0] == self.CON:
            dotbots_len = int((len(conn_msg) - 1 ) / 7)
            log.info(f"DK connected successfully:  Dotbots connected {dotbots_len}")
            
            for i in range(dotbots_len):
                dot_index = 1 + i * 7
                dotbot_dk_id = conn_msg[dot_index]
                dotbot_mac = ':'.join([f'{i:02X}' for i in conn_msg[dot_index+1: dot_index + 7]]) # this may should be replaced by struct.unpacked
                
                self.dotbots[dotbot_mac] = DotBot(dotbot_mac, dotbot_dk_id)
                self.dotbots_mac[dotbot_dk_id] = dotbot_mac
                
                log.info(f"DotBot Connected - mac: {dotbot_mac} - id: {dotbot_dk_id}")
            return True

        else:
            log.warning(f"DK at port {self.port} didn't respond to START message")
            return False

    def _check_connection(self):
        '''
        Check if the DK is still connected.
        This method is supposed to run as a Daemon, periodically checking if the connection has been dropped.
        If so, it tries to reconnect. 
        '''
        while True:
            while self.port in self._get_ports():
                time.sleep(3) # sleep 3 seconds then check again
            
            self.dk_connected = False
            log.warning("DK disconnected, trying to connect again... ")
            self._reconnect()
            time.sleep(3)

    def _reconnect(self):
        '''
        Reconnect to DK.
        Close the serial port, clean the buffers and try to connect again. 
        '''

        self.ser.ser.reset_input_buffer()
        self.ser.ser.reset_output_buffer()
        self.close()
        # should destroy and recreate the SerialPortHandler (?)

        self.dotbots = {}
        self.dotbots_mac = {}
        self.connect()

    def _write(self, command):
        '''
        Write to the serial connection

        Parameters
        ----------
        command: bytearray
            Command to be written

        Returns
        -------
        bool
            True if the command was written, False otherwise.
        '''

        if not self.ser.is_open():
            log.warning("Port closed, quitting.")
            return False

        try:
            self.ser.write(command)
        
        except serial.SerialTimeoutException:
            log.warning(f"SerialTimeout! Couldn't write command {command}")
            raise

        log.info(f"Write command: {command}")
        return True

    def _read(self, timeout=0):
        '''
        Reads/wait for message from the serial connection (DK)

        Parameters
        ----------
        timeout: number
            Timeout to wait for a message

        Returns
        -------
        list
            a list of ints containing the incoming msg
        '''

        if not self.ser.is_open():
            log.warning("Port closed, quitting.")
            return None
        msg = self.ser.read_frame(timeout=timeout)
        return msg

    # def _wait_ack(self, timeout=0):
    #     ack =  self._read(timeout=timeout)
    #     return len(ack) == 1 and ack[0] == self.ACK

    @_Decorators._command_decorator
    def command_move(self, linear, angular, dotbot, ack_code):
        '''
        Sends a move command to certain dotbot

        Parameters
        ----------
        linear: float
            linear velocity.
        angular: float
            angular velocity.
        dotbot: DotBot
            DotBot to command.
        ack_code: int
            acknowledgment code of the command.

        Return
        ------
        bytearray
            Bytearray containing the encoded command.
        '''
        payload = Gateway.compute_pwm(linear, angular)
        log.info(f"Twist request to dotbot ({dotbot.internal_id}) {dotbot.mac}")
        return struct.pack("<BBH", 0x1, dotbot.internal_id, ack_code) + payload

    @_Decorators._command_decorator
    def command_led(self, color, dotbot, ack_code):
        '''
        Parameters
        ----------
        color: tuple 
            3 unsigned char (0-255) representing a color in RGB model.
        dotbot: DotBot
            DotBot to command.
        ack_code: int
            acknowledgment code of the command.
        
        Return
        ------
        bytearray
            Bytearray containing the encoded command.
        '''
        payload = b''.join([struct.pack("<B", x) for x in [color[0], color[1], color[2]]])
        log.info(f"LED request to dotbot ({dotbot.internal_id}) {dotbot.mac}  - color: {[color[0], color[1], color[2]]}")
        return struct.pack("<BBH", 0x2, dotbot.internal_id, ack_code) + payload

    def continuous_status_read(self):
        '''
        This method continuously waits for messages from the DK.
        This method is supposed to run as a Daemon, continuously reading the serial connection to then process new messages from the DK.
        '''
        while True:
            with self.command_lock:
                result = self._read()

                if result:
                    self.parse_message(result)
            
            time.sleep(0.5)

    def parse_message(self, msg):
        '''
        This method parse messages that are received from the DK. 
        It checks the type of message and parse it accordinly. 
        Message can be acknowledgments or notifications of  dotbot connected or disconnected.

        Parameters
        ----------
        msg: list of ints
            msg to be parsed
        '''
    
        if not len(msg) > 0: return

        msg_type = msg[0]
        
        if msg_type == self.ACK or msg_type == self.ACK_0:
            dotbot_dk_id = msg[1]
            ack_code = struct.unpack("<H", bytes(msg[2:]))[0]
            dot = self.dotbots[self.dotbots_mac[dotbot_dk_id]]
            log.info(f"[{'FAIL' if msg_type == self.ACK_0 else 'OK'}] ACK received id:{dotbot_dk_id} code: {ack_code}")
            dot.receive_ack(ack_code)

        if msg_type == self.NDB or msg_type == self.RDB:
            dotbot_mac = ':'.join([f'{i:02X}' for i in msg[2:]])
            dotbot_dk_id = msg[1]

            if msg_type == self.NDB:
                for (mac, dot) in list(self.dotbots.items()):
                    if mac == dotbot_mac:
                        del self.dotbots_mac[dot.internal_id]
                        del self.dotbots[dotbot_mac] # delete the last instance of this dotbot
                    
                    elif dot.internal_id == dotbot_dk_id: # there is another dotbot using the internal id
                        log.warning(f"DotBot {mac} has the same internal id, removing it from DotBot list")
                        del self.dotbots_mac[dot.internal_id]
                        del self.dotbots[mac]
                
                self.dotbots[dotbot_mac] = DotBot(dotbot_mac, dotbot_dk_id) # add new dot
                self.dotbots_mac[dotbot_dk_id] = dotbot_mac
                log.info(f"DotBot Connected - mac: {dotbot_mac} id: {dotbot_dk_id}")

            else:
                if dotbot_mac in self.dotbots:
                    del self.dotbots_mac[self.dotbots[dotbot_mac].internal_id]
                    del self.dotbots[dotbot_mac]

                log.info(f"DotBot Disconnected - mac: {dotbot_mac} id: {dotbot_dk_id}")

    @staticmethod
    def compute_pwm(linear, angular, max_pwm=100):
        '''
        This aux method computes the pwm commands to both motors of a DotBot, to get certain linear and angular velocity.

        Parameters
        ----------
        linear: float
            linear velocity to be set to the DotBot.

        angular: float
            angular velocity to be set to the DotBot.

        max_pwm: int, optional
            maximum pwm value.

        Returns
        -------
        list
            list of ints containing the pwm commands

        '''

        # Compute PWM inputs
        mag_vec = np.array([linear - angular, linear + angular])
        mag_max = max(abs(mag_vec.min()), abs(mag_vec.max()))
        mag_vec /= max(1, mag_max)

        L, R = max_pwm * mag_vec

        pwmL, pwmR = [0, 0], [0, 0]  # 2 channel PWM (https://www.ti.com/lit/ds/symlink/drv8833.pdf)
        pwmL[int(L < 0)] = int(abs(L))
        pwmR[int(R < 0)] = int(abs(R))

        # print(pwmL, pwmR)

        # Pack into struct
        pwm_struct = b''.join([struct.pack("<H", pwm16) for pwm16 in pwmL + pwmR])

        return pwm_struct # TODO: add header with ID

    def _get_ack_code(self):
        '''
        Get an acknowledgement code to the next command.
        It simply adds 1 to the last ack code, but ensuring that the MAX_ACK is not broken.

        Returns
        -------
        int
            ACK code.

        '''
        self._ack_code =  int((self._ack_code + 1) % self._MAX_ACK) 
        return self._ack_code

    def get_dotbots(self):
        '''
        Returns a list of the current connected dotbots

        Returns
        -------
        list
            List of MAC of connected DotBots
        '''
        return list(self.dotbots.keys())

    def get_dotbot_id(self, mac):
        '''
        Get the internal id of a certain Dotbot by its mac

        Parameters
        ----------
        mac: array of ints
            mac of the dotbot

        Return
        ------
        int
            Internal ID of the requested DotBot

        '''
        return self.dotbots[mac].internal_id