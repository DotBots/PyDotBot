"""CSV Data Logger for DotBot"""

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Optional, Union

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
        control_mode: int,
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


def camera_log_path(csv_data_output: Union[str, Path]) -> Path:
    """The camera log that sits beside one `--csv-data-output` file."""
    path = Path(csv_data_output)
    return path.with_name(f"{path.stem}-camera{path.suffix or '.csv'}")


class CameraCSVLogger:
    """One row per camera detection, with the lighthouse's own answer beside it.

    The two files a run writes are keyed differently: the robot log is keyed
    to an address and written when a packet arrives, a detection has no
    address and arrives from another thread. So this is a second file, and
    each row copies the latest lighthouse pose of the one robot standing in
    the camera's area, which is what makes a single row enough to draw both
    poses superimposed. `timestamp` joins the two files.

    The two headings are DIFFERENT PHYSICAL QUANTITIES and the column names
    say so: `cam_body_heading_deg` is the body's orientation, measured
    whether the robot moves or not, and `lh2_travel_direction_deg` is the
    firmware's direction of travel over the last stretch of motion. They
    agree only after forward motion.
    """

    FIELDNAMES: list[str] = [
        "timestamp",
        "sequence",
        "area",
        "camera_id",
        "status",
        "candidates",
        "elapsed_ms",
        "cam_centre_x_mm",
        "cam_centre_y_mm",
        "cam_photodiode_x_mm",
        "cam_photodiode_y_mm",
        "cam_body_heading_deg",
        "cam_body_heading_atan2_deg",
        "green_lever_mm",
        "tmpl_margin",
        "refined",
        "lh2_address",
        "lh2_x_mm",
        "lh2_y_mm",
        "lh2_travel_direction_deg",
        "lh2_age_s",
        "lh2_in_area",
    ]

    def __init__(
        self, file_path: Union[str, Path], area: str = "", camera_id: str = ""
    ) -> None:
        self.file_path: Path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.area = area
        self.camera_id = camera_id
        self.logger = LOGGER.bind(context=__name__)
        file_exists = self.file_path.exists()
        self.file: IO[str] = open(self.file_path, "a", newline="")
        self.writer: csv.DictWriter = csv.DictWriter(
            self.file, fieldnames=self.FIELDNAMES
        )
        if not file_exists:
            self.writer.writeheader()
        self.file.flush()
        self.write_sidecar()

    @property
    def sidecar_path(self) -> Path:
        """The file pinning the geometry and frames this log was written in."""
        return self.file_path.with_suffix(".toml")

    def write_sidecar(self) -> None:
        """Pin the constants and conventions, so an old log survives a change."""
        self.sidecar_path.write_text(self._sidecar_text(), encoding="utf-8")

    def log(self, record: dict, lh2: Optional[dict] = None) -> None:
        """One detection, and the lighthouse pose it is to be compared with.

        Every detection is a row, `none` included, so a gap in the file is a
        gap in the detection and not an absence of robots.
        """
        pose = record.get("pose") or {}
        centre = pose.get("centre_mm", (None, None))
        photodiode = pose.get("photodiode_mm", (None, None))
        lh2 = lh2 or {}
        row = {
            "timestamp": record.get("timestamp"),
            "sequence": record.get("sequence"),
            "area": record.get("area", self.area),
            "camera_id": record.get("camera_id", self.camera_id),
            "status": record.get("status"),
            "candidates": record.get("candidates"),
            "elapsed_ms": record.get("elapsed_ms"),
            "cam_centre_x_mm": centre[0],
            "cam_centre_y_mm": centre[1],
            "cam_photodiode_x_mm": photodiode[0],
            "cam_photodiode_y_mm": photodiode[1],
            "cam_body_heading_deg": pose.get("heading_deg"),
            "cam_body_heading_atan2_deg": pose.get("heading_atan2_deg"),
            "green_lever_mm": pose.get("green_lever_mm"),
            "tmpl_margin": pose.get("tmpl_margin"),
            "refined": pose.get("refined"),
            "lh2_address": lh2.get("address"),
            "lh2_x_mm": lh2.get("x"),
            "lh2_y_mm": lh2.get("y"),
            "lh2_travel_direction_deg": lh2.get("direction"),
            "lh2_age_s": lh2.get("age_s"),
            "lh2_in_area": lh2.get("in_area", 0),
        }
        self.writer.writerow({k: "" if v is None else v for k, v in row.items()})
        self.file.flush()

    def close(self) -> None:
        """Close the CSV file."""
        if self.file:
            self.file.close()

    def _sidecar_text(self) -> str:
        from dotbot.camera.detection.pose import (
            AXLE_BEHIND_CENTRE_MM,
            NOSE_AHEAD_MM,
            OUTLINE_MM,
            PHOTODIODE_AHEAD_MM,
        )
        from dotbot.camera.service import MM_PER_PX, WARP_FPS_MAX

        outline = ", ".join(f"[{float(x)}, {float(y)}]" for x, y in OUTLINE_MM)
        lines = [
            "schema_version = 1",
            'kind = "camera-detection-log"',
            f'area = "{self.area}"',
            f'camera_id = "{self.camera_id}"',
            f"mm_per_px = {float(MM_PER_PX)}",
            f"warp_fps_max = {float(WARP_FPS_MAX)}",
            "",
            "[frames]",
            'position = "frame millimetres, x right, y down; the frame of '
            "lh2_x_mm/lh2_y_mm and of the site's areas\"",
            "cam_body_heading_deg = \"the robot body's orientation, measured "
            "moving or not. Robot direction convention: 0 = +y, +90 = -x, "
            'wrapped to (-180, 180]; equals cam_body_heading_atan2_deg - 90"',
            'cam_body_heading_atan2_deg = "the same body orientation as '
            'atan2(dy, dx) in the same frame: 0 = +x, +90 = +y"',
            "lh2_travel_direction_deg = \"the firmware's direction of TRAVEL "
            "over the last >= 50 mm of motion, not a body orientation: stale "
            "while the robot stands still, 180 out after reversing, -1000 "
            'until it has ever moved"',
            "lh2_position = \"the photodiode's position, whole millimetres "
            '(the firmware truncates)"',
            'lh2_age_s = "how long ago the lighthouse pose in this row was '
            "received; the detection is of this row's own frame\"",
            'timestamp = "time.time() when the frame was read from the device"',
            "",
            "[robot]",
            f"outline_mm = [{outline}]",
            'outline_frame = "robot frame, +x right, +y forward, origin at the '
            'outline centre"',
            f"photodiode_ahead_mm = {float(PHOTODIODE_AHEAD_MM)}",
            f"nose_ahead_mm = {float(NOSE_AHEAD_MM)}",
            f"axle_behind_mm = {float(AXLE_BEHIND_CENTRE_MM)}",
        ]
        return "\n".join(lines) + "\n"
