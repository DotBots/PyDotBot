# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's calibration routes: list, draw and place a spin
calibration, never writing the file it was loaded from."""

import dataclasses

import pytest

from dotbot.calibration import conics, lighthouse2
from dotbot.calibration.lighthouse2 import read_calibration_file, write_calibration
from dotbot.calibration.placement import Rigid2D, spin_centres
from dotbot.site import Site
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_conics import CENTRES, track_samples
from dotbot.tests.test_site_editor import local_client
from dotbot.tests.test_site_toml import ARENA


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    return tmp_path / "home" / "calibrations"


@pytest.fixture
def spun(home):
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab"), tag="spin"
    )
    write_calibration(calibration)
    return calibration


@pytest.fixture
def client(tmp_path, home):
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(ARENA)
    page = tmp_path / "dist"
    page.mkdir()
    (page / "site-editor.html").write_text("<html></html>")
    return local_client(create_app(EditorState("arena", pack, [home / "arena"]), page))


def test_the_calibrations_are_listed_with_their_kind(client, spun):
    listed = client.get("/api/calibrations").json()
    assert [
        (c["id"], c["site"], c["tag"], c["free"], c["stations"]) for c in listed
    ] == [(spun.id, "lab", "spin", True, [0])]


def test_a_calibration_is_drawn_by_id_in_its_own_frame(client, spun):
    body = client.get(f"/api/calibrations/{spun.id8}").json()
    assert body["id"] == spun.id and body["free"] is True
    (station,) = body["stations"]
    assert (station["index"], station["channel"]) == (0, 1)
    assert len(station["centres"]) == len(CENTRES)
    assert body["fence"] == station["rect"] == list(spun.valid_mm)
    assert body["links"] == []


def test_an_unknown_calibration_is_a_404(client, spun):
    assert client.get("/api/calibrations/ffffffff").status_code == 404


def test_a_placement_writes_a_new_calibration_and_keeps_the_original(
    client, spun, home
):
    source = spun.path.read_bytes()
    body = client.post(
        f"/api/calibrations/{spun.id8}/place",
        json={"dx_mm": 100, "dy_mm": 200, "theta_deg": 0},
    ).json()
    assert spun.path.read_bytes() == source
    placed = read_calibration_file(home / "arena" / body["path"].split("/")[-1])
    assert placed.id == body["id"] != spun.id
    assert placed.site.name == "arena"
    assert placed.site.anchor == "the corner where the top wall meets the door wall"
    assert placed.valid_mm == (0, 0, 2000, 4000)
    assert body["push"] == (
        f"dotbot swarm calibrate-lh2 push {placed.id8} --site arena --site-changed"
    )
    move = Rigid2D(100, 200, 0)
    before = spin_centres(spun)[0]
    after = spin_centres(placed)[0]
    for a, b in zip(before, after):
        assert (b["x"], b["y"]) == pytest.approx(
            move.apply([(a["x"], a["y"])])[0], abs=0.1
        )


def test_a_corner_calibration_is_refused_unless_re_anchored(client, spun):
    corner = dataclasses.replace(
        spun,
        stations=[
            dataclasses.replace(st, solved_from="direct") for st in spun.stations
        ],
        tag="corner",
    )
    write_calibration(corner)
    listed = {c["tag"]: c["free"] for c in client.get("/api/calibrations").json()}
    assert listed == {"spin": True, "corner": False}
    refused = client.post("/api/calibrations/corner/place", json={"dx_mm": 10})
    assert refused.status_code == 422
    assert "collected at points of the room" in refused.json()["detail"]
    moved = client.post(
        "/api/calibrations/corner/place", json={"dx_mm": 10, "reanchor": True}
    )
    assert moved.status_code == 200
    assert any("re-anchored" in w for w in moved.json()["warnings"])


def test_placing_twice_the_same_way_keeps_the_first_file(client, spun, home):
    move = {"dx_mm": 100, "dy_mm": 200, "theta_deg": 0}
    first = client.post(f"/api/calibrations/{spun.id8}/place", json=move).json()
    written = (home / "arena" / first["path"].split("/")[-1]).read_bytes()
    second = client.post(f"/api/calibrations/{spun.id8}/place", json=move).json()
    assert (second["id"], second["tag"], second["path"]) == (
        first["id"],
        first["tag"],
        first["path"],
    )
    assert len(list((home / "arena").glob("*.toml"))) == 1
    assert (home / "arena" / first["path"].split("/")[-1]).read_bytes() == written
    assert client.get(f"/api/calibrations/{first['tag']}").status_code == 200


def test_a_placement_below_zero_is_refused(client, spun):
    refused = client.post(
        f"/api/calibrations/{spun.id8}/place", json={"theta_deg": 180}
    )
    assert refused.status_code == 422
    assert "below zero" in refused.json()["detail"]


def test_a_placement_outside_the_extent_is_saved_with_a_warning(client, spun):
    body = client.post(
        f"/api/calibrations/{spun.id8}/place", json={"dx_mm": 1500}
    ).json()
    assert any("outside the site's extent" in w for w in body["warnings"])
