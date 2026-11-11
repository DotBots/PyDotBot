# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One ordered Save, and the site.toml versions kept to undo it."""

from datetime import datetime, timedelta, timezone

from dotbot import site_history
from dotbot.calibration.lighthouse2 import read_calibration_file
from dotbot.tests.test_site_placement import client, home, placed, spun  # noqa: F401


def _with_area(site: dict, name: str) -> dict:
    areas = [{**a, "was": a["name"]} for a in site["areas"]]
    return {
        **site,
        "areas": areas + [{"name": name, "x": 0, "y": 0, "w": 100, "h": 100}],
    }


def test_a_refused_second_step_leaves_site_toml_written_and_reports_both(
    client, placed  # noqa: F811
):
    loaded = client.get("/api/site").json()
    body = client.post(
        "/api/apply",
        json={
            "revision": loaded["revision"],
            "site": _with_area(loaded["site"], "pen"),
            "boxes_of": placed.id,
            "boxes": {"stations": {"0": [0, 0, 99999, 2000]}},
        },
    ).json()
    assert body["ok"] is False
    assert [(s["step"], s["status"]) for s in body["steps"]] == [
        ("site.toml", "written"),
        ("calibration", "refused"),
    ]
    assert "extent" in body["steps"][1]["detail"]
    assert body["revision"] != loaded["revision"]
    assert "pen" in [a["name"] for a in client.get("/api/site").json()["site"]["areas"]]


def test_both_steps_write_in_order(client, placed):  # noqa: F811
    loaded = client.get("/api/site").json()
    body = client.post(
        "/api/apply",
        json={
            "revision": loaded["revision"],
            "site": _with_area(loaded["site"], "pen"),
            "boxes_of": placed.id,
            "boxes": {"stations": {"0": [0, 0, 1000, 2000]}},
        },
    ).json()
    assert body["ok"] is True
    site_step, cal_step = body["steps"]
    assert site_step["status"] == "written"
    boxed = read_calibration_file(cal_step["detail"])
    assert boxed.id == cal_step["id"] and boxed.station(0).coverage_mm == (
        0,
        0,
        1000,
        2000,
    )


def test_a_stale_revision_writes_nothing(client):  # noqa: F811
    loaded = client.get("/api/site").json()
    response = client.post(
        "/api/apply",
        json={"revision": "0" * 64, "site": _with_area(loaded["site"], "pen")},
    )
    assert response.status_code == 409
    assert client.get("/api/site").json()["revision"] == loaded["revision"]
    assert client.get("/api/history").json() == []


def test_a_save_is_undone_from_the_history(client):  # noqa: F811
    loaded = client.get("/api/site").json()
    saved = client.post(
        "/api/apply",
        json={
            "revision": loaded["revision"],
            "site": _with_area(loaded["site"], "pen"),
        },
    ).json()
    (kept,) = client.get("/api/history").json()
    assert kept["revision"] == loaded["revision"]
    restored = client.post(
        "/api/restore", json={"version": kept["id"], "revision": saved["revision"]}
    ).json()
    assert restored["revision"] == loaded["revision"]
    # The restore is kept too, so it can itself be undone
    assert [v["revision"] for v in client.get("/api/history").json()] == [
        saved["revision"],
        loaded["revision"],
    ]


def test_the_history_keeps_the_last_twenty(home):  # noqa: F811
    t0 = datetime(2026, 11, 10, tzinfo=timezone.utc)
    for i in range(25):
        site_history.snapshot("arena", f"v{i}".encode(), now=t0 + timedelta(seconds=i))
    kept = site_history.versions("arena")
    assert len(kept) == site_history.KEEP
    assert site_history.read_version("arena", kept[0]["id"]) == b"v24"


def test_the_payload_carries_the_file_text_for_the_diff(client):  # noqa: F811
    loaded = client.get("/api/site").json()
    from dotbot.tests.test_site_toml import ARENA

    assert loaded["text"] == ARENA
