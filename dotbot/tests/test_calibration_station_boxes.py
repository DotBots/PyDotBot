# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Changing where each station of a calibration is trusted, as a new
calibration."""

import dataclasses

import pytest

from dotbot.calibration import conics, lighthouse2
from dotbot.calibration.lighthouse2 import read_calibration_file
from dotbot.calibration.placement import Rigid2D, place_calibration, save_new
from dotbot.calibration.station_boxes import (
    BoxesRefused,
    coverage_warnings,
    reboxed,
)
from dotbot.site import Site
from dotbot.tests.test_calibration_conics import (
    CENTRES,
    STATION,
    STATION_B,
    circle_samples,
)

ARENA = Site(name="arena", anchor="the door corner", extent_mm=(3000, 4000))


@pytest.fixture(scope="module")
def free():
    samples = circle_samples(STATION, CENTRES, 0) + circle_samples(
        STATION_B, CENTRES[1:], 1, start=1
    )
    calibration, _, unsolved = conics.solve_calibration(
        samples, Site(name="lab"), tag="spin"
    )
    assert not unsolved
    return calibration


@pytest.fixture(scope="module")
def placed(free):
    return place_calibration(free, ARENA, Rigid2D(100, 200, 0))


def test_only_the_named_rectangle_and_the_fence_change(placed):
    boxed = reboxed(placed, ARENA, {0: (0, 0, 1500, 4000)})
    assert placed.stations[0].valid_mm == (0, 0, 3000, 4000)
    assert [st.valid_mm for st in boxed.stations] == [
        (0, 0, 1500, 4000),
        (0, 0, 3000, 4000),
    ]
    assert boxed.valid_mm == (0, 0, 3000, 4000)
    assert [st.homography for st in boxed.stations] == [
        st.homography for st in placed.stations
    ]
    assert (boxed.tracks, boxed.links, boxed.created_at) == (
        placed.tracks,
        placed.links,
        placed.created_at,
    )
    assert boxed.id != placed.id
    assert boxed.edited_from == placed.id
    assert boxed.placed_from == placed.placed_from
    assert boxed.tag == "spin-arena-boxes"


def test_the_fence_shrinks_to_the_union(placed):
    boxed = reboxed(placed, ARENA, {0: (0, 0, 1500, 2000), 1: (1000, 500, 2500, 3000)})
    assert boxed.valid_mm == (0, 0, 2500, 3000)


def test_a_reboxed_calibration_reads_back_with_its_lineage(placed, tmp_path, monkeypatch):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    boxed, path = save_new(reboxed(placed, ARENA, {1: (500, 0, 3000, 4000)}))
    back = read_calibration_file(path)
    assert back.id == boxed.id
    assert back.edited_from == placed.id
    assert back.station(1).valid_mm == (500, 0, 3000, 4000)
    # Saving the same rectangles again finds the file instead of a second one
    again, same = save_new(reboxed(placed, ARENA, {1: (500, 0, 3000, 4000)}))
    assert same == path and again.id == boxed.id


def test_a_second_edit_numbers_the_tag(placed):
    first = reboxed(placed, ARENA, {0: (0, 0, 1500, 4000)})
    second = reboxed(first, ARENA, {0: (0, 0, 1000, 4000)}, taken_tags=[first.tag])
    assert second.tag == "spin-arena-boxes-2"
    assert second.edited_from == first.id


@pytest.mark.parametrize(
    "rect, why",
    [
        ((100, 0, 100, 4000), "is empty"),
        ((500, 0, 100, 4000), "is empty"),
        ((-10, 0, 1000, 4000), "below zero"),
        ((0, 0, 3001, 4000), "outside the site's extent"),
    ],
)
def test_a_rectangle_a_robot_cannot_take_is_refused(placed, rect, why):
    with pytest.raises(BoxesRefused, match=rf"station 0 \(channel 1\)'s rectangle .*{why}"):
        reboxed(placed, ARENA, {0: rect})


def test_a_free_mode_calibration_is_refused(free):
    with pytest.raises(BoxesRefused, match="free-mode spin calibration"):
        reboxed(free, Site(name="lab"), {0: (0, 0, 100, 100)})


def test_a_calibration_of_another_site_or_anchor_is_refused(placed):
    with pytest.raises(BoxesRefused, match="not in site hall's frame"):
        reboxed(placed, dataclasses.replace(ARENA, name="hall"), {0: (0, 0, 10, 10)})
    with pytest.raises(BoxesRefused, match="anchor"):
        reboxed(placed, dataclasses.replace(ARENA, anchor="moved"), {0: (0, 0, 10, 10)})


def test_an_unknown_station_nothing_changed_and_a_taken_tag_are_refused(placed):
    with pytest.raises(BoxesRefused, match="has no station 5"):
        reboxed(placed, ARENA, {5: (0, 0, 10, 10)})
    with pytest.raises(BoxesRefused, match="nothing to write"):
        reboxed(placed, ARENA, {0: (0, 0, 3000, 4000)})
    with pytest.raises(BoxesRefused, match="tag 'mine' is taken"):
        reboxed(placed, ARENA, {0: (0, 0, 10, 10)}, tag="mine", taken_tags=["Mine"])


def test_a_hand_edited_file_is_refused(placed):
    edited = dataclasses.replace(placed, stored_id="0123456789abcdef")
    with pytest.raises(BoxesRefused, match="edited after it was written"):
        reboxed(edited, ARENA, {0: (0, 0, 10, 10)})


def test_a_rectangle_leaving_out_circles_is_warned_about(placed):
    assert coverage_warnings(placed) == []
    boxed = reboxed(placed, ARENA, {0: (0, 0, 50, 50)})
    (line,) = coverage_warnings(boxed)
    assert line.startswith("station 0 (channel 1)'s rectangle [0, 0, 50, 50] leaves out")
    assert "spin circle(s)" in line

