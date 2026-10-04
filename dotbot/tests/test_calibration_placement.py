# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Moving a spin calibration onto a site as one rigid body."""

import dataclasses
import math

import numpy as np
import pytest

from dotbot.calibration import conics
from dotbot.calibration.conics import apply
from dotbot.calibration.lighthouse2 import StationSolution, transform_points
from dotbot.calibration.placement import (
    PlacementRefused,
    Rigid2D,
    overlay,
    place_calibration,
    placed_tag,
    save_placed,
    spin_centres,
)
from dotbot.site import Site
from dotbot.tests.test_calibration_conics import (
    CENTRES,
    FLOOR_TO_CAM,
    STATION,
    STATION_B,
    circle_samples,
    track_samples,
)

SITE = Site(name="hand", anchor="the door's left jamb", extent_mm=(5000, 5000))


@pytest.fixture(scope="module")
def spun():
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab"), tag="spin"
    )
    return calibration


def _centres(calibration):
    return {
        (index, c["name"]): (c["x"], c["y"])
        for index, circles in spin_centres(calibration).items()
        for c in circles
    }


def test_a_move_turns_then_shifts():
    move = Rigid2D(1000, 0, 90)
    assert move.apply([(100, 0)]) == [pytest.approx((1000, 100))]


def test_a_move_about_a_pivot_keeps_the_pivot():
    move = Rigid2D.about((500, 300), 90)
    assert move.apply([(500, 300)]) == [pytest.approx((500, 300))]
    assert move.apply([(600, 300)]) == [pytest.approx((500, 400))]


@pytest.mark.parametrize("rotate", [0, 90, 37.5, -90])
def test_the_move_agrees_with_reframe_s_point_transform(rotate):
    points = [(0, 0), (1200, 300), (-40, 2000)]
    move = Rigid2D.about((1200, 300), rotate, (250, -75))
    assert np.ravel(move.apply(points)) == pytest.approx(
        np.ravel(transform_points(points, (250, -75), rotate, (1200, 300)))
    )


def test_a_box_turned_by_a_right_angle_stays_exact():
    assert Rigid2D(3000, 0, 90).box((0, 0, 2000, 1000)) == (2000, 0, 3000, 2000)


def test_a_box_turned_freely_grows_to_hold_the_turned_rectangle():
    x0, y0, x1, y1 = Rigid2D.about((500, 500), 45).box((0, 0, 1000, 1000))
    half = 500 * math.sqrt(2)
    assert (x0, y0) == (math.floor(500 - half), math.floor(500 - half))
    assert (x1, y1) == (math.ceil(500 + half), math.ceil(500 + half))


def test_placed_circles_land_where_the_move_puts_them(spun):
    move = Rigid2D(3000, 400, 90)
    placed = place_calibration(spun, SITE, move)
    before, after = _centres(spun), _centres(placed)
    assert after.keys() == before.keys()
    for key, (x, y) in before.items():
        assert after[key] == pytest.approx(move.apply([(x, y)])[0], abs=0.1)


def test_a_placement_is_a_new_calibration_in_the_site(spun):
    placed = place_calibration(spun, SITE, Rigid2D(3000, 400, 90))
    assert placed.id != spun.id
    assert placed.site.name == "hand"
    assert placed.site.anchor == SITE.anchor
    assert placed.valid_mm == (0, 0, 5000, 5000)
    assert placed.tracks == spun.tracks
    assert placed.tag == "spin-hand"
    assert spun.site.name == "lab" and spun.stations[0].matrix.tolist() != (
        placed.stations[0].matrix.tolist()
    )


def test_scale_is_kept(spun):
    placed = place_calibration(spun, SITE, Rigid2D(2500, 600, 33))
    cam = apply(FLOOR_TO_CAM, np.array([[500.0, 500.0], [1500.0, 2500.0]]))
    a = apply(spun.stations[0].matrix, cam)
    b = apply(placed.stations[0].matrix, cam)
    assert np.linalg.norm(b[1] - b[0]) == pytest.approx(np.linalg.norm(a[1] - a[0]))


def test_a_corner_calibration_is_refused_unless_re_anchored(spun):
    corner = dataclasses.replace(
        spun,
        stations=[
            dataclasses.replace(st, solved_from="direct") for st in spun.stations
        ],
    )
    with pytest.raises(PlacementRefused, match="collected at points of the room"):
        place_calibration(corner, SITE, Rigid2D(100, 0, 0))
    placed = place_calibration(corner, SITE, Rigid2D(100, 0, 0), reanchor=True)
    assert placed.stations[0].solved_from == "direct"


def test_a_move_below_zero_is_refused(spun):
    with pytest.raises(PlacementRefused, match="below zero"):
        place_calibration(spun, SITE, Rigid2D(0, 0, 90))


def test_a_turn_that_puts_the_fence_below_zero_is_refused(spun):
    top = max(y for _, y in _centres(spun).values())
    # Every centre lands at x >= 1, but the fence round them does not
    with pytest.raises(PlacementRefused, match="rectangle"):
        place_calibration(spun, SITE, Rigid2D(math.ceil(top) + 1, 0, 90))


def test_a_re_anchored_calibration_without_tracks_is_held_to_zero_too(spun):
    corner = dataclasses.replace(
        spun,
        tracks=[],
        stations=[
            dataclasses.replace(st, solved_from="direct") for st in spun.stations
        ],
    )
    bare = Site(name="hand", anchor="the door's left jamb")
    with pytest.raises(PlacementRefused, match="below zero"):
        place_calibration(corner, bare, Rigid2D(0, 0, 180), reanchor=True)


def test_saving_a_placement_never_overwrites(spun, tmp_path, monkeypatch):
    from dotbot.calibration import lighthouse2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    same_site = Site(name=spun.site.name, anchor="the door's left jamb")
    unmoved = place_calibration(spun, same_site, Rigid2D())
    if unmoved.id == spun.id:
        with pytest.raises(PlacementRefused, match="nothing to write"):
            save_placed(spun, unmoved)
    first, path = save_placed(spun, place_calibration(spun, SITE, Rigid2D(10, 0, 0)))
    written = path.read_bytes()
    again = place_calibration(spun, SITE, Rigid2D(10, 0, 0), taken_tags=[first.tag])
    second, same = save_placed(spun, again)
    assert same == path and path.read_bytes() == written
    assert second.tag == first.tag == "spin-hand"


def test_the_tag_is_suffixed_with_the_site_and_never_reused():
    assert placed_tag("", "hand") == ""
    assert placed_tag("spin", "hand") == "spin-hand"
    assert placed_tag("spin-hand", "hand") == "spin-hand-2"
    assert placed_tag("spin", "hand", ["spin-hand", "SPIN-HAND-2"]) == "spin-hand-3"


@dataclasses.dataclass
class _RectStation(StationSolution):
    # A station carrying its own rectangle, as a schema 4 file does
    valid_mm: tuple[int, int, int, int] | None = None


def test_every_station_moves_as_one_body_with_its_own_rectangle():
    samples = circle_samples(STATION, CENTRES, 0) + circle_samples(
        STATION_B, CENTRES[1:], 1, start=1
    )
    calibration, _, unsolved = conics.solve_calibration(samples, Site(name="lab"))
    assert not unsolved
    rects = {0: (0, 0, 1500, 1500), 1: (500, 200, 2000, 2800)}
    calibration = dataclasses.replace(
        calibration,
        stations=[
            _RectStation(**dataclasses.asdict(st), valid_mm=rects[st.index])
            for st in calibration.stations
        ],
    )
    move = Rigid2D(3500, 100, 90)
    placed = place_calibration(calibration, SITE, move)
    before, after = _centres(calibration), _centres(placed)
    for key, (x, y) in before.items():
        assert after[key] == pytest.approx(move.apply([(x, y)])[0], abs=0.1)
    assert {st.index: st.valid_mm for st in placed.stations} == {
        0: (2000, 100, 3500, 1600),
        1: (700, 600, 3300, 2100),
    }
    drawn = overlay(placed)["stations"]
    assert [s["rect"] for s in drawn] == [
        [2000, 100, 3500, 1600],
        [700, 600, 3300, 2100],
    ]
    assert placed.valid_mm == (700, 100, 3500, 2100)
    assert all(len(s["circles"]) for s in drawn)
    with pytest.raises(PlacementRefused, match=r"station 1 \(channel 2\)'s rectangle"):
        place_calibration(calibration, SITE, Rigid2D(2700, 100, 90))


def test_reframe_moves_a_spin_calibration_as_the_editor_does(
    spun, tmp_path, monkeypatch
):
    from click.testing import CliRunner

    from dotbot.calibration import lighthouse2
    from dotbot.calibration.lighthouse2 import read_calibration_file, write_calibration
    from dotbot.cli import swarm_lh2
    from dotbot.config import load_discovered

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    source = write_calibration(spun)
    lab = tmp_path / "lab"
    (lab / "sites" / "hand").mkdir(parents=True)
    (lab / "sites" / "hand" / "site.toml").write_text(
        f'anchor = "{SITE.anchor}"\nextent_mm = [5000, 5000]\n'
    )
    (lab / "dotbot.toml").write_text('site = "hand"\n')
    result = CliRunner().invoke(
        swarm_lh2.cmd,
        [
            "reframe",
            str(source),
            "--site",
            "hand",
            "--shift",
            "3000,400",
            "--rotate",
            "90",
        ],
        obj={"config": load_discovered(environ={}, start_dir=lab)},
    )
    assert result.exit_code == 0, result.output
    (written,) = (tmp_path / "home" / "calibrations" / "hand").glob("*.toml")
    expected = place_calibration(spun, SITE, Rigid2D(3000, 400, 90))
    assert read_calibration_file(written).id == expected.id


def test_site_init_s_placement_is_the_editor_s(spun):
    site, placed = conics.self_defined_site(spun, "spun", size_mm=(4000, 4000))
    field = site.areas["field"]
    moved = place_calibration(spun, site, Rigid2D(field.x, field.y, 0))
    assert moved.id == placed.id
    assert moved.tag == placed.tag
