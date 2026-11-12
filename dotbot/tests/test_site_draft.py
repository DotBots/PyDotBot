# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

# ruff: noqa: F811

"""One draft, one Save: every pending edit composed into site.toml and at
most one calibration, a move of the origin moving the extent rigidly and
keeping everything else where it is on the floor."""

import pytest

from dotbot import site_history
from dotbot.calibration.lighthouse2 import read_calibration_file, write_calibration
from dotbot.site_draft import Move, between, moved_site
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_station_boxes import free  # noqa: F401
from dotbot.tests.test_site_editor import local_client
from dotbot.tests.test_site_placement import home, spun  # noqa: F401

SITE = """\
# The bench: zero is the door corner.

anchor = "the door corner"
extent_mm = [2000, 4000]   # the floor

[areas.field]   # where they run
x = 0
y = 0
w = 2000
h = 2000

[[walls]]
name = "north"
points = [[0, 1000], [1000, 1000]]

[objects.pad]
kind = "charger"
x = 800
y = 1800
heading_deg = 90.0
"""

BENCH = """\
anchor = "the tape cross"
extent_mm = [1060, 1220]

[areas.field]
x = 0
y = 0
w = 1060
h = 1220
"""


def _editor(tmp_path, text):
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(text, newline="\n")
    used = []
    client = local_client(
        create_app(
            EditorState("arena", pack, []),
            page_dir=None,
            serve=lambda spec, persist: used.append(spec) or {"served": {"id": spec}},
        )
    )
    return client, pack, used


def _loaded(client):
    body = client.get("/api/site").json()
    site = body["site"]
    for key in ("areas", "objects"):
        for entry in site.get(key) or []:
            entry["was"] = entry["name"]
    for key in ("walls", "obstacles"):
        for i, entry in enumerate(site.get(key) or []):
            entry["was"] = i
    site.pop("connection", None)
    site.pop("frame", None)
    return body["revision"], site


def _save(client, site=None, **calibration):
    revision, _ = _loaded(client)
    body = {"revision": revision, "site": site}
    if calibration:
        body["calibration"] = calibration
    response = client.post("/api/apply", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _calibrations(home):  # noqa: F811
    return sorted((home / "arena").glob("*.toml"))


@pytest.fixture
def editor(tmp_path, home):  # noqa: F811
    return _editor(tmp_path, SITE)


@pytest.fixture
def placed(editor, free):  # noqa: F811
    client, _, _ = editor
    write_calibration(free)
    body = _save(client, source=free.id, place={"dx_mm": 100, "dy_mm": 200})
    (step,) = (s for s in body["steps"] if s["step"] == "calibration")
    return read_calibration_file(step["detail"])


def test_several_edits_then_one_save_write_one_file(editor, placed, home):  # noqa: F811
    client, pack, used = editor
    before = _calibrations(home)
    _, site = _loaded(client)
    site["areas"][0]["w"] = 1500
    site["areas"].append({"name": "pen", "x": 0, "y": 2000, "w": 500, "h": 500})
    site["objects"][0]["x"] = 900
    body = _save(
        client,
        site,
        source=placed.id,
        stations={"0": [0, 0, 1200, 4000], "1": [800, 0, 2000, 4000]},
    )
    assert body["ok"] is True
    assert [(s["step"], s["status"]) for s in body["steps"]] == [
        ("calibration", "written"),
        ("site.toml", "written"),
        ("use", "written"),
    ]
    (new,) = set(_calibrations(home)) - set(before)
    saved = read_calibration_file(new)
    assert [st.coverage_mm for st in saved.stations] == [
        (0, 0, 1200, 4000),
        (800, 0, 2000, 4000),
    ]
    assert saved.tag == f"{placed.tag}-split"
    assert saved.edited_from == placed.id
    assert used == [placed.id, saved.id]
    assert len(site_history.versions("arena")) == 1
    text = (pack / "site.toml").read_text()
    assert "[areas.pen]" in text and "# where they run" in text


def test_a_save_of_an_unchanged_draft_writes_nothing(
    editor, placed, home
):  # noqa: F811
    client, pack, used = editor
    before = (_calibrations(home), (pack / "site.toml").read_bytes())
    _, site = _loaded(client)
    rects = {str(st.index): list(st.coverage_mm) for st in placed.stations}
    body = _save(client, site, source=placed.id, stations=rects)
    assert [(s["step"], s["status"]) for s in body["steps"]] == [
        ("calibration", "unchanged"),
        ("site.toml", "unchanged"),
    ]
    assert (_calibrations(home), (pack / "site.toml").read_bytes()) == before
    assert site_history.versions("arena") == []
    assert used == [placed.id]


def test_a_draft_equal_to_an_existing_file_reuses_it(
    editor, placed, home
):  # noqa: F811
    client, _, _ = editor
    split = {"0": [0, 0, 1200, 4000], "1": [800, 0, 2000, 4000]}
    first = _save(client, source=placed.id, stations=split)["calibration"]
    files = _calibrations(home)
    revision, _ = _loaded(client)
    dry = client.post(
        "/api/apply",
        json={
            "revision": revision,
            "calibration": {"source": placed.id, "stations": split},
            "dry_run": True,
        },
    ).json()
    assert dry["calibration"]["existing"]["id"] == first["id"]
    assert dry["calibration"]["new"] is False
    assert dry["calibration"]["tag"] == first["tag"]
    again = _save(client, source=placed.id, stations=split)
    assert again["steps"][0]["status"] == "reused"
    assert _calibrations(home) == files


def test_a_dry_run_names_the_tag_it_derives_and_writes_nothing(
    editor, placed, home  # noqa: F811
):
    client, pack, used = editor
    before = (_calibrations(home), (pack / "site.toml").read_bytes())
    revision, site = _loaded(client)
    moved = client.post(
        "/api/frame",
        json={
            "calibration": placed.id,
            "site": site,
            "base": site,
            "move": {"dx_mm": -100},
        },
    ).json()
    dry = client.post(
        "/api/apply",
        json={
            "revision": revision,
            "site": moved["site"],
            "calibration": {"source": placed.id, "frame": {"dx_mm": -100}},
            "dry_run": True,
        },
    ).json()
    assert dry["calibration"]["tag"] == f"{placed.tag}-moved"
    assert dry["calibration"]["new"] is True and dry["use"] is True
    assert dry["frame"] == moved["frame"] != dry["from_frame"]
    assert f'frame = "{moved["frame"]}"' in dry["text"]
    assert (_calibrations(home), (pack / "site.toml").read_bytes()) == before
    assert used == [placed.id]


def test_an_origin_move_and_a_split_save_as_one_file_everything_kept_in_place(
    editor, placed, home  # noqa: F811
):
    client, pack, used = editor
    before = _calibrations(home)
    _, site = _loaded(client)
    move = {"theta_deg": 0, "pivot": [0, 0], "dx_mm": -300, "dy_mm": -200}
    moved = client.post(
        "/api/frame",
        json={"calibration": placed.id, "site": site, "base": site, "move": move},
    )
    assert moved.status_code == 200, moved.text
    moved = moved.json()
    # The extent moves with zero at its size, so the coverage is cut to it
    assert moved["coverage"] == {
        "0": [300, 200, 2000, 4000],
        "1": [300, 200, 2000, 4000],
    }
    assert moved["site"]["extent_mm"] == [2000, 4000]
    assert any("cut to it" in w for w in moved["warnings"])
    split = {"0": [300, 200, 1500, 4000], "1": [1100, 200, 2000, 4000]}
    body = _save(client, moved["site"], source=placed.id, frame=move, stations=split)
    assert body["ok"] is True, body
    (new,) = set(_calibrations(home)) - set(before)
    saved = read_calibration_file(new)
    assert [st.coverage_mm for st in saved.stations] == [
        (300, 200, 1500, 4000),
        (1100, 200, 2000, 4000),
    ]
    assert saved.tag == f"{placed.tag}-moved-split"
    assert saved.edited_from == placed.id
    assert saved.site.frame == moved["frame"]
    assert used == [placed.id, saved.id]
    site = client.get("/api/site").json()["site"]
    assert site["frame"] == moved["frame"]
    (field,) = site["areas"]
    assert (field["x"], field["y"], field["w"], field["h"]) == (300, 200, 2000, 2000)
    assert site["walls"][0]["points"] == [[300, 1200], [1300, 1200]]
    assert (site["objects"][0]["x"], site["objects"][0]["y"]) == (1100, 2000)
    assert site["objects"][0]["heading_deg"] == 90.0
    assert site["extent_mm"] == [2000, 4000]
    assert "# where they run" in (pack / "site.toml").read_text()


def _bench(tmp_path, spun):  # noqa: F811
    client, _, _ = _editor(tmp_path, BENCH)
    cal = read_calibration_file(
        next(
            s["detail"]
            for s in _save(client, source=spun.id8, place={})["steps"]
            if s["step"] == "calibration"
        )
    )
    return client, cal


def _frame(client, cal, site, move, base=None, start=None):
    body = {"calibration": cal.id, "site": site, "base": base or site, "move": move}
    if start is not None:
        body["start"] = start
    response = client.post("/api/frame", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_bench_s_origin_moved_500_mm_left_and_up_moves_the_extent_rigidly(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    assert cal.stations[0].coverage_mm == (0, 0, 1060, 1220)
    _, site = _loaded(client)
    move = {"dx_mm": -500, "dy_mm": -500}
    moved = _frame(client, cal, site, move)
    # Same size; its far corner moves by the shift, so the field and the
    # coverage keep their floor place and run past it
    assert moved["site"]["extent_mm"] == [1060, 1220]
    assert moved["coverage"]["0"] == [500, 500, 1060, 1220]
    (field,) = moved["site"]["areas"]
    assert (field["x"], field["y"], field["w"], field["h"]) == (500, 500, 1060, 1220)
    assert any("outside the extent" in w for w in moved["warnings"])
    body = _save(client, moved["site"], source=cal.id, frame=move)
    saved = read_calibration_file(body["steps"][0]["detail"])
    assert saved.stations[0].coverage_mm == (500, 500, 1060, 1220)
    site = client.get("/api/site").json()["site"]
    assert site["extent_mm"] == [1060, 1220]
    (field,) = site["areas"]
    assert (field["x"], field["y"], field["w"], field["h"]) == (500, 500, 1060, 1220)


def test_a_drag_from_a_drafted_origin_keeps_the_extent_size(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    _, base = _loaded(client)
    first = {"dx_mm": -500, "dy_mm": -500}
    drafted = _frame(client, cal, base, first)["site"]
    # The origin dragged 130 mm right and 140 mm down from where the draft has it
    moved = _frame(
        client, cal, drafted, {"dx_mm": -370, "dy_mm": -360}, base=base, start=first
    )
    assert moved["site"]["extent_mm"] == [1060, 1220]
    (field,) = moved["site"]["areas"]
    assert (field["x"], field["y"]) == (370, 360)


def test_a_turn_turns_the_extent_rigidly_about_the_pivot(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    _, site = _loaded(client)
    # The field, the extent's own rectangle, stays on the floor as the box
    # round it once turned; the extent turns with the frame at its own size
    move = {"theta_deg": 2, "pivot": [530, 610], "dx_mm": 0, "dy_mm": 0}
    moved = _frame(client, cal, site, move)
    assert moved["site"]["extent_mm"] == [1060, 1220]
    (field,) = moved["site"]["areas"]
    x0, y0, x1, y1 = Move(**move).floor().box((0, 0, 1060, 1220))
    assert (field["x"], field["y"], field["w"], field["h"]) == (
        x0,
        y0,
        x1 - x0,
        y1 - y0,
    )
    assert x0 < 0 and x1 > 1060


def test_a_resize_from_the_left_shifts_the_origin_and_keeps_the_floor(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    revision, site = _loaded(client)
    # The left edge dragged 50 mm in, the right edge staying on the floor:
    # zero moves 50 mm right and the extent is 50 mm narrower
    site["extent_mm"] = [1010, 1220]
    move = {"dx_mm": 50, "dy_mm": 0}
    moved = _frame(client, cal, site, move)
    assert moved["site"]["extent_mm"] == [1010, 1220]
    assert moved["coverage"]["0"] == [0, 0, 1010, 1220]
    (field,) = moved["site"]["areas"]
    assert (field["x"], field["w"]) == (-50, 1060)
    body = _save(client, moved["site"], source=cal.id, frame=move)
    assert body["ok"] is True, body
    saved = read_calibration_file(body["steps"][0]["detail"])
    assert saved.stations[0].coverage_mm == (0, 0, 1010, 1220)
    assert client.get("/api/site").json()["site"]["extent_mm"] == [1010, 1220]


def test_a_resize_from_the_top_shifts_the_origin_along_y(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    _, site = _loaded(client)
    # The top edge dragged 200 mm out: zero moves 200 mm up
    site["extent_mm"] = [1060, 1420]
    moved = _frame(client, cal, site, {"dx_mm": 0, "dy_mm": -200})
    assert moved["site"]["extent_mm"] == [1060, 1420]
    assert moved["coverage"]["0"] == [0, 200, 1060, 1420]
    (field,) = moved["site"]["areas"]
    assert (field["x"], field["y"]) == (0, 200)


def test_a_resize_from_the_right_or_bottom_changes_the_size_only(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    _, site = _loaded(client)
    site["extent_mm"] = [800, 1300]
    body = _save(client, site)
    assert [s["step"] for s in body["steps"]] == ["site.toml"]
    site = client.get("/api/site").json()["site"]
    assert site["extent_mm"] == [800, 1300]
    (field,) = site["areas"]
    assert (field["x"], field["y"], field["w"], field["h"]) == (0, 0, 1060, 1220)


def test_spin_circles_left_outside_the_extent_are_a_warning_not_a_refusal(
    tmp_path, home, spun
):  # noqa: F811
    client, cal = _bench(tmp_path, spun)
    _, site = _loaded(client)
    moved = _frame(client, cal, site, {"dx_mm": -700, "dy_mm": 0})
    assert any("land outside the site's extent" in w for w in moved["warnings"])


def test_a_move_a_robot_could_not_take_is_refused_with_the_largest_shift(
    editor, placed, home  # noqa: F811
):
    client, _, _ = editor
    revision, site = _loaded(client)
    refused = client.post(
        "/api/frame",
        json={
            "calibration": placed.id,
            "site": site,
            "base": site,
            "move": {"dx_mm": 5000},
        },
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "below zero" in detail["message"]
    assert 0 < detail["offer"]["dx_mm"] < 5000
    files = _calibrations(home)
    saved = client.post(
        "/api/apply",
        json={
            "revision": revision,
            "site": site,
            "calibration": {"source": placed.id, "frame": {"dx_mm": 5000}},
        },
    )
    assert saved.status_code == 422
    assert _calibrations(home) == files


def test_a_turn_keeps_points_on_the_floor_and_turns_headings():
    move = Move(theta_deg=90, pivot=(0, 0), dy_mm=-1000)
    model = {
        "anchor": "a",
        "extent_mm": [1000, 1000],
        "areas": [{"name": "a", "x": 0, "y": 0, "w": 100, "h": 200, "was": "a"}],
        "objects": [
            {"name": "p", "kind": "dock", "x": 0, "y": 100, "heading_deg": 0.0}
        ],
    }
    out = moved_site(model, move.floor())
    (area,) = out["areas"]
    assert (area["x"], area["y"], area["w"], area["h"]) == (0, 900, 200, 100)
    assert (out["objects"][0]["x"], out["objects"][0]["y"]) == (100, 1000)
    assert out["objects"][0]["heading_deg"] == -90.0
    assert out["extent_mm"] == [1000, 1000]


def test_a_shift_keeps_the_extent_size_and_lets_numbers_go_below_zero():
    move = Move(dx_mm=300, dy_mm=-100)
    model = {
        "extent_mm": [1000, 800],
        "areas": [{"name": "a", "x": 100, "y": 0, "w": 500, "h": 500, "was": "a"}],
        "walls": [{"points": [[0, 0], [1000, 0]], "was": 0}],
    }
    out = moved_site(model, move.floor())
    assert out["extent_mm"] == [1000, 800]
    (area,) = out["areas"]
    assert (area["x"], area["y"], area["w"], area["h"]) == (-200, 100, 500, 500)
    assert out["walls"][0]["points"] == [[-300, 100], [700, 100]]


def test_a_second_move_starts_from_the_first():
    first = Move(dx_mm=-100)
    second = Move(dx_mm=-300, dy_mm=-50)
    step = between(first, second)
    assert step.apply([(100, 0)])[0] == pytest.approx((300, 50))
    assert between(None, second).apply([(0, 0)])[0] == pytest.approx((300, 50))
