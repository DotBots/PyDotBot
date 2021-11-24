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
from  dotbot.orchestrator.openhdlc.utils import format_buf

LOGFILE_NAME = 'test_hdlc.log'
logging.basicConfig(level=logging.INFO, format='%(relativeCreated)6d %(threadName)s %(message)s')
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

class NoData(Exception):
    pass


class SerialportHandler:
    '''
    This class wraps the serial connection. 
    
    Manage connection and disconnection, write and read using HDLC framing. 
    '''
    XOFF = 0x13
    XON = 0x11
    XONXOFF_ESCAPE = 0x12
    XONXOFF_MASK = 0x10


    def __init__(self, serialport, baudrate):
        '''
        
        Parameters
        ----------
        serialport: str
            Port to connect
        baudrate: int
            Baudrate to use

        '''
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

        self.name = 'SerialportHandler@{0}'.format(self._port)
        # flag to permit exit from read loop
        self.quit = False
        # to be assigned, callback
        self.send_to_parser = None

        # frame parsing variables
        self.rx_buf = []
        self.rx_unframed_buf = []

        self.hdlc_flag = False
        self.receiving = False
        self.xonxoff_escaping = False

        self.connected = False
        self.hdlc = openhdlc.OpenHdlc()

        # initialize thread
        self.name = 'DKSerial@' + str(self._port)
    # ======================== public ==========================================
    
    def is_open(self):
        '''
        Checks if serial port is open
        
        Returns
        -------
        bool
            True if port is open, False otherwise
        '''
        return self.ser.is_open

    def open(self):
        '''
        Open the serial port, if is not already open.
        '''

        if not self.ser.is_open:
            self.ser.open()
        self.connected = True
    
    def close(self):
        '''
        Closes the serial port. 
        '''
        if self.ser.is_open:
            self.ser.close()
        self.connected = False

    def write(self, data):
        '''
        Writes data in the serial port, it frames the data using HDLC framing and then write it in the serial port.
        
        Parameters
        ----------
        data: bytes
            Data to be written in the serial port
        
        '''
        if not self.connected:
            self.open()

        data = list(data) # convert bytes to list of int
        hdlc_data = self.hdlc.hdlcify(data) 
        self.ser.flush()
        self.ser.write(hdlc_data)


    def read_frame(self, timeout = None):
        '''
        Read a whole HDLC frame from the serial connection. 
        It reads byte by byte until the whole frame is completed or timeout is reached.

        Parameters
        ----------
        timeout: num
            Timeout time (in seconds)
        '''

        if timeout is not None:
            original_timeout = self.ser.timeout
            self.ser.timeout = timeout

        self.read = True
        self.rx_buf = []
        self.rx_unframed_buf = []
        
        while self.read:
            try:
                byterx = self._rcv_data(1) # TODO: check if we can read more than 1 byte at a time
                self._parse_bytes(byterx)

            except openhdlc.HdlcException as err:
                log.warning('{}: invalid serial frame: {} {}'.format(self.name, self.rx_buf, err))
                return None

            except NoData:
                self.read = False
        
        if timeout is not None:
            self.ser.timeout = original_timeout
        
        return self.rx_unframed_buf


    def _rcv_data(self, rx_bytes=None):
        '''
        Auxiliary method to read certain number of bytes from the serial port.
        
        Parameters
        ----------
        rx_bytes: int
            number of bytes to read.

        Returns
        -------
            data read.

        Raises
        ------
            NoData exception if there is no data to read.
        '''
        data = self.ser.read(rx_bytes) if rx_bytes is not None else self.ser.read()
        if data == b"":
            raise NoData
        else:
            return data
            
    def _parse_bytes(self, octets):
        """ 
        Parses bytes received from serial pipe, add it to a buffer and check what part of the frame it is.
        When a whole frame is completed, call the method _handle_frame() to handle it.
        
        Parameters
        ---------
        octets: bytes
            data received
        """
        for byte in octets:
            if not self.receiving:
                if self.hdlc_flag and byte != self.hdlc.HDLC_FLAG:
                    self.receiving = True                    
                    # discard received self.hdlc_flag
                    self.hdlc_flag = False
                    self.xonxoff_escaping = False
                    self.rx_buf = [self.hdlc.HDLC_FLAG]
                    self._rx_buf_add(byte)
                
                elif byte == self.hdlc.HDLC_FLAG:
                    # received hdlc flag
                    log.debug("Input - start of hdlc frame")
                    self.hdlc_flag = True
                else:
                    # everything thats is not wrapped in a frame is garbage
                    # drop garbage
                    pass
            else:
                if byte != self.hdlc.HDLC_FLAG:
                    # middle of frame
                    self._rx_buf_add(byte)
                
                else:
                    # end of frame, received self.hdlc_flag
                    self.hdlc_flag = True
                    self.receiving = False
                    self.read = False
                    self._rx_buf_add(byte)
                    valid_frame = self._handle_frame()

                    if valid_frame:
                        # discard valid frame self.hdlc_flag
                        self.hdlc_flag = False

    def _handle_frame(self):
        """
        Handles a HDLC frame contained in the rx_unframed_buf attribute. 
        Dehdlcify the frame and check its validity.
        
        Returns
        -------
        The read frame without the hdlc frame.

        Raises
        ------
        HdlcException: If the frame is not valid or complete.
        
        """
        valid_frame = False
        temp_buf = self.rx_buf

        try:
            self.rx_unframed_buf = self.hdlc.dehdlcify(self.rx_buf)

            if log.isEnabledFor(logging.DEBUG):
                log.debug("{}: {} dehdlcized input: {}".format(
                    self.name,
                    format_buf(temp_buf),
                    format_buf(self.rx_buf)))

            valid_frame = True

        except openhdlc.HdlcException as err:
            log.warning('\n{}: invalid serial frame: {}\n{}\n'.format(self.name, format_buf(temp_buf), err))

        return valid_frame

    def _rx_buf_add(self, byte):
        """
        Adds byte to the buffer and escapes the XONXOFF bytes

        Parameters
        ----------
        byte: byte
            Byte to be added to the buffer
        """
        if byte == self.XONXOFF_ESCAPE:
            self.xonxoff_escaping = True
        else:
            if self.xonxoff_escaping is True:
                self.rx_buf += [byte ^ self.XONXOFF_MASK]
                self.xonxoff_escaping = False
            elif byte != self.XON and byte != self.XOFF:
                self.rx_buf += [byte]
