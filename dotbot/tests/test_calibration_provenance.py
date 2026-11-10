# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

from datetime import datetime, timezone

from dotbot.calibration import conics
from dotbot.calibration import multi_station as ms
from dotbot.calibration.provenance import fix_lines, provenance_lines
from dotbot.site import Site, derived_frame_id
from dotbot.tests import lh2_multi_fixture as F
from dotbot.tests.test_calibration_multi_station import floor_grid, two_stations


def _calibration(shared_box: bool):
    a, b = two_stations()
    samples = F.samples(F.spins([a, b], floor_grid([a, b]), noise=0.5, seed=5))
    calibration, _, _ = conics.solve_calibration(
        samples, Site(name="arena", anchor="the door")
    )
    if shared_box:
        for station in calibration.stations:
            station.valid_mm = calibration.valid_mm
    return calibration


def test_the_frame_id_derives_from_the_name_and_anchor():
    assert derived_frame_id("arena", "the door") == derived_frame_id("arena", "the door")
    assert derived_frame_id("arena", "the door") != derived_frame_id("arena", "a door")
    assert len(derived_frame_id("arena", "")) == 8


def test_shared_boxes_say_the_disagreement_decides():
    calibration = _calibration(shared_box=True)
    lines = fix_lines(calibration)
    assert lines[0] == "who gives the fix: S0 and S1 share one box: the boxes do not decide"
    assert "mm disagreement on" in lines[1] and "decides" in lines[1]


def test_the_provenance_names_the_frame_the_error_and_its_limit():
    calibration = _calibration(shared_box=True)
    em = ms.error_map_from_calibration(calibration)
    lines = provenance_lines(
        calibration,
        Site(name="arena", lh2_error_limit_mm=0.01),
        em,
        now=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    text = "\n".join(lines)
    frame = derived_frame_id("arena", calibration.site.anchor)
    assert f"site arena, frame {frame}" in text
    assert f"calibration {calibration.id}" in text
    assert "(a bound), over the 0.0 mm limit" in text
    assert "checked on a mark: not recorded" in text
    assert lines[-1] == "  printed 2026-11-10T00:00:00Z"


def test_the_provenance_names_the_last_check_on_a_mark():
    calibration = _calibration(shared_box=True)
    check = {"error_mm": 3.06, "mark_mm": [500.0, 600.0], "robot": "222A34F9458E8AAD", "at": "2026-11-09T21:48:00Z"}
    lines = provenance_lines(calibration, Site(name="arena", anchor="the door"), None, check=check)
    assert "  checked on a mark: 3.1 mm at (500, 600) by …8E8AAD, 2026-11-09T21:48:00Z" in lines
