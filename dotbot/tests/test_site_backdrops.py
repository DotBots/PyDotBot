# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What the site editor draws under a site: its calibrations' spans and its
cameras' stills, warped into the frame."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dotbot.calibration import conics
from dotbot.calibration.lighthouse2 import write_calibration
from dotbot.site import Site
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_calibration_conics import CENTRES, track_samples
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
    client = TestClient(
        create_app(EditorState("arena", pack, [home]), page),
        base_url="http://127.0.0.1",
    )
    return client, home


def test_a_site_with_no_calibration_has_no_backdrop(setup):
    client, _ = setup
    assert client.get("/api/backdrops").json() == {"calibrations": [], "cameras": []}


def test_a_calibration_of_the_site_is_drawn_by_its_spin_centres(setup):
    client, _ = setup
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="arena"), tag="spin"
    )
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
    assert client.get("/api/backdrops/camera/ffffffff.png").status_code == 404
