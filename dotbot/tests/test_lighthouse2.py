"""Test module for the lighthouse2 API."""

from unittest.mock import patch

import pytest

from dotbot.lighthouse2 import calculate_camera_point, lh2_raw_data_to_counts
from dotbot.protocol import Lh2RawLocation, Lh2RawData


EXPECTED_COUNTS = [49341, 85887, 49341, 85887]
LOCATIONS = [
    Lh2RawLocation(
        bits=0b1110000100011111111001110010111000000100001001100011001010001110,
        polynomial_index=1,
        offset=3,
    ),
    Lh2RawLocation(
        bits=0b1011101111101010101101010010101010100100111101101001000111011100,
        polynomial_index=1,
        offset=1,
    ),
    Lh2RawLocation(
        bits=0b1100001000111111110011100101110000001000010011000110010100011100,
        polynomial_index=1,
        offset=2,
    ),
    Lh2RawLocation(
        bits=0b0111011111010101011010100101010101001001111011010010001110111000,
        polynomial_index=1,
        offset=0,
    ),
]


def test_raw_data_to_counts():
    raw_data = Lh2RawData(locations=LOCATIONS)
    assert lh2_raw_data_to_counts(raw_data) == EXPECTED_COUNTS


@patch("os.path.exists")
def test_raw_data_to_counts_no_lib(lib_exists):
    lib_exists.return_value = False
    raw_data = Lh2RawData(locations=LOCATIONS)
    assert lh2_raw_data_to_counts(raw_data) == EXPECTED_COUNTS


def test_camera_points():
    assert calculate_camera_point(49341, 85887, 1) == pytest.approx(
        (-0.4255775370509014, 0.15468717476270966)
    )
