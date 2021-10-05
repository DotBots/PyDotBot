import threading
import queue
import serial
import time


import logging
import logging.handlers
import sys
import traceback
import struct

import dotbot.orchestrator.openhdlc.openhdlc as openhdlc
from  dotbot.orchestrator.openhdlc.utils import format_buf, format_string_buf, format_critical_message, format_crash_message

LOGFILE_NAME = 'test_hdlc.log'

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class NoData(Exception):
    pass


class SerialportHandler:
    '''
    Connects to serial port. Puts received serial bytes in queue. Method to send bytes.
    Can be started/stopped many times (used when reprogramming).
    '''
    XOFF = 0x13
    XON = 0x11
    XONXOFF_ESCAPE = 0x12
    XONXOFF_MASK = 0x10


    def __init__(self, serialport, baudrate):

        super(SerialportHandler, self).__init__()
        
        # store params
        self._port = serialport
        self._baudrate = baudrate
        self.ser = serial.Serial(self._port, baudrate=self._baudrate, timeout=0, write_timeout=1.0)

        # local variables
        self.rxqueue = queue.Queue()
        self.serial_handler = None
        self.go_on = True
        self.please_connect = False
        self.connected = False
        
        # self.connectLock = threading.RLock()        
        # self.dataLock = threading.RLock()

        self.name = 'SerialportHandler@{0}'.format(self._port)
        # self.logger = logging.getLogger(self.name)
        # self.start()
      
        # flag to permit exit from read loop
        self.quit = False
        # to be assigned, callback
        self.send_to_parser = None

        # frame parsing variables
        self.rx_buf = ''
        self.hdlc_flag = False
        self.receiving = False
        self.xonxoff_escaping = False

        self.connected = False
        self.hdlc = openhdlc.OpenHdlc()

        # initialize thread
        self.name = 'DKSerial@' + str(self._port)


    # ======================== public ==========================================
    
    def is_open(self):
        return self.ser.is_open

    def open(self):
        if not self.ser.is_open:
            self.ser.open()
        self.connected = True
    
    def close(self):
        if self.ser.is_open:
            self.ser.close()
        self.connected = False

    def write(self, data):
 
        if not self.connected:
            self.open()

        hdlc_data = self.hdlc.hdlcify(data)
        self.ser.flush()
        self.ser.write(hdlc_data)


    def read_frame(self):

        self.read = True
        self.rx_buf = b""
        
        while self.read:
            try:
                byterx = self._rcv_data(1)
                self._parse_bytes(byterx)    
            except openhdlc.HdlcException as err:
                log.warning('{}: invalid serial frame: {} {}'.format(self.name, format_string_buf(self.rx_buf), err))
                return None

            except NoData:
                self.read = False
            
        return self.rx_buf


    def _rcv_data(self, rx_bytes=1):
        data = self.ser.read(rx_bytes)
        if data == b"":
            raise NoData
        else:
            return data
            
    def _parse_bytes(self, octets):
        """ Parses bytes received from serial pipe """
        for byte in octets:
            if not self.receiving:
                if self.hdlc_flag and byte != self.hdlc.HDLC_FLAG:
                    # start of frame
                    if log.isEnabledFor(logging.DEBUG):
                        log.debug("%s: start of HDLC frame %s %s",
                                  self.name,
                                  format_string_buf(self.hdlc.HDLC_FLAG),
                                  format_string_buf(chr(byte)),
                                  )

                    self.receiving = True
                    
                    # discard received self.hdlc_flag
                    self.hdlc_flag = False
                    self.xonxoff_escaping = False
                    self.rx_buf = self.hdlc.HDLC_FLAG
                    self._rx_buf_add(byte)
                
                elif byte == ord(self.hdlc.HDLC_FLAG):
                    # received hdlc flag
                    log.debug("Input - start of hdlc frame")
                    self.hdlc_flag = True
                else:
                    # everything thats is not wrapped in a frame is garbage
                    # drop garbage
                    pass
            else:
                if byte != ord(self.hdlc.HDLC_FLAG):
                    # middle of frame
                    self._rx_buf_add(byte)
                
                else:
                    # end of frame, received self.hdlc_flag
                    if log.isEnabledFor(logging.DEBUG):
                        log.debug("{}: end of hdlc frame {}".format(self.name, format_string_buf(chr(byte))))

                    self.hdlc_flag = True
                    self.receiving = False
                    self.read = False
                    self._rx_buf_add(byte)
                    valid_frame = self._handle_frame()

                    if valid_frame:
                        # discard valid frame self.hdlc_flag
                        self.hdlc_flag = False

    def _handle_frame(self):
        """ Handles a HDLC frame """
        valid_frame = False
        temp_buf = self.rx_buf
        frame = ""

        try:
            self.rx_buf = self.hdlc.dehdlcify(self.rx_buf)

            if log.isEnabledFor(logging.DEBUG):
                log.debug("{}: {} dehdlcized input: {}".format(
                    self.name,
                    format_string_buf(temp_buf),
                    format_string_buf(self.rx_buf)))

            if self.send_to_parser:
                self.send_to_parser([ord(c) for c in self.rx_buf])

            valid_frame = True

        except openhdlc.HdlcException as err:
            log.warning('{}: invalid serial frame: {} {}'.format(self.name, format_string_buf(temp_buf), err))

        return valid_frame

    def _rx_buf_add(self, byte):
        """ Adds byte to buffer and escapes the XONXOFF bytes """
        if byte == chr(self.XONXOFF_ESCAPE):
            self.xonxoff_escaping = True
        else:
            if self.xonxoff_escaping is True:
                self.rx_buf += chr(ord(byte) ^ self.XONXOFF_MASK)
                self.xonxoff_escaping = False
            elif byte != chr(self.XON) and byte != chr(self.XOFF):
                self.rx_buf += chr(byte)
