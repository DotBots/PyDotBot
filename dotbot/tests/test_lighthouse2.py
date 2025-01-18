"""Test module for the lighthouse2 API."""

import pytest

from dotbot.lighthouse2 import calculate_camera_point, lh2_raw_data_to_counts
from dotbot.protocol import PayloadLh2RawData, PayloadLh2RawLocation

EXPECTED_COUNTS = [49341, 85887]
LOCATIONS = [
    PayloadLh2RawLocation(
        bits=0b1110000100011111111001110010111000000100001001100011001010001110,
        polynomial_index=1,
        offset=3,
    ),
    PayloadLh2RawLocation(
        bits=0b1011101111101010101101010010101010100100111101101001000111011100,
        polynomial_index=1,
        offset=1,
    ),
]


def test_raw_data_to_counts():
    raw_data = PayloadLh2RawData(locations=LOCATIONS)
    assert lh2_raw_data_to_counts(raw_data) == EXPECTED_COUNTS


def test_camera_points():
    assert calculate_camera_point(49341, 85887, 1) == pytest.approx(
        (-0.4255775370509014, 0.15468717476270966)
    )
