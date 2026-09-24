"""Tests for the camera detection log and the sidecar that explains it."""

import csv
import tomllib

import pytest

from dotbot.csv_data_logger import CameraCSVLogger, camera_log_path

FOUND = {
    "area": "dev-corner",
    "camera_id": "22248be43bde6d93",
    "sequence": 412,
    "timestamp": 1758100000.123,
    "status": "found",
    "candidates": 1,
    "elapsed_ms": 48.2,
    "robots": [
        {
            "address": "0000000000000001",
            "status": "found",
            "timestamp": 1758100000.123,
            "pose": {
                "centre_mm": [1523.4, 488.1],
                "photodiode_mm": [1540.2, 511.7],
                "nose_mm": [1551.0, 526.2],
                "outline_mm": [[1481.2, 500.3]],
                "heading_deg": -37.5,
                "heading_atan2_deg": 52.5,
                "green_flare": 0.82,
                "tmpl_margin": 0.91,
                "refined": True,
            },
        }
    ],
}

NOTHING = {
    "area": "dev-corner",
    "camera_id": "22248be43bde6d93",
    "sequence": 413,
    "timestamp": 1758100000.223,
    "status": "none",
    "candidates": 0,
    "elapsed_ms": 5.1,
}

LH2 = {
    "address": "0000000000000001",
    "x": 1541,
    "y": 509,
    "direction": 315,
    "packet_age_s": 0.42,
    "in_area": 1,
}


def rows_of(path):
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_camera_log_sits_beside_the_robot_log():
    assert camera_log_path("run.csv").name == "run-camera.csv"
    assert camera_log_path("run.csv").with_suffix(".toml").name == "run-camera.toml"
    assert camera_log_path("/data/run").name == "run-camera.csv"


def test_a_found_detection_writes_every_column(tmp_path):
    path = camera_log_path(tmp_path / "run.csv")
    logger = CameraCSVLogger(path, area="dev-corner", camera_id="22248be43bde6d93")
    logger.log(FOUND, LH2, FOUND["robots"][0])
    logger.close()

    with open(path, newline="") as handle:
        header = next(csv.reader(handle))
    assert header == CameraCSVLogger.FIELDNAMES

    (row,) = rows_of(path)
    assert row["status"] == "found"
    assert row["sequence"] == "412"
    assert row["cam_centre_x_mm"] == "1523.4"
    assert row["cam_photodiode_y_mm"] == "511.7"
    assert row["cam_body_heading_deg"] == "-37.5"
    assert row["cam_body_heading_atan2_deg"] == "52.5"
    assert row["refined"] == "True"
    assert row["lh2_address"] == "0000000000000001"
    assert row["lh2_travel_direction_deg"] == "315"
    assert row["lh2_packet_age_s"] == "0.42"
    assert row["lh2_in_area"] == "1"
    assert row["cam_address"] == "0000000000000001"
    assert row["cam_status"] == "found"
    assert all(row[name] != "" for name in CameraCSVLogger.FIELDNAMES)


def test_a_detection_of_nothing_is_a_row_too(tmp_path):
    """A gap in the file is a gap in the detection, not an absence of robots."""
    path = camera_log_path(tmp_path / "run.csv")
    logger = CameraCSVLogger(path, area="dev-corner")
    logger.log(NOTHING, {"in_area": 0})
    logger.close()

    (row,) = rows_of(path)
    assert row["status"] == "none"
    assert row["cam_centre_x_mm"] == ""
    assert row["cam_body_heading_deg"] == ""
    assert row["lh2_address"] == ""
    assert row["lh2_in_area"] == "0"


def test_rows_append_to_an_existing_file(tmp_path):
    path = camera_log_path(tmp_path / "run.csv")
    first = CameraCSVLogger(path, area="dev-corner")
    first.log(FOUND, LH2, FOUND["robots"][0])
    first.close()
    second = CameraCSVLogger(path, area="dev-corner")
    second.log(NOTHING, None)
    second.close()

    rows = rows_of(path)
    assert [row["sequence"] for row in rows] == ["412", "413"]


def test_the_sidecar_pins_the_geometry_the_log_was_written_against(tmp_path):
    """An old log outlives a change to the outline only if this file exists."""
    from dotbot.camera.detection.pose import (
        NOSE_AHEAD_MM,
        OUTLINE_MM,
        PHOTODIODE_AHEAD_MM,
    )
    from dotbot.camera.raster import MM_PER_PX

    path = camera_log_path(tmp_path / "run.csv")
    logger = CameraCSVLogger(path, area="dev-corner", camera_id="22248be43bde6d93")
    logger.close()

    sidecar = path.with_suffix(".toml")
    assert sidecar.exists()
    pinned = tomllib.loads(sidecar.read_text())

    assert pinned["kind"] == "camera-detection-log"
    assert pinned["area"] == "dev-corner"
    assert pinned["camera_id"] == "22248be43bde6d93"
    assert pinned["mm_per_px"] == MM_PER_PX
    assert pinned["robot"]["outline_mm"] == [[x, y] for x, y in OUTLINE_MM]
    assert pinned["robot"]["photodiode_ahead_mm"] == PHOTODIODE_AHEAD_MM
    assert pinned["robot"]["nose_ahead_mm"] == NOSE_AHEAD_MM


def test_the_sidecar_separates_body_heading_from_direction_of_travel(tmp_path):
    """The two angles are different quantities and the file has to say so."""
    path = camera_log_path(tmp_path / "run.csv")
    CameraCSVLogger(path, area="dev-corner").close()
    frames = tomllib.loads(path.with_suffix(".toml").read_text())["frames"]

    assert "moving or not" in frames["cam_body_heading_deg"]
    assert "0 = +y" in frames["cam_body_heading_deg"]
    assert "0 = +x" in frames["cam_body_heading_atan2_deg"]
    assert "TRAVEL" in frames["lh2_travel_direction_deg"]
    assert "-1000" in frames["lh2_travel_direction_deg"]
    assert "photodiode" in frames["lh2_x_mm"]


def test_the_sidecar_warns_that_a_first_fix_reads_as_a_direction(tmp_path):
    """-1000 is not the filter that drops every pre-motion row."""
    path = camera_log_path(tmp_path / "run.csv")
    CameraCSVLogger(path, area="dev-corner").close()
    frames = tomllib.loads(path.with_suffix(".toml").read_text())["frames"]

    assert "ORIGIN" in frames["lh2_travel_direction_deg"]
    assert "50 mm" in frames["lh2_travel_direction_deg"]
    assert "ANY kind" in frames["lh2_packet_age_s"]
    assert "fresh fix" in frames["lh2_packet_age_s"]


def test_appending_under_a_different_sidecar_is_refused(tmp_path):
    """One sidecar describes the whole file, so the older rows must still fit."""
    path = camera_log_path(tmp_path / "run.csv")
    CameraCSVLogger(path, area="dev-corner").close()
    sidecar = path.with_suffix(".toml")
    sidecar.write_text(
        sidecar.read_text().replace("mm_per_px = 2.0", "mm_per_px = 1.0")
    )

    with pytest.raises(ValueError) as caught:
        CameraCSVLogger(path, area="dev-corner")
    assert "mm_per_px" in str(caught.value)
    assert sidecar.name in str(caught.value)


def test_appending_under_different_columns_is_refused(tmp_path):
    path = camera_log_path(tmp_path / "run.csv")
    path.write_text("timestamp,sequence\n")

    with pytest.raises(ValueError) as caught:
        CameraCSVLogger(path, area="dev-corner")
    assert "different columns" in str(caught.value)


def test_a_re_registered_camera_still_appends(tmp_path):
    """`camera_id` is on every row, so a new registration is recoverable."""
    path = camera_log_path(tmp_path / "run.csv")
    first = CameraCSVLogger(path, area="dev-corner", camera_id="1111111111111111")
    first.log(FOUND, LH2, FOUND["robots"][0])
    first.close()
    second = CameraCSVLogger(path, area="dev-corner", camera_id="2222222222222222")
    second.log(NOTHING, None)
    second.close()

    assert [row["sequence"] for row in rows_of(path)] == ["412", "413"]
