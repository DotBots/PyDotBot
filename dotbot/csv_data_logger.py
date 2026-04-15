"""CSV Data Logger for DotBot"""

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Union

from dotbot.logger import LOGGER


@dataclass
class CSVLog:
    """Snapshot of a DotBot (real or simulated) for a single CSV row."""

    pos_x: int
    pos_y: int
    direction: int
    pwm_left: int
    pwm_right: int
    encoder_left: int
    encoder_right: int


class CSVDataLogger:
    def __init__(self, file_path: Union[str, Path]) -> None:
        """Initialize the CSV data logger and create a new file."""
        self.file_path: Path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = LOGGER.bind(context=__name__)

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
            "sim_encoder_right",
            "sim_encoder_left",
            "control_mode",
            "waypoint_index",
            "waypoint_x",
            "waypoint_y",
            "battery_level",
            "sim_battery_voltage",
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
        real_log: CSVLog,
        sim_log: CSVLog,
        control_mode: str,
        waypoint_index: int,
        waypoint_x: int,
        waypoint_y: int,
        battery_level: float,
        sim_battery_voltage: float,
        address: str,
    ) -> None:
        """Log a data entry to the CSV file."""
        row = {
            "timestamp": time.time(),
            "real_pos_x": real_log.pos_x,
            "real_pos_y": real_log.pos_y,
            "real_direction": real_log.direction,
            "sim_pos_x": sim_log.pos_x,
            "sim_pos_y": sim_log.pos_y,
            "sim_direction": sim_log.direction,
            "pwm_right": real_log.pwm_right,
            "pwm_left": real_log.pwm_left,
            "encoder_right": real_log.encoder_right,
            "encoder_left": real_log.encoder_left,
            "sim_encoder_right": sim_log.encoder_right,
            "sim_encoder_left": sim_log.encoder_left,
            "control_mode": control_mode,
            "waypoint_index": waypoint_index,
            "waypoint_x": waypoint_x,
            "waypoint_y": waypoint_y,
            "battery_level": battery_level,
            "sim_battery_voltage": sim_battery_voltage,
            "address": address,
        }
        self.logger.info("Logging CSV data", **row)
        self.writer.writerow(row)
        self.file.flush()

    def close(self) -> None:
        """Close the CSV file."""
        if self.file:
            self.file.close()
