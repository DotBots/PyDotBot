import threading
import time
import logging

logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

class DotBot:
    '''
    A class used to represent a DotBot
    
    ...
    Attributes
    ----------
    mac: str
        mac address of DotBot
    id: int
        GW internal id of DotBot
    last_location_update: int
        Last location update timestamp
    location:
        Last computed location
    last_command_ts: int
        Last sent command timestamp
    led_color: str
        Current color of LED
    command_rate: float
        rate at which the DotBot can accept command
    ack_code: int
        Code associated to the last command sent, DotBot is waiting for this ack.

    Methods
    -------
    wait_ack(ack_code, timeout=5)
        Waits to receive an ack. Blocks new commands until ack is received or timeout is reached.

    receive_ack(ack_code)
        Receive an ack.
    
    is_ready()
        Return True if the DotBot is ready to receive a new command, False if still waiting for an ack.

    '''
    def __init__(self, mac, id, command_rate=2):
        self.mac = mac
        self.internal_id = id   

        self.last_location_update = None
        self.location = None

        self.led_color = ""
        self.last_command_ts = time.time()
        self.command_rate = command_rate
        self.ack_code = None
        self.ack_sem = threading.Semaphore(value=0)

    def wait_ack(self, ack_code, timeout=5.):
        '''
        Waits to receive certain ack_code. 
        This blocks until an acknowledgment for the last command sent is received 
        or until timeout is reached. An ack is received using the method receive_ack (called by the GW).

        Parameters
        -----------
        ack_code: int
            code to wait
        timeout: num
            Max time in seconds to wait for the ack

        Returns
        -------
        bool
            True if the ack is received, False if the timeout is reached.
        '''

        self.last_command_ts = time.time()
        self.ack_code = ack_code
        
        ack = self.ack_sem.acquire(blocking=True, timeout=timeout)        
        self.ack_code = None
        return ack
    

    def receive_ack(self, ack_code):
        '''
        Receive an ack. If the DotBot is currently waiting for it, it releases the semaphore blocking the wait method.
        
        Parameters
        -----------
        ack_code: int
            code received
        '''
        if self.ack_code == ack_code:
            self.ack_sem.release()
        

    def is_ready(self):
        '''
        Method to check if the DotBot is ready to receive a new command

        Returns
        -------
        bool
            False if the DotBot is currently waiting for an ack, or to guarantee that the max command rate is not broken.
        '''
        # control '
        if self.ack_code is None and time.time() - self.last_command_ts  > 1.0 / self.command_rate:
            return True
        else:
            log.debug(f"Not ready yet, waiting {self.ack_code}")
            return False
    