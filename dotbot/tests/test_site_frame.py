# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The frame id: derived for files without one, compared wherever the anchor
was, stamped before the note on zero changes, and moved as one change."""

import dataclasses

import pytest

from dotbot.calibration import lighthouse2, site_frame, site_turn
from dotbot.calibration.lighthouse2 import check_calibration_site, write_calibration
from dotbot.calibration.station_boxes import frame_refusal, reboxed
from dotbot.site import Site, derived_frame_id
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_station_boxes import ARENA, free, placed  # noqa: F401
from dotbot.tests.test_site_editor import local_client

SITE_TOML = """\
anchor = "the door corner"
extent_mm = [3000, 4000]

[areas.field]
x = 0
y = 0
w = 3000
h = 4000
"""


def test_a_file_without_a_frame_derives_the_inria_2lh_id():
    anchor = (
        "top-left of the rectangle around 4 robots on the Inria bench (2026-11-09), "
        "grown by 200 mm; zero is (80, -530) mm in spin calibration 91e5e710's "
        "frame, axes along it"
    )
    assert Site(name="inria-2lh", anchor=anchor).frame_id == "f0237ffd"


def test_check_calibration_site_accepts_a_file_lacking_the_key(placed):  # noqa: F811
    assert placed.site.frame is None
    check_calibration_site(placed.site, ARENA, None)
    stamped = dataclasses.replace(ARENA, frame=derived_frame_id("arena", ARENA.anchor), anchor="a new note")
    check_calibration_site(placed.site, stamped, None)
    with pytest.raises(ValueError, match="is in frame"):
        check_calibration_site(placed.site, dataclasses.replace(ARENA, frame="0badf00d"), None)


def test_rebox_and_turn_accept_a_file_lacking_the_key(placed, tmp_path, monkeypatch):  # noqa: F811
    stamped = dataclasses.replace(ARENA, frame=derived_frame_id("arena", ARENA.anchor), anchor="edited")
    assert frame_refusal(placed.site, stamped) is None
    boxed = reboxed(placed, stamped, {0: (0, 0, 1500, 4000)})
    assert boxed.site.frame is None and boxed.site.anchor == placed.site.anchor
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    path = write_calibration(placed)
    assert [c.id for c in site_turn.in_frame(stamped, [path])] == [placed.id]


def test_the_controller_load_accepts_a_file_lacking_the_key(placed, tmp_path, monkeypatch):  # noqa: F811
    from dotbot.controller import load_calibration

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    write_calibration(placed)
    stamped = dataclasses.replace(ARENA, frame=derived_frame_id("arena", ARENA.anchor), anchor="edited")
    assert load_calibration(placed.id8, site=stamped).id == placed.id


@pytest.fixture
def editor(tmp_path, monkeypatch, placed):  # noqa: F811
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    write_calibration(placed)
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(SITE_TOML)
    served = []
    app = create_app(
        EditorState("arena", pack, [tmp_path / "home" / "calibrations" / "arena"]),
        page_dir=None,
        serve=lambda spec, persist: served.append(spec) or {"served": {"id": spec}},
    )
    return local_client(app), pack, served


def test_editing_the_note_writes_the_derived_frame_first(editor):
    client, pack, _ = editor
    body = client.get("/api/site").json()
    site = body["site"]
    for area in site["areas"]:
        area["was"] = area["name"]
    site["anchor"] = "the door corner, by the window"
    saved = client.put("/api/site", json={"revision": body["revision"], "site": site})
    assert saved.status_code == 200, saved.text
    text = (pack / "site.toml").read_text()
    assert f'frame = "{derived_frame_id("arena", "the door corner")}"' in text
    assert 'anchor = "the door corner, by the window"' in text


def test_a_turn_with_a_shift_below_zero_is_refused_with_the_largest_legal_shift(editor, placed):  # noqa: F811
    client, _, _ = editor
    revision = client.get("/api/site").json()["revision"]
    refused = client.post(
        "/api/frame",
        json={"calibration": placed.id8, "theta_deg": 0, "pivot": [1500, 2000], "dx_mm": 5000, "revision": revision},
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "below zero" in detail["message"]
    assert 0 < detail["offer"]["dx_mm"] < 5000


def test_the_frame_change_writes_the_file_the_site_and_serves_in_order(editor, placed):  # noqa: F811
    client, pack, served = editor
    revision = client.get("/api/site").json()["revision"]
    body = client.post(
        "/api/frame",
        json={"calibration": placed.id8, "theta_deg": 2, "pivot": [1500, 2000], "revision": revision},
    ).json()
    assert [s["step"] for s in body["steps"]] == ["calibration", "site.toml", "serve"]
    assert body["ok"] is True
    new = lighthouse2.read_calibration_file(body["steps"][0]["detail"])
    assert new.site.frame == body["frame"] != body["from_frame"]
    assert f'frame = "{body["frame"]}"' in (pack / "site.toml").read_text()
    assert served == [new.id]
    site = Site(name="arena", anchor="the door corner", frame=body["frame"])
    assert frame_refusal(placed.site, site) is not None
    assert frame_refusal(new.site, site) is None


def test_the_new_frame_id_follows_the_move():
    a = site_frame.new_frame_id("f0237ffd", 2, (530, 610), (0, 0))
    assert a != site_frame.new_frame_id("f0237ffd", 2, (530, 610), (10, 0))
    assert a == site_frame.new_frame_id("f0237ffd", 2.0, (530.0, 610.0), (0.0, 0.0))
