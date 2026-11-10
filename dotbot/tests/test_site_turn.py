# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Turning a site on the floor or moving its zero: its calibrations saved
again in a new frame, site.toml's frame id changed, no other number."""

import dataclasses

import pytest
from click.testing import CliRunner

from dotbot.calibration import conics, lighthouse2
from dotbot.calibration.lighthouse2 import read_calibration_file, write_calibration
from dotbot.calibration.placement import Rigid2D, place_calibration, spin_centres
from dotbot.calibration.site_turn import (
    TurnRefused,
    anchor_marks,
    floor_move,
    plan_turn,
    turned,
)
from dotbot.site import Site
from dotbot.tests.test_calibration_conics import CENTRES, track_samples

SELF = "self-defined from spin calibration 1234abcd"
ARENA = Site(name="arena", anchor=SELF, extent_mm=(3000, 4000))
SITE_TOML = f"""\
# kept as it is
anchor = "{SELF}"
extent_mm = [3000, 4000]

[areas.field]   # the top half
x = 0
y = 0
w = 3000
h = 2000
"""


@pytest.fixture(scope="module")
def placed():
    free, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab"), tag="spin"
    )
    return place_calibration(free, ARENA, Rigid2D(800, 900, 0))


def test_a_floor_point_turns_the_other_way_about_the_pivot():
    # The site turns a quarter clockwise about its zero: a point on its old
    # +x axis is on its new -y axis
    x, y = floor_move(90, (0, 0)).apply([(1000, 0)])[0]
    assert (x, y) == pytest.approx((0, -1000))
    assert floor_move(30, (500, 700)).apply([(500, 700)])[0] == pytest.approx(
        (500, 700)
    )


def test_a_turned_calibration_moves_every_fix_by_the_floor_move(placed):
    result = turned(placed, ARENA, 10, (1500, 2000), "zero moved")
    move = floor_move(10, (1500, 2000))
    for a, b in zip(spin_centres(placed)[0], spin_centres(result)[0]):
        assert (b["x"], b["y"]) == pytest.approx(
            move.apply([(a["x"], a["y"])])[0], abs=0.1
        )
    assert result.id != placed.id
    assert [st.valid_mm for st in result.stations] == [
        st.valid_mm for st in placed.stations
    ]
    assert result.valid_mm == placed.valid_mm
    assert result.site == Site(name="arena", anchor="zero moved")
    assert plan_turn([placed], ARENA, 10, (1500, 2000), "zero moved")[0].site.frame
    assert result.edited_from == placed.id
    assert result.placed_from == placed.placed_from != ""
    assert result.tag == "spin-arena-turned"


def test_a_turn_with_nothing_to_do_is_refused_and_a_note_may_stay(placed):
    with pytest.raises(TurnRefused, match="nothing moves"):
        plan_turn([placed], ARENA, 360, (0, 0), "new")
    with pytest.raises(TurnRefused, match="no calibration"):
        plan_turn([], ARENA, 5, (0, 0), "new")
    (kept,) = plan_turn([placed], ARENA, 5, (0, 0), SELF)
    assert kept.site.anchor == SELF and kept.site.frame != ARENA.frame_id


def test_a_shift_alone_moves_zero(placed):
    (shifted,) = plan_turn([placed], ARENA, 0, (0, 0), SELF, shift=(-100, -50))
    for a, b in zip(spin_centres(placed)[0], spin_centres(shifted)[0]):
        assert (b["x"], b["y"]) == pytest.approx((a["x"] + 100, a["y"] + 50), abs=0.1)


def test_a_turn_putting_a_circle_below_zero_is_refused(placed):
    with pytest.raises(TurnRefused, match="below zero"):
        turned(placed, ARENA, 180, (0, 0), "new")


def test_a_calibration_of_another_anchor_is_refused(placed):
    other = Site(name="arena", anchor="the door", extent_mm=(3000, 4000))
    with pytest.raises(TurnRefused, match="not in site arena's frame"):
        turned(placed, other, 5, (0, 0), "new")


def test_floor_marks_are_named(placed):
    assert anchor_marks(ARENA, [placed]) == []
    marked = Site(name="arena", anchor="the door corner")
    assert "names a mark in the room" in anchor_marks(marked, [])[0]
    corner = dataclasses.replace(
        placed,
        stations=[
            dataclasses.replace(st, solved_from="direct") for st in placed.stations
        ],
        placements=[lighthouse2.Placement(index=0, points_mm=[(0.0, 0.0)])],
    )
    (line,) = anchor_marks(ARENA, [corner])
    assert "collected at points measured from the anchor" in line


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    return tmp_path / "home" / "calibrations"


def _lab(tmp_path):
    lab = tmp_path / "lab"
    (lab / "sites" / "arena").mkdir(parents=True)
    (lab / "sites" / "arena" / "site.toml").write_text(SITE_TOML)
    (lab / "dotbot.toml").write_text('site = "arena"\n')
    return lab


def _site_cmd(lab, *args, input=None):
    from dotbot.cli import site_cmd
    from dotbot.config import load_discovered

    return CliRunner().invoke(
        site_cmd.cmd,
        ["turn", *args],
        obj={"config": load_discovered(environ={}, start_dir=lab)},
        input=input,
    )


def test_site_turn_writes_the_new_frame_and_the_calibrations(tmp_path, home, placed):
    lab = _lab(tmp_path)
    write_calibration(placed)
    result = _site_cmd(lab, "arena", "--rotate", "5", "--about", "1500,2000")
    assert result.exit_code == 0, result.output
    (written,) = set((home / "arena").glob("*.toml")) - {placed.path}
    cal = read_calibration_file(written)
    (expected,) = plan_turn([placed], ARENA, 5, (1500, 2000), SELF)
    assert cal.id == expected.id and cal.site.frame == expected.site.frame
    text = (lab / "sites" / "arena" / "site.toml").read_text()
    assert f'frame = "{cal.site.frame}"' in text
    assert f'anchor = "{SELF}"' in text
    assert text.startswith("# kept as it is\n")
    assert f"dotbot swarm calibrate-lh2 push {cal.id8} --site arena" in result.output


def test_site_turn_names_the_largest_legal_shift(tmp_path, home, placed):
    lab = _lab(tmp_path)
    write_calibration(placed)
    result = _site_cmd(lab, "arena", "--shift", "5000,0")
    assert result.exit_code != 0
    assert "the largest legal shift that way is --shift" in result.output


def test_site_turn_asks_when_the_anchor_is_a_floor_mark(tmp_path, home, placed):
    lab = _lab(tmp_path)
    path = lab / "sites" / "arena" / "site.toml"
    path.write_text(SITE_TOML.replace(SELF, "the door corner"))
    marked = Site(name="arena", anchor="the door corner", extent_mm=(3000, 4000))
    write_calibration(dataclasses.replace(placed, site=marked))
    result = _site_cmd(lab, "--rotate", "5", "--anchor", "moved", input="n\n")
    assert result.exit_code != 0
    assert "names a mark in the room" in result.output
    assert "the door corner" in path.read_text()
    result = _site_cmd(lab, "--rotate", "5", "--anchor", "moved", "-y")
    assert result.exit_code == 0, result.output
    assert 'anchor = "moved"' in path.read_text()


def test_site_turn_needs_a_turn_or_a_shift(tmp_path, home, placed):
    lab = _lab(tmp_path)
    write_calibration(placed)
    result = _site_cmd(lab)
    assert result.exit_code != 0
    assert "nothing moves" in result.output
