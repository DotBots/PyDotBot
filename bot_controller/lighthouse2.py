"""Module containing the API to convert LH2 raw data to relative positions."""

# pylint: disable=invalid-name,unspecified-encoding,no-member

import csv
import math
import os
import pickle

from ctypes import CDLL
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from bot_controller.protocol import Lh2RawData


LH2_LIB_PATH = os.path.join(os.path.dirname(__file__), "lib/lh2.so")
POLYNOMIALS = [
    0x0001D258,
    0x00017E04,
    0x0001FF6B,
    0x00013F67,
]
END_BUFFERS = [
    [
        0x00000000000000001,
        0b10101010110011101,
        0b10001010101011010,
        0b11001100100000010,
        0b01100101100011111,
        0b10010001101011110,
        0b10100011001011111,
        0b11110001010110001,
        0b10111000110011011,
        0b10100110100011110,
        0b11001101100010000,
        0b01000101110011111,
        0b11100101011110101,
        0b01001001110110111,
        0b11011100110011101,
        0b10000110101101011,
    ],
    [
        0x00000000000000001,
        0b11010000110111110,
        0b10110111100111100,
        0b11000010101101111,
        0b00101110001101110,
        0b01000011000110100,
        0b00010001010011110,
        0b10100101111010001,
        0b10011000000100001,
        0b01110011011010110,
        0b00100011101000011,
        0b10111011010000101,
        0b00110010100110110,
        0b01000111111100110,
        0b10001101000111011,
        0b00111100110011100,
    ],
    [
        0x00000000000000001,
        0b00011011011000100,
        0b01011101010010110,
        0b11001011001101010,
        0b01110001111011010,
        0b10110110011111010,
        0b10110001110000001,
        0b10001001011101001,
        0b00000010011101011,
        0b01100010101111011,
        0b00111000001101111,
        0b10101011100111000,
        0b01111110101111111,
        0b01000011110101010,
        0b01001011100000011,
        0b00010110111101110,
    ],
    [
        0x00000000000000001,
        0b11011011110010110,
        0b11000100000001101,
        0b11100011000010110,
        0b00011111010001100,
        0b11000001011110011,
        0b10011101110001010,
        0b00001011001111000,
        0b00111100010000101,
        0b01001111001010100,
        0b01011010010110011,
        0b11111101010001100,
        0b00110101011011111,
        0b01110110010101011,
        0b00010000110100010,
        0b00010111110101110,
    ],
]
INITIALIZATION_CAMERA_POINTS = [
    [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],  # Cam A
    [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],  # Cam B
]


def _lh2_raw_data_to_counts(raw_data: Lh2RawData, func: callable) -> List[int]:
    counts = [0] * 4
    pos_A = 0
    pos_B = 0
    for i in range(4):
        index = 0
        if raw_data.locations[i].polynomial_index in [0, 1]:
            index = pos_A
            pos_A += 1
        elif raw_data.locations[i].polynomial_index in [2, 3]:
            index = 2 + pos_B
            pos_B += 1
        if index > 3:
            continue
        counts[index] = func(
            raw_data.locations[i].polynomial_index,
            raw_data.locations[i].bits >> (47 - raw_data.locations[i].offset),
        )
    return counts


def _lh2_raw_data_to_counts_lib(raw_data: Lh2RawData) -> List[int]:
    lh2_lib = CDLL(LH2_LIB_PATH)
    return _lh2_raw_data_to_counts(raw_data, lh2_lib.reverse_count_p)


def _reverse_count_py(index, bit_seq):
    poly = POLYNOMIALS[index]

    count = 0
    match = False
    buffer = bit_seq

    while match is False:
        for idx in range(16):
            if buffer == END_BUFFERS[index][idx]:
                count = count + 8192 * idx - 1
                match = True
                return count

        b17 = buffer & 0b1
        buffer = buffer & 0x1FFFE
        buffer = buffer >> 1
        masked_buffer = buffer & poly
        result = bin(masked_buffer).count("1") % 2
        result = result ^ b17
        result = result << 16
        buffer = buffer | result
        result = 0
        count = count + 1


def _lh2_raw_data_to_counts_py(raw_data: Lh2RawData) -> List[int]:
    return _lh2_raw_data_to_counts(raw_data, _reverse_count_py)


def lh2_raw_data_to_counts(raw_data: Lh2RawData) -> List[int]:
    """Convert bits sequence to an array of counts."""
    if os.path.exists(LH2_LIB_PATH):
        return _lh2_raw_data_to_counts_lib(raw_data)
    return _lh2_raw_data_to_counts_py(raw_data)


def calculate_camera_point(count1, count2, poly_in):
    """Calculate camera points from counts."""
    if poly_in < 2:
        period = 959000
    if poly_in > 1:
        period = 957000

    a1 = (count1 * 8 / period) * 2 * math.pi
    a2 = (count2 * 8 / period) * 2 * math.pi

    cam_x = -math.tan(0.5 * (a1 + a2))
    if count1 < count2:
        cam_y = -math.sin(a2 / 2 - a1 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)
    else:
        cam_y = -math.sin(a1 / 2 - a2 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)

    return cam_x, cam_y


def _unitize(x_in, y_in):
    magnitude = np.sqrt(x_in**2 + y_in**2)
    return x_in / magnitude, y_in / magnitude


@dataclass
class CalibrationData:
    """Class that stores calibration data."""

    zeta: float
    random_rodriguez: np.array
    normal: np.array


def compute_coordinates(
    raw_data: Lh2RawData, calibration: CalibrationData
) -> List[float]:
    """Compute the relative coordinates using raw and calibration data."""
    if any(raw_data.locations[index].bits == 0 for index in range(4)):
        return [0.0, 0.0]
    counts = lh2_raw_data_to_counts(raw_data)
    camera_points = np.asarray(
        [
            calculate_camera_point(
                counts[0], counts[1], raw_data.locations[0].polynomial_index
            ),
            calculate_camera_point(
                counts[2], counts[3], raw_data.locations[2].polynomial_index
            ),
        ],
        dtype="float64",
    )
    print(camera_points, np.ones((len(camera_points), 1)))
    pts_cam_new = np.hstack((camera_points, np.ones((len(camera_points), 1))))
    scales = (1 / calibration.zeta) / np.matmul(calibration.normal, pts_cam_new.T)
    scales_matrix = np.vstack((scales, scales, scales))
    final_points = scales_matrix * pts_cam_new.T
    final_points = final_points.T

    return final_points.dot(calibration.random_rodriguez.T)[0]


def save_camera_points(raw_data: Lh2RawData, filename: str):
    """Store camera points computed from lh2 raw data to a csv file."""
    counts = lh2_raw_data_to_counts(raw_data)
    camera_points = calculate_camera_point(
        counts[0], counts[1], raw_data.locations[0].polynomial_index
    )
    camera_points += calculate_camera_point(
        counts[2], counts[3], raw_data.locations[2].polynomial_index
    )
    with open(filename, "a") as camera_points_file:
        writer = csv.writer(camera_points_file)
        writer.writerow(camera_points)


def compute_calibration_data(calibration_dir: str):  # pylint: disable=too-many-locals
    """Compute n_star and random_rodriguez matrices from a calibration data file."""

    csv_file = os.path.join(calibration_dir, "calibration.csv")
    output = os.path.join(calibration_dir, "calibration.out")
    if not os.path.exists(csv_file):
        raise SystemExit("Cannot find calibration data")

    calibration_data = []
    with open(csv_file) as calibration_file:
        reader = csv.reader(calibration_file)
        for row in reader:
            calibration_data.append(row)

    print(f"found {len(calibration_data)} samples")
    camera_points = [[], []]
    for data in calibration_data:
        camera_points[0].append([data[0], data[1]])
        camera_points[1].append([data[2], data[3]])

    camera_points_arr = np.asarray(camera_points, dtype="float64")

    homography_mat = cv2.findHomography(
        camera_points_arr[0][0 : len(camera_points[0])][:],
        camera_points_arr[1][0 : len(camera_points[1])][:],
        method=cv2.RANSAC,
        ransacReprojThreshold=0.001,
    )[0]

    _, S, V = np.linalg.svd(homography_mat)
    V = V.T

    s1 = S[0] / S[1]
    s3 = S[2] / S[1]
    zeta = s1 - s3
    a1 = np.sqrt(1 - s3**2)
    b1 = np.sqrt(s1**2 - 1)
    a, b = _unitize(a1, b1)
    v1 = np.array(V[:, 0])
    v3 = np.array(V[:, 2])
    n = b * v1 + a * v3

    if n[2] < 0:
        n = -n

    random_rodriguez = np.array(
        [
            [
                -n[1] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                n[0] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                0,
            ],
            [
                n[0] * n[2] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                n[1] * n[2] / np.sqrt(n[0] * n[0] + n[1] * n[1]),
                -np.sqrt(n[0] * n[0] + n[1] * n[1]),
            ],
            [-n[0], -n[1], -n[2]],
        ]
    )

    calibration_data = CalibrationData(zeta, random_rodriguez, n)
    print(f"calibration data:\n\t{calibration_data}")

    with open(output, "wb") as output_file:
        pickle.dump(CalibrationData(zeta, random_rodriguez, n), output_file)
    print(f"calibration data stored in '{output}'")
