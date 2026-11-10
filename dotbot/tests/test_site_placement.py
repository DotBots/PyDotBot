# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's calibration routes: list, draw and place a spin
calibration, never writing the file it was loaded from."""

import dataclasses
from pathlib import Path

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
    (pack / "site.toml").write_text(ARENA, newline="\n")
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


@pytest.fixture
def placed(client, spun, home):
    body = client.post(
        f"/api/calibrations/{spun.id8}/place",
        json={"dx_mm": 100, "dy_mm": 200, "theta_deg": 0},
    ).json()
    return read_calibration_file(body["path"])


def test_the_listing_says_which_calibrations_are_in_the_site_s_frame(
    client, spun, placed
):
    listed = {c["id"]: c["in_frame"] for c in client.get("/api/calibrations").json()}
    assert listed == {spun.id: False, placed.id: True}
    assert client.get(f"/api/calibrations/{placed.id8}").json()["frame_refusal"] is None
    refusal = client.get(f"/api/calibrations/{spun.id8}").json()["frame_refusal"]
    assert "free-mode spin calibration" in refusal


def test_boxes_write_a_new_calibration_with_only_the_rectangles_changed(client, placed):
    source = placed.path.read_bytes()
    revision = client.get("/api/site").json()["revision"]
    response = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"revision": revision, "stations": {"0": [0, 0, 1000, 2000]}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert placed.path.read_bytes() == source
    boxed = read_calibration_file(body["path"])
    assert boxed.id == body["id"] != placed.id
    assert boxed.station(0).valid_mm == (0, 0, 1000, 2000)
    assert boxed.valid_mm == (0, 0, 1000, 2000)
    assert boxed.station(0).homography == placed.station(0).homography
    assert boxed.edited_from == placed.id
    assert boxed.tag == f"{placed.tag}-boxes"
    assert body["stations"][0]["rect"] == [0, 0, 1000, 2000]
    assert body["source"] == placed.id8
    assert body["push"] == f"dotbot swarm calibrate-lh2 push {boxed.id8} --site arena"


def test_boxes_leaving_out_circles_are_saved_with_a_warning(client, placed):
    body = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"stations": {"0": [1500, 3000, 2000, 4000]}},
    ).json()
    (warning,) = body["warnings"]
    assert "leaves out" in warning and "spin circle(s)" in warning


@pytest.mark.parametrize(
    "rect, why",
    [
        ([0, 0, 2500, 4000], "outside the site's extent"),
        ([0, 0, 0, 4000], "is empty"),
    ],
)
def test_boxes_a_robot_cannot_take_are_refused(client, placed, home, rect, why):
    response = client.post(
        f"/api/calibrations/{placed.id}/boxes", json={"stations": {"0": rect}}
    )
    assert response.status_code == 422
    assert why in response.json()["detail"]
    assert len(list((home / "arena").glob("*.toml"))) == 1


def test_boxes_of_a_free_mode_calibration_are_refused(client, spun):
    response = client.post(
        f"/api/calibrations/{spun.id}/boxes", json={"stations": {"0": [0, 0, 10, 10]}}
    )
    assert response.status_code == 422
    assert "free-mode spin calibration" in response.json()["detail"]


def test_boxes_checked_against_an_older_site_toml_are_a_409(client, placed, home):
    response = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"revision": "stale", "stations": {"0": [0, 0, 1000, 2000]}},
    )
    assert response.status_code == 409
    assert len(list((home / "arena").glob("*.toml"))) == 1


def test_the_site_library_groups_box_layouts_by_spin(client, spun, placed):
    boxed = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    ).json()
    library = client.get("/api/calibrations?scope=site").json()
    assert library["site"] == "arena" and library["served"] is None
    # The spin of site "lab" lives in another site's folder, so it is not here
    assert library["count"] == 2 and library["not_placed"] == []
    (group,) = library["groups"]
    assert {r["id"] for r in group["rows"]} == {placed.id, boxed["id"]}
    row = next(r for r in group["rows"] if r["id"] == boxed["id"])
    assert row["in_frame"] is True and row["served"] is False
    assert row["reading"] == "S0 x 0-1000, y 0-2000"
    assert row["stations"][0]["box"] == [0, 0, 1000, 2000]


def test_an_unknown_library_scope_is_refused(client):
    assert client.get("/api/calibrations?scope=fleet").status_code == 422


def test_a_dry_run_names_the_id_and_writes_nothing(client, placed, home):
    before = sorted((home / "arena").iterdir())
    body = client.post(
        f"/api/calibrations/{placed.id}/boxes?dry_run=1",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    ).json()
    assert body["written"] is False and body["existing"] is None
    assert sorted((home / "arena").iterdir()) == before
    saved = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    ).json()
    assert saved["id"] == body["id"]
    again = client.post(
        f"/api/calibrations/{placed.id}/boxes?dry_run=1",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    ).json()
    assert again["existing"]["id"] == saved["id"]


def test_a_standalone_editor_has_no_served_calibration(client):
    body = client.get("/api/context").json()
    assert body["mode"] == "standalone" and body["served"] is None
    assert body["site"] == "arena"


@pytest.fixture
def two_station_spin(home):
    from dotbot.calibration import multi_station as ms
    from dotbot.tests import lh2_multi_fixture as F
    from dotbot.tests.test_calibration_multi_station import floor_grid, two_stations

    a, b = two_stations()
    samples = F.samples(F.spins([a, b], floor_grid([a, b]), noise=0.5, seed=5))
    calibration, _, _ = conics.solve_calibration(samples, Site(name="lab"), tag="two")
    write_calibration(calibration)
    return calibration, ms


def test_coverage_prints_the_show_headline_and_follows_new_boxes(
    client, two_station_spin
):
    calibration, ms = two_station_spin
    body = client.get(f"/api/calibrations/{calibration.id8}/coverage").json()
    expected = ms.error_map_from_calibration(calibration)
    assert body["headline"]["worst_mm"] == pytest.approx(expected.worst_mm, abs=1e-3)
    assert body["headline"]["bound"] == expected.worst_is_bound
    assert body["limit_mm"] == 2.0
    fog = body["fog"]
    assert len(fog["sigma"]) == fog["rows"] * fog["cols"]
    assert set(fog["own"]) == {"0", "1"}
    assert set(body["geometry"]["stations"]) == {"0", "1"}
    x0, y0, x1, y1 = calibration.valid_mm
    mid = (x0 + x1) // 2
    split = {"0": [x0, y0, mid + 100, y1], "1": [mid - 100, y0, x1, y1]}
    import json

    other = client.get(
        f"/api/calibrations/{calibration.id8}/coverage",
        params={"boxes": json.dumps(split)},
    ).json()
    assert other["headline"]["bound"] is False
    refused = client.get(
        f"/api/calibrations/{calibration.id8}/coverage",
        params={"boxes": json.dumps({"0": [10, 0, 5, 5]})},
    )
    assert refused.status_code == 422


def test_a_tag_rename_keeps_the_id_and_the_file(client, home, spun):
    path = spun.path
    before = path.read_text()
    body = client.patch(
        f"/api/calibrations/{spun.id8}", json={"tag": "monday class"}
    ).json()
    assert body["id"] == spun.id and body["tag"] == "monday class"
    assert body["path"] == str(path)
    after = path.read_text()
    assert 'tag = "monday class"' in after
    assert before.replace('tag = "spin"', 'tag = "monday class"') == after


def test_archive_hides_a_file_and_its_full_id_still_finds_it(client, home, spun):
    body = client.patch(f"/api/calibrations/{spun.id8}", json={"archived": True}).json()
    assert "archived" in Path(body["path"]).parts
    assert not spun.path.exists()
    assert client.get(f"/api/calibrations/{spun.id8}").status_code == 404
    assert client.get(f"/api/calibrations/{spun.id}").status_code == 200
    back = client.patch(f"/api/calibrations/{spun.id}", json={"archived": False}).json()
    assert back["path"] == str(spun.path) and spun.path.exists()


def test_a_pack_s_calibration_is_not_renamed(client, tmp_path, spun):
    import shutil

    pack_folder = tmp_path / "arena" / "calibrations"
    pack_folder.mkdir()
    copy = pack_folder / spun.path.name
    shutil.copy(spun.path, copy)
    spun.path.unlink()
    refused = client.patch(f"/api/calibrations/{spun.id8}", json={"tag": "x"})
    assert refused.status_code == 422
    assert "tracked with the pack" in refused.json()["detail"]


def test_an_empty_tag_is_refused(client, spun):
    refused = client.patch(f"/api/calibrations/{spun.id8}", json={"tag": "  "})
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "a tag cannot be empty: archive the file to hide it instead"
    )
    assert 'tag = "spin"' in spun.path.read_text()


def test_a_tag_another_file_of_the_site_carries_is_refused(client, placed):
    boxed = client.post(
        f"/api/calibrations/{placed.id}/boxes",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    ).json()
    refused = client.patch(
        f"/api/calibrations/{boxed['id']}", json={"tag": "Spin-Arena"}
    )
    assert refused.status_code == 422
    assert refused.json()["detail"] == f'tag "Spin-Arena" is already {placed.id8}\'s'
    # Its own tag, and a tag only another site's file carries, are fine
    assert (
        client.patch(
            f"/api/calibrations/{boxed['id']}", json={"tag": boxed["tag"]}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/calibrations/{boxed['id']}", json={"tag": "spin"}
        ).status_code
        == 200
    )


@pytest.fixture
def opened(client, tmp_path, home):
    """An editor on the same pack, opened by a controller whose context is
    the returned dict, changed by a test as it goes."""
    found = {"mode": "controller", "served": None, "next_start": None}
    app = create_app(
        EditorState("arena", tmp_path / "arena", [home / "arena"]),
        tmp_path / "dist",
        context=lambda: found,
    )
    return local_client(app), found


def test_archiving_a_file_the_next_start_names_is_refused_unless_forced(opened, placed):
    client, found = opened
    found["next_start"] = {"spec": placed.id8, "source": "dotbot.local.toml"}
    refused = client.patch(f"/api/calibrations/{placed.id}", json={"archived": True})
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["dependents"] == [
        f"named for the next start: {placed.id8} in dotbot.local.toml"
    ]
    assert detail["message"] == (
        f"{placed.id8} is named for the next start: {placed.id8} in dotbot.local.toml"
    )
    assert placed.path.exists()
    forced = client.patch(
        f"/api/calibrations/{placed.id}", json={"archived": True, "force": True}
    )
    assert forced.status_code == 200, forced.text
    assert "archived" in Path(forced.json()["path"]).parts
    assert not placed.path.exists()


def test_archiving_a_file_a_snapshot_kept_is_refused(opened, placed):
    from dotbot import site_history

    client, _ = opened
    site_history.save_point("arena", "Monday class", b"", placed.id)
    refused = client.patch(f"/api/calibrations/{placed.id}", json={"archived": True})
    assert refused.status_code == 409
    assert refused.json()["detail"]["dependents"] == ["kept in snapshot Monday class"]


def test_archiving_the_served_file_is_refused_even_forced(opened, placed):
    client, found = opened
    found["served"] = {"id": placed.id, "id8": placed.id8}
    refused = client.patch(
        f"/api/calibrations/{placed.id}", json={"archived": True, "force": True}
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["dependents"] == ["in use by this controller"]
    assert "serve another calibration" in detail["message"]
    assert placed.path.exists()


def test_a_rename_breaks_only_a_config_naming_the_file_by_tag(opened, placed):
    client, found = opened
    found["configured"] = {"spec": placed.id8, "source": "dotbot.toml"}
    assert (
        client.patch(
            f"/api/calibrations/{placed.id}", json={"tag": "monday"}
        ).status_code
        == 200
    )
    found["started_with"] = {"spec": "monday", "source": "the command line"}
    refused = client.patch(f"/api/calibrations/{placed.id}", json={"tag": "tuesday"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["dependents"] == [
        "named for the next start: monday in the command line"
    ]
    assert 'tag = "monday"' in placed.path.read_text()
    forced = client.patch(
        f"/api/calibrations/{placed.id}", json={"tag": "tuesday", "force": True}
    )
    assert forced.status_code == 200 and forced.json()["tag"] == "tuesday"
