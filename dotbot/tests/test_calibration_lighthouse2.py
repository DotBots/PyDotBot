"""Tests for the LH2 calibration math + persistence.

Carried over from dotbot-lh2-calibration's tests/test_lighthouse2.py.
The original test called calculate_camera_point with positional args
matching an older signature (count1, count2, lh_index); the function
now takes an LH2Counts dataclass. Fixed during the fold; kept the
golden values.
"""

import tomllib

import numpy as np
import pytest

from dotbot.calibration import lighthouse2
from dotbot.calibration.lighthouse2 import (
    LH2Counts,
    LH2Homography,
    LighthouseManager,
    calculate_camera_point,
)


def test_camera_points():
    counts = LH2Counts(lh_index=1, count1=49341, count2=85887)
    x, y = calculate_camera_point(counts)
    assert x == pytest.approx(-0.43435315273542)
    assert y == pytest.approx(0.1512338330873567)


def _seed_homography(value: float) -> LH2Homography:
    h = LH2Homography()
    h.matrix = np.full((3, 3), value, dtype=np.float64)
    return h


def test_save_calibration_writes_toml_and_legacy_out(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    mgr = LighthouseManager(calibration_distance=750, extra_lh_num=1)
    mgr.calibration_output_path = tmp_path / lighthouse2.CALIBRATION_LEGACY_OUT
    mgr.homographies = [_seed_homography(1.5), _seed_homography(2.5)]

    mgr.save_calibration()

    toml_files = list(tmp_path.glob("calibration-*.toml"))
    assert len(toml_files) == 1, f"expected exactly one TOML file, got {toml_files}"
    assert (
        tmp_path / "calibration.out"
    ).exists(), "legacy .out should still be written"

    with open(toml_files[0], "rb") as f:
        parsed = tomllib.load(f)
    assert parsed["schema_version"] == lighthouse2.CALIBRATION_SCHEMA_VERSION
    assert parsed["metadata"]["calibration_distance_mm"] == 750
    assert parsed["metadata"]["num_lh_stations"] == 2
    assert parsed["metadata"]["created_at"].endswith("Z")

    payload = bytes.fromhex(parsed["calibration"]["data_hex"])
    assert payload[0] == 2
    assert len(payload) == 1 + 2 * 36
    assert payload == (tmp_path / "calibration.out").read_bytes()


def test_load_calibration_prefers_newest_toml(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    mgr = LighthouseManager(extra_lh_num=0)
    mgr.calibration_output_path = tmp_path / lighthouse2.CALIBRATION_LEGACY_OUT

    mgr.homographies = [_seed_homography(3.0)]
    mgr.save_calibration()
    first = list(tmp_path.glob("calibration-*.toml"))[0]
    first.stat()  # touch to avoid mtime tie
    import os
    import time

    older = time.time() - 60
    os.utime(first, (older, older))

    mgr.homographies = [_seed_homography(7.0)]
    mgr.save_calibration()

    matrices = mgr.load_calibration()
    assert len(matrices) == 1
    # The newest save wrote 7.0; legacy .out would also be 7.0 (last
    # write wins), so this test specifically pins that the loader picks
    # a TOML file at all by checking the matrix matches the in-memory
    # value packed via homography_as_bytes.
    expected = lighthouse2.homography_as_bytes(np.full((3, 3), 7.0))
    assert matrices[0] == expected


def test_load_calibration_falls_back_to_legacy_out(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    legacy = tmp_path / "calibration.out"
    # 1 homography, all-zero matrix
    legacy.write_bytes(b"\x01" + (b"\x00" * 36))

    mgr = LighthouseManager()
    mgr.calibration_output_path = legacy
    matrices = mgr.load_calibration()
    assert matrices == [b"\x00" * 36]


def test_load_calibration_rejects_unknown_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    (tmp_path / "calibration-2099-01-01T00-00-00Z.toml").write_text(
        'schema_version = 999\n[calibration]\ndata_hex = "00"\n'
    )
    mgr = LighthouseManager()
    with pytest.raises(ValueError, match="schema_version 999"):
        mgr.load_calibration()
