"""CSV Data Logger for DotBot"""

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Optional, Union

from dotbot.logger import LOGGER

if TYPE_CHECKING:
    from dotbot.models import DotBotPoseModel


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
            "pose_centre_x",
            "pose_centre_y",
            "heading_deg",
            "heading_source",
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
        pose: Optional["DotBotPoseModel"] = None,
    ) -> None:
        """Log a data entry to the CSV file."""
        row = {
            "timestamp": time.time(),
            "real_pos_x": real_log.pos_x,
            "real_pos_y": real_log.pos_y,
            "real_direction": real_log.direction,
            "pose_centre_x": pose.centre.x if pose else None,
            "pose_centre_y": pose.centre.y if pose else None,
            "heading_deg": pose.heading_deg if pose else None,
            "heading_source": pose.heading_source if pose else None,
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

    A second file rather than more columns on the robot log: that one is
    keyed to an address and written when a packet arrives, a detection has
    no address and arrives from another thread. Each row copies the latest
    lighthouse pose of the one robot standing in the camera's area, which is
    what makes a single row enough to draw both poses superimposed.
    `timestamp` joins the two files.

    The sidecar beside the CSV is what says what each column means; it is
    written from `_sidecar_text` and read back by anyone analysing the log.
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
        "green_flare",
        "tmpl_margin",
        "refined",
        "lh2_address",
        "lh2_x_mm",
        "lh2_y_mm",
        "lh2_travel_direction_deg",
        "lh2_packet_age_s",
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
        if file_exists:
            self._check_appendable()
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

    def _check_appendable(self) -> None:
        """Refuse an existing log this build's sidecar would misdescribe.

        One sidecar describes the whole file, so appending rows written
        against different columns, geometry or conventions would leave the
        older rows described by a file that no longer fits them. Which
        camera wrote a row is not part of the check: `camera_id` is on
        every row, so a re-registration mid-file stays recoverable.
        """
        import tomllib

        with open(self.file_path, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle), [])
        if header and header != self.FIELDNAMES:
            raise ValueError(
                f"{self.file_path} has different columns than this build "
                "writes, so its rows and new ones cannot share one sidecar. "
                "Pass a new --csv-data-output."
            )
        if not self.sidecar_path.exists():
            return
        try:
            existing = tomllib.loads(self.sidecar_path.read_text(encoding="utf-8"))
            mine = tomllib.loads(self._sidecar_text())
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(
                f"{self.sidecar_path} cannot be read, so it cannot be shown "
                f"to describe the rows already in {self.file_path.name}: {exc}"
            ) from exc
        described = ("schema_version", "mm_per_px", "warp_fps_max", "frames", "robot")
        differing = [key for key in described if existing.get(key) != mine.get(key)]
        if differing:
            raise ValueError(
                f"{self.sidecar_path} describes {self.file_path.name} under a "
                f"different {', '.join(differing)} than this build writes, so "
                "appending would leave the rows already there misdescribed. "
                "Pass a new --csv-data-output."
            )

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
            "green_flare": pose.get("green_flare"),
            "tmpl_margin": pose.get("tmpl_margin"),
            "refined": pose.get("refined"),
            "lh2_address": lh2.get("address"),
            "lh2_x_mm": lh2.get("x"),
            "lh2_y_mm": lh2.get("y"),
            "lh2_travel_direction_deg": lh2.get("direction"),
            "lh2_packet_age_s": lh2.get("packet_age_s"),
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
        from dotbot.camera.raster import MM_PER_PX, WARP_FPS_MAX

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
            'position = "every *_mm column: frame millimetres, x right, y '
            "down, the frame the site's areas are measured in\"",
            "cam_body_heading_deg = \"the robot body's orientation, measured "
            "moving or not. Robot direction convention: 0 = +y, +90 = -x, "
            'wrapped to (-180, 180]; equals cam_body_heading_atan2_deg - 90"',
            'cam_body_heading_atan2_deg = "the same body orientation as '
            'atan2(dy, dx) in the same frame: 0 = +x, +90 = +y"',
            "lh2_x_mm = \"the photodiode's position as the robot last "
            "advertised it, whole millimetres (the firmware truncates). The "
            "firmware keeps the fix it holds until a new one is at least 50 "
            'mm away, so this trails the robot by up to 50 mm of travel"',
            'lh2_y_mm = "the same quantity on the y axis"',
            "lh2_travel_direction_deg = \"the firmware's direction of TRAVEL, "
            "never a body orientation. -1000 from boot until the first "
            "lighthouse fix; from that fix until the robot has moved 50 mm it "
            "is the bearing from the frame ORIGIN to that first fix, which "
            "reads as a valid direction and is not one; after that, the "
            "direction of travel over the last >= 50 mm, stale while the "
            'robot stands still and 180 out after reversing"',
            'lh2_packet_age_s = "seconds since the last packet of ANY kind '
            "from this robot, not the age of the fix: the robot repeats its "
            "last accepted fix in every advertisement, so a small age does "
            'not mean a fresh fix"',
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
