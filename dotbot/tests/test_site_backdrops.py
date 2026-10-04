# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What the site editor draws under a site: its calibrations' spans and its
cameras' stills, warped into the frame."""

import dataclasses

import numpy as np
import pytest

from dotbot.calibration import conics
from dotbot.calibration.lighthouse2 import write_calibration
from dotbot.site import Site
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_conics import CENTRES, track_samples
from dotbot.tests.test_site_editor import local_client
from dotbot.tests.test_site_toml import ARENA


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from dotbot.calibration import lighthouse2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(ARENA)
    page = tmp_path / "dist"
    page.mkdir()
    (page / "site-editor.html").write_text("<html></html>")
    home = tmp_path / "home" / "calibrations" / "arena"
    client = local_client(create_app(EditorState("arena", pack, [home]), page))
    return client, home


ARENA_ANCHOR = "the corner where the top wall meets the door wall"


def _placed_spin():
    """A spin calibration recorded against the arena's anchor, as placed."""
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="arena"), tag="spin"
    )
    return dataclasses.replace(
        calibration, site=Site(name="arena", anchor=ARENA_ANCHOR)
    )


def test_a_site_with_no_calibration_has_no_backdrop(setup):
    client, _ = setup
    assert client.get("/api/backdrops").json() == {"calibrations": [], "cameras": []}


def test_a_calibration_of_the_site_is_drawn_by_its_spin_centres(setup):
    client, _ = setup
    calibration = _placed_spin()
    write_calibration(calibration)
    (drawn,) = client.get("/api/backdrops").json()["calibrations"]
    assert drawn["id8"] == calibration.id8
    assert drawn["placements"] == []
    assert len(drawn["centres"]) == len(CENTRES)


def test_a_camera_still_is_warped_onto_its_area(setup):
    cv2 = pytest.importorskip("cv2")
    from dotbot.camera.registration import CameraCalibration, write_camera_calibration
    from dotbot.tests.camera_fixtures import (
        DEV_CORNER,
        ground_truth_px_to_mm,
        synthetic_frame,
    )

    client, home = setup
    camera = CameraCalibration(
        site=Site(name="arena"),
        area="dev-corner",
        width=640,
        height=480,
        matrix=ground_truth_px_to_mm().tolist(),
        created="2026-10-02T10:00:00Z",
    )
    path = write_camera_calibration(camera, root=home.parent)
    cv2.imwrite(str(path.with_suffix(".jpg")), synthetic_frame(DEV_CORNER))
    (listed,) = client.get("/api/backdrops").json()["cameras"]
    assert listed["rect"] == [1000, 0, 1000, 1000]
    still = client.get(listed["still"])
    assert still.status_code == 200
    image = cv2.imdecode(np.frombuffer(still.content, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (200, 200)
    # The area's own floor fills the still: a lost origin leaves it mostly black
    assert (image.max(axis=2) == 0).mean() < 0.2
    assert client.get("/api/backdrops/camera/ffffffff.png").status_code == 404


def _camera(home, area, matrix):
    from dotbot.camera.registration import CameraCalibration, write_camera_calibration

    camera = CameraCalibration(
        site=Site(name="arena"),
        area=area,
        width=640,
        height=480,
        matrix=matrix,
        created="2026-10-02T10:00:00Z",
    )
    return write_camera_calibration(camera, root=home.parent)


def test_a_file_that_cannot_be_read_is_skipped_not_a_500(setup):
    client, home = setup
    calibration = _placed_spin()
    good = write_calibration(calibration)
    text = good.read_text()
    (home / "calibration-broken.toml").write_text(
        text.replace(f'id = "{calibration.id}"', "id = 7")
    )
    (home / "calibration-garbage.toml").write_text("[[placement]]\nhomography = 1\n")
    _camera(home, "dev-corner", [[1.0, 0.0], [0.0, 1.0]])
    response = client.get("/api/backdrops")
    assert response.status_code == 200
    body = response.json()
    assert [c["id8"] for c in body["calibrations"]] == [calibration.id8]
    assert body["cameras"] == []


def test_a_calibration_in_another_frame_is_not_drawn(setup):
    client, _ = setup
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="arena"), tag="spin"
    )
    write_calibration(calibration)
    assert client.get("/api/backdrops").json()["calibrations"] == []


def test_a_still_of_a_huge_area_is_capped(setup):
    cv2 = pytest.importorskip("cv2")
    from dotbot.tests.camera_fixtures import ground_truth_px_to_mm, synthetic_frame

    client, home = setup
    path = _camera(home, "0,0,100000,50000", ground_truth_px_to_mm().tolist())
    cv2.imwrite(str(path.with_suffix(".jpg")), synthetic_frame())
    (listed,) = client.get("/api/backdrops").json()["cameras"]
    still = client.get(listed["still"])
    assert still.status_code == 200
    image = cv2.imdecode(np.frombuffer(still.content, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (2048, 4096)


def test_a_still_url_changes_when_its_area_moves(setup):
    cv2 = pytest.importorskip("cv2")
    from dotbot.tests.camera_fixtures import ground_truth_px_to_mm, synthetic_frame

    client, home = setup
    path = _camera(home, "dev-corner", ground_truth_px_to_mm().tolist())
    cv2.imwrite(str(path.with_suffix(".jpg")), synthetic_frame())
    before = client.get("/api/backdrops").json()["cameras"][0]["still"]
    site = home.parent.parent.parent / "arena" / "site.toml"
    site.write_text(site.read_text().replace("x = 1000", "x = 900"))
    after = client.get("/api/backdrops").json()["cameras"][0]["still"]
    assert before != after
