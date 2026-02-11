import math
from dotbot.models import (
    DotBotLH2Position,
)
from dotbot.examples.sct import SCT

class Controller:
    def __init__(self, address: str, path: str):
        self.address = address

        # SCT initialization
        self.sct = SCT(path)
        self.add_callbacks()

        self.waypoint_current = None
        self.waypoint_threshold = 50 # default threshold

        self.led = (0, 0, 0)  # initial LED color
        self.energy = 'high'  # initial energy level 


    def set_work_waypoint(self, waypoint: DotBotLH2Position):
        self.waypoint_work = waypoint


    def set_charge_waypoint(self, waypoint: DotBotLH2Position):
        self.waypoint_charge = waypoint


    def set_current_position(self, position: DotBotLH2Position):
        self.position_current = position


    def control_step(self):

        # Calculate distance to work waypoint
        dx = self.waypoint_work.x - self.position_current.x
        dy = self.waypoint_work.y - self.position_current.y
        self.dist_work = math.sqrt(dx * dx + dy * dy)

        # Calculate distance to charge waypoint
        dx = self.waypoint_charge.x - self.position_current.x
        dy = self.waypoint_charge.y - self.position_current.y
        self.dist_charge = math.sqrt(dx * dx + dy * dy)

        # Run SCT control step
        self.sct.run_step()


    # Register callback functions to the generator player
    def add_callbacks(self):

        # Automatic addition of callbacks
        # 1. Get list of events and list specifying whether an event is controllable or not.
        # 2. For each event, check controllable or not and add callback.

        events, controllability_list = self.sct.get_events()

        for event, index in events.items():
            is_controllable = controllability_list[index]
            stripped_name = event.split('EV_', 1)[1]    # Strip preceding string 'EV_'

            if is_controllable: # Add controllable event
                func_name = '_callback_{0}'.format(stripped_name)
                func = getattr(self, func_name)
                self.sct.add_callback(event, func, None, None)
            else:   # Add uncontrollable event
                func_name = '_check_{0}'.format(stripped_name)
                func = getattr(self, func_name)
                self.sct.add_callback(event, None, func, None)


    # Callback functions (controllable events)
    def _callback_moveToWork(self, data: any):
        # print(f'DotBot {self.address}. ACTION: moveToWork')
        self.waypoint_current = self.waypoint_work
        self.led = (0, 255, 0)  # Green LED when moving to work


    def _callback_moveToCharge(self, data: any):
        # print(f'DotBot {self.address}. ACTION: moveToCharge')
        self.waypoint_current = self.waypoint_charge
        self.led = (255, 0, 0)  # Red LED when moving to charge


    def _callback_work(self, data: any):
        # print(f'DotBot {self.address}. ACTION: work')
        self.energy = 'low'  # After working, energy level goes low


    def _callback_charge(self, data: any):
        # print(f'DotBot {self.address}. ACTION: charge')
        self.energy = 'high'  # After charging, energy level goes high


    # Callback functions (uncontrollable events)
    def _check_atWork(self, data: any):
        if self.dist_work < self.waypoint_threshold:
            # print(f'DotBot {self.address}. EVENT: atWork')
            return True
        return False


    def _check_notAtWork(self, data: any):
        if self.dist_work >= self.waypoint_threshold:
            # print(f'DotBot {self.address}. EVENT: notAtWork')
            return True
        return False


    def _check_atCharger(self, data: any):
        if self.dist_charge < self.waypoint_threshold:
            # print(f'DotBot {self.address}. EVENT: atCharger')
            return True
        return False


    def _check_notAtCharger(self, data: any):
        if self.dist_charge >= self.waypoint_threshold:
            # print(f'DotBot {self.address}. EVENT: notAtCharger')
            return True
        return False


    def _check_lowEnergy(self, data: any):
        if self.energy == 'low':
            # print(f'DotBot {self.address}. EVENT: lowEnergy')
            return True
        return False


    def _check_highEnergy(self, data: any):
        if self.energy == 'high':
            # print(f'DotBot {self.address}. EVENT: highEnergy')
            return True
        return False