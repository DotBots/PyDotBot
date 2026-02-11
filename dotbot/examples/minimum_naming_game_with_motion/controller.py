import math
import random
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
)
from dotbot.examples.sct import SCT
from dotbot.examples.minimum_naming_game_with_motion.walk_avoid import walk_avoid

DISTINCT_COLORS = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Lime
    (0, 0, 255),    # Blue
    (255, 255, 0),  # Yellow
    (255, 0, 255),  # Magenta
    (0, 255, 255),  # Cyan
    (255, 165, 0),  # Orange
    (128, 0, 255),  # Violet
]


class Controller:
    def __init__(self, address: str, path: str, max_speed: float, arena_limits: tuple[float, float]):
        self.address = address
        self.max_speed = max_speed
        self.arena_limits = arena_limits

        self.position = DotBotLH2Position(x=0.0, y=0.0, z=0.0)  # initial position
        self.direction = 0.0  # initial orientation
        self.prev_position: DotBotLH2Position | None = None

        self.neighbors: list[DotBotModel] = []  # initial empty neighbor list
        self.vector = [0.0, 0.0]  # initial movement vector

        # SCT initialization
        self.sct = SCT(path)
        self.add_callbacks()

        self.led = (0, 0, 0)  # initial LED color

        # --- Naming Game Variables ---
        self.counter = 0                       # FOR DEBUGGING
        self.last_broadcast_ticks = 0          # Tracks timing
        self.max_broadcast_ticks = 5 
        
        # Pre-defined words (e.g., num_words = 128)
        self.num_words = 8
        self.words = list(range(self.num_words)) 
        
        # Word reception state
        self.received_word = None
        # self.received_word_checked = True
        self.new_word_received = False
        
        # Global variable for the word chosen for transmission
        self.w_index = 0
        
        # Inventory of known words
        self.inventory = set()


    def control_step(self):

        self.counter += 1  # Increment step counter

        # Run SCT control step
        self.sct.run_step()

        self.color_code()  # Update LED color based on inventory state

        self.vector = walk_avoid(self.position.x, self.position.y, self.direction, self.neighbors, self.max_speed, self.arena_limits)
        # print(f'DotBot {self.address} Walk Vector: {self.vector}')

    def update_pose(self, position: DotBotLH2Position) -> None:
        if self.prev_position is not None:
            dx = position.x - self.prev_position.x
            dy = position.y - self.prev_position.y
            if (dx * dx + dy * dy) > 1e-6:
                heading_rad = math.atan2(dy, -dx)
                self.direction = (math.degrees(heading_rad) + 360.0) % 360.0

        self.prev_position = position
        self.position = position


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
    def _callback_startTimer(self, data: any):
            """
            Saves the current tick count to mark the start of the broadcast interval.
            """
            # print(f'DotBot {self.address}. ACTION: startTimer')
            self.last_broadcast_ticks = self.counter


    def _callback_selectAndBroadcast(self, data: any):
            """
            Selects a random word from the inventory, or invents a new one
            if the inventory is empty. Sets the flag for transmission.
            """
            # print(f'DotBot {self.address}. ACTION: selectAndBroadcast', end=". ")
            
            # Select or Invent a word
            if not self.inventory:
                # Inventory is empty: invent a new word from the pool
                self.w_index = random.randrange(self.num_words)
                # Store the word (equivalent to inventory[0] = words[w_index].data[0])
                self.inventory.add(self.words[self.w_index])
            else:
                # Inventory is not empty: pick a random word from current known words
                self.w_index = random.choice(list(self.inventory))

            # Set broadcast flag for transmission
            self.broadcast_word = True

            # print(f'\tinventory: {self.inventory},\tselected word: {self.w_index}')
            

    def _callback_updateInventory(self, data: any):
            """
            Updates the inventory based on the last received word.
            If the word is known, the agent reaches a local consensus (inventory collapses).
            If unknown, the word is added to the agent's vocabulary.
            """
            # print(f'DotBot {self.address}. ACTION: updateInventory', end=". ")

            # Ensure we have a word to process
            if self.received_word is None:
                return

            # Check if the received word is within the inventory
            if self.received_word in self.inventory:
                # SUCCESS: word is known. 
                # Remove all other words (collapse inventory to just this one)
                self.inventory = {self.received_word}
                # print(f' removed all other words, inventory now: {self.inventory}')
            else:
                # FAILURE: word is unknown.
                # Insert it into the inventory
                self.inventory.add(self.received_word)
                # print(f' added word {self.received_word}, inventory now: {self.inventory}')
            
            # Mark as checked
            self.received_word_checked = True


    # Callback functions (uncontrollable events)
    def _check__selectAndBroadcast(self, data: any) -> bool:
        """
        Checks if a new word has been received. 
        Returns True (1) if a word is waiting to be processed, otherwise False (0).
        """
        if self.new_word_received:
            # Reset the flag
            self.new_word_received = False
            return True
        
        return False
    

    def _check_timeout(self, data: any) -> bool:
        """
        Checks if the broadcast timer has expired.
        Returns True if the current counter exceeds the last broadcast time 
        plus the defined interval.
        """        
        if self.counter > (self.last_broadcast_ticks + self.max_broadcast_ticks):
            return True
        
        return False


    def color_code(self):
        """
        Updates the LED color based on the inventory state.
        - If the robot has not reached consensus (inventory size != 1), the LED is OFF.
        - If consensus is reached, the word is mapped to a specific RGB color.
        """
        # 1. Check if the inventory has reached consensus (size exactly 1)
        if len(self.inventory) != 1:
            self.led = (0, 0, 0)  # Turn LED off
            return

        # 2. Extract the single word known to the agent
        word = list(self.inventory)[0]

        # ------ ORIGINAL ------
        # # 3. Calculate RGB components using the original base-4 logic
        # # Mapping word index (0-127) to a color space (1-64)
        # color = (word % 63) + 1
        
        # r = color // 16
        # rem1 = color % 16
        # g = rem1 // 4
        # b = rem1 % 4

        # # 4. Update the LED state
        # # Note: Original Kilobot RGB values are 0-3. 
        # # convert to range 0-255.
        # self.led = (r * 85, g * 85, b * 85)
        # ------------------------

        # ------ NEW SIMPLIFIED COLOR CODING ------
        # Map the word to an index (0-7)
        color_idx = word % len(DISTINCT_COLORS)

        # Assign the high-contrast color
        self.led = DISTINCT_COLORS[color_idx]
        # -----------------------------------------