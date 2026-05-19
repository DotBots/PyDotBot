"""Tests for the LH2 calibration math.

Carried over from dotbot-lh2-calibration's tests/test_lighthouse2.py.
The original test called calculate_camera_point with positional args
matching an older signature (count1, count2, lh_index); the function
now takes an LH2Counts dataclass. Fixed during the fold; kept the
golden values.
"""

import pytest

from dotbot.calibration.lighthouse2 import LH2Counts, calculate_camera_point


def test_camera_points():
    counts = LH2Counts(lh_index=1, count1=49341, count2=85887)
    x, y = calculate_camera_point(counts)
    assert x == pytest.approx(-0.43435315273542)
    assert y == pytest.approx(0.1512338330873567)
