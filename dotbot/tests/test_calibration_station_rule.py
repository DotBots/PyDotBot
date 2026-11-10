# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

import json

import pytest

from dotbot.calibration import station_rule as rule

WHOLE = (0, 0, 1060, 1220)


def test_the_fixture_file_is_what_the_rule_writes():
    assert rule.FIXTURES_PATH.read_text(encoding="utf-8") == rule.fixture_text()


@pytest.mark.parametrize(
    "case", json.loads(rule.fixture_text())["cases"], ids=lambda c: c["name"]
)
def test_every_case_keeps_its_station(case):
    rects = {int(k): v for k, v in case["rects"].items()}
    solves = {s: (float(x), float(y)) for s, x, y in case["solves"]}
    assert rule.select(solves, rects) == case["expect"]


@pytest.mark.parametrize(
    "point", json.loads(rule.fixture_text())["points"], ids=lambda p: p["name"]
)
def test_every_point_names_its_candidates(point):
    rects = {int(k): v for k, v in point["rects"].items()}
    assert list(rule.candidates(rects, *point["point"])) == point["expect"]


def test_equal_boxes_decide_nothing():
    rects = {0: WHOLE, 1: WHOLE}
    assert rule.candidates(rects, 10.0, 10.0) == (0, 1)
    assert rule.shared_centres(rects) == [(0, 1)]


def test_split_boxes_hand_over_halfway_between_their_centres():
    rects = {0: (0, 0, 630, 1220), 1: (430, 0, 1060, 1220)}
    assert rule.candidates(rects, 529.9, 600.0) == (0,)
    assert rule.candidates(rects, 530.1, 600.0) == (1,)
    assert rule.shared_centres(rects) == []


def test_an_infinite_solve_is_dropped():
    assert rule.select({0: (float("inf"), 0.0)}, {0: WHOLE}) is None
