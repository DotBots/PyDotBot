"""CSV Data Logger for DotBot"""

import csv
import queue
import time
from pathlib import Path
from typing import IO, Union

from dotbot.dotbot_simulator import DotBotSimulator, SimulatedDotBotSettings
from dotbot.logger import LOGGER


class CSVDataLogger:
    def __init__(self, file_path: Union[str, Path]) -> None:
        """Initialize the CSV data logger and create a new file."""
        self.file_path: Path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.simulators: dict[str, DotBotSimulator] = {}
        self.log_timestamps: dict[str, float] = {}
        self.logger = LOGGER.bind(context=__name__)

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
        file_exists = self.file_path.exists()
        self.file: IO[str] = open(self.file_path, "a", newline="")
        self.writer: csv.DictWriter = csv.DictWriter(
            self.file, fieldnames=self.fieldnames
        )
        if not file_exists:
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
        if address not in self.simulators:
            self.simulators[address] = DotBotSimulator(
                SimulatedDotBotSettings(
                    address=address, pos_x=real_pos_x, pos_y=real_pos_y
                ),
                queue.Queue(),
            )
            self.log_timestamps[address] = time.time()
        simulator = self.simulators[address]
        simulator.pos_x = real_pos_x
        simulator.pos_y = real_pos_y
        simulator.direction = real_direction
        now = time.time()
        dt = now - self.log_timestamps[address]
        self.log_timestamps[address] = now
        simulator.pwm_right = pwm_right
        simulator.pwm_left = pwm_left
        simulator.diff_drive_model_update(dt)
        row = {
            "timestamp": time.time(),
            "real_pos_x": real_pos_x,
            "real_pos_y": real_pos_y,
            "real_direction": real_direction,
            "sim_pos_x": simulator.pos_x,
            "sim_pos_y": simulator.pos_y,
            "sim_direction": simulator.direction,
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
        self.logger.info("Logging CSV data", **row)
        self.writer.writerow(row)
        self.file.flush()

    def close(self) -> None:
        """Close the CSV file."""
        if self.file:
            self.file.close()
