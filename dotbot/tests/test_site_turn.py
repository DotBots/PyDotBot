# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Turning a site on the floor: its calibrations saved again for the turned
frame, its anchor rewritten, no other number of site.toml changed."""

import dataclasses

import pytest

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
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_conics import CENTRES, track_samples
from dotbot.tests.test_site_editor import local_client

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
    assert result.edited_from == placed.id
    assert result.placed_from == placed.placed_from != ""
    assert result.tag == "spin-arena-turned"


def test_a_turn_with_nothing_to_do_or_the_same_anchor_is_refused(placed):
    with pytest.raises(TurnRefused, match="0 degrees"):
        plan_turn([placed], ARENA, 360, (0, 0), "new")
    with pytest.raises(TurnRefused, match="anchor still reads"):
        plan_turn([placed], ARENA, 5, (0, 0), SELF + "  ")
    with pytest.raises(TurnRefused, match="no calibration"):
        plan_turn([], ARENA, 5, (0, 0), "new")


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
        stations=[dataclasses.replace(st, solved_from="direct") for st in placed.stations],
        placements=[lighthouse2.Placement(index=0, points_mm=[(0.0, 0.0)])],
    )
    (line,) = anchor_marks(ARENA, [corner])
    assert "collected at points measured from the anchor" in line


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    return tmp_path / "home" / "calibrations"


@pytest.fixture
def pack(tmp_path, home, placed):
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(SITE_TOML)
    write_calibration(placed)
    return pack


@pytest.fixture
def client(pack, home):
    saves = []
    app = create_app(
        EditorState("arena", pack, [home / "arena"]),
        page_dir=None,
        on_saved=lambda: saves.append(1),
    )
    c = local_client(app)
    c.saves = saves
    return c


def _turn(client, **body):
    loaded = client.get("/api/site").json()
    request = {
        "theta_deg": 5,
        "pivot": [1500, 2000],
        "anchor": "zero is 40 mm right of the pillar",
        "calibrations": [c["id"] for c in client.get("/api/turn").json()["calibrations"]],
        "revision": loaded["revision"],
        **body,
    }
    return client.post("/api/turn", json=request)


def test_the_turn_lists_the_calibrations_in_the_site_s_frame(client, placed):
    info = client.get("/api/turn").json()
    assert [c["id"] for c in info["calibrations"]] == [placed.id]
    assert info["pivot"] == [1500, 2000]
    assert info["anchor"] == SELF
    assert info["anchor_marks"] == []


def test_a_turn_writes_new_calibrations_and_only_the_anchor(client, pack, home, placed):
    source = placed.path.read_bytes()
    body = _turn(client).json()
    (saved,) = body["saved"]
    assert placed.path.read_bytes() == source
    written = read_calibration_file(saved["path"])
    assert written.id == saved["id"] != placed.id
    assert written.site.anchor == "zero is 40 mm right of the pillar"
    assert written.edited_from == placed.id
    assert saved["push"] == f"dotbot swarm calibrate-lh2 push {written.id8} --site arena"
    assert (pack / "site.toml").read_text() == SITE_TOML.replace(
        SELF, "zero is 40 mm right of the pillar"
    )
    assert client.saves == [1]
    # The old calibration names the old anchor, so only the new one is in frame
    assert [c["id"] for c in client.get("/api/turn").json()["calibrations"]] == [
        written.id
    ]


def test_a_turn_over_an_older_site_toml_is_a_409(client, pack, home):
    response = _turn(client, revision="stale")
    assert response.status_code == 409
    assert len(list((home / "arena").glob("*.toml"))) == 1
    assert (pack / "site.toml").read_text() == SITE_TOML


def test_a_turn_keeping_the_anchor_is_refused_and_writes_nothing(client, home):
    response = _turn(client, anchor=SELF)
    assert response.status_code == 422
    assert "anchor still reads" in response.json()["detail"]
    assert len(list((home / "arena").glob("*.toml"))) == 1


def test_another_anchor_takes_a_calibration_out_and_is_named(client, pack):
    (pack / "site.toml").write_text(SITE_TOML.replace(SELF, "the door corner"))
    response = client.get("/api/turn").json()
    # The placed calibration records the old anchor: no longer in frame
    assert response["calibrations"] == []
    assert "names a mark in the room" in response["anchor_marks"][0]


def test_a_floor_marked_anchor_is_refused_until_confirmed(client, pack, home, placed):
    marked = Site(name="arena", anchor="the door corner", extent_mm=(3000, 4000))
    write_calibration(dataclasses.replace(placed, site=marked))
    (pack / "site.toml").write_text(SITE_TOML.replace(SELF, "the door corner"))
    refused = _turn(client)
    assert refused.status_code == 422
    assert "floor marks" in refused.json()["detail"]
    assert _turn(client, marks_confirmed=True).status_code == 200
