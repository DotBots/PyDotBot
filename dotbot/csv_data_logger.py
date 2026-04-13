"""CSV Data Logger for DotBot"""

import csv
import queue
import time
from pathlib import Path
from typing import IO, Union

from dotbot.dotbot_simulator import DotBotSimulator, SimulatedDotBotSettings


class CSVDataLogger:
    def __init__(self, file_path: Union[str, Path]) -> None:
        """Initialize the CSV data logger and create a new file."""
        self.file_path: Path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.simulator: DotBotSimulator = DotBotSimulator(
            SimulatedDotBotSettings(address="00", pos_x=0, pos_y=0), queue.Queue()
        )  # Create an instance of the simulator to access its state
        self.log_timestamp: float = time.time()

        # Create/overwrite the file with headers
        self.fieldnames: list[str] = [
            "timestamp",
            "real_pos_x",
            "real_pos_y",
            "real_direction",
            "sim_pos_x",
            "sim_pos_y",
            "sim_direction",
            "pwm_right",
            "pwm_left",
            "encoder_right",
            "encoder_left",
            "control_mode",
            "waypoint_index",
            "waypoint_x",
            "waypoint_y",
            "battery_level",
            "address",
        ]
        self.file: IO[str] = open(self.file_path, "w", newline="")
        self.writer: csv.DictWriter = csv.DictWriter(
            self.file, fieldnames=self.fieldnames
        )
        self.writer.writeheader()
        self.file.flush()

    def log(
        self,
        real_pos_x: int,
        real_pos_y: int,
        real_direction: int,
        pwm_right: int,
        pwm_left: int,
        encoder_right: int,
        encoder_left: int,
        control_mode: str,
        waypoint_index: int,
        waypoint_x: int,
        waypoint_y: int,
        battery_level: float,
        address: str,
    ) -> None:
        """Log data entry to CSV file."""
        if self.simulator.pos_x == 0:
            self.simulator.pos_x = real_pos_x
        if self.simulator.pos_y == 0:
            self.simulator.pos_y = real_pos_y
        now = time.time()
        dt = now - self.log_timestamp
        self.log_timestamp = now
        self.simulator.pwm_right = pwm_right
        self.simulator.pwm_left = pwm_left
        self.simulator.diff_drive_model_update(dt)
        row = {
            "timestamp": time.time(),
            "real_pos_x": real_pos_x,
            "real_pos_y": real_pos_y,
            "real_direction": real_direction,
            "sim_pos_x": self.simulator.pos_x,
            "sim_pos_y": self.simulator.pos_y,
            "sim_direction": self.simulator.direction,
            "pwm_right": pwm_right,
            "pwm_left": pwm_left,
            "encoder_right": encoder_right,
            "encoder_left": encoder_left,
            "control_mode": control_mode,
            "waypoint_index": waypoint_index,
            "waypoint_x": waypoint_x,
            "waypoint_y": waypoint_y,
            "battery_level": battery_level,
            "address": address,
        }
        self.writer.writerow(row)
        self.file.flush()

    def close(self) -> None:
        """Close the CSV file."""
        if self.file:
            self.file.close()
