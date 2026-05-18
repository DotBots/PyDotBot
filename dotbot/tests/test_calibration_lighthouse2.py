"""Tests for the LH2 calibration math.

Carried over from dotbot-lh2-calibration's tests/test_lighthouse2.py.
The original test called calculate_camera_point with positional args
matching an older signature (count1, count2, lh_index); the function
now takes an LH2Counts dataclass. Fixed during the fold; kept the
golden values.

Skips when opencv-python isn't installed — that's the [calibrate]
extra. The test itself doesn't use cv2, but the module under test
imports it at module-load (homography math).
"""

import pytest

pytest.importorskip(
    "cv2",
    reason="dotbot.calibration.lighthouse2 imports cv2 at module load; "
    "install `dotbot[calibrate]` to run this test.",
)

from dotbot.calibration.lighthouse2 import (  # noqa: E402  (after importorskip)
    LH2Counts,
    calculate_camera_point,
)


def test_camera_points():
    counts = LH2Counts(lh_index=1, count1=49341, count2=85887)
    x, y = calculate_camera_point(counts)
    assert x == pytest.approx(-0.43435315273542)
    assert y == pytest.approx(0.1512338330873567)
