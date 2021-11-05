import threading
import time
import logging

logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

class DotBot:
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

    def wait_ack(self, ack_code, timeout=5):
        self.last_command_ts = time.time()
        self.ack_code = ack_code
        
        ack = self.ack_sem.acquire(blocking=True, timeout=timeout)        
        self.ack_code = None
        return ack
    

    def receive_ack(self, ack_code):
        if self.ack_code == ack_code:
            self.ack_sem.release()
        

    def is_ready(self):
        # control '
        if self.ack_code is None and time.time() - self.last_command_ts  > 1.0 / self.command_rate:
            return True
        else:
            log.debug(f"Not ready yet, waiting {self.ack_code}")
            return False
    

        

