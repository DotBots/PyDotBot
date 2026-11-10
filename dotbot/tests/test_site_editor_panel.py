# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor inside the console: its routes on the controller, and a
save reaching the live map and a running simulator without a restart."""

import asyncio

import httpx
import pytest
import pytest_asyncio

from dotbot.server import api
from dotbot.site_packs import pack_at
from dotbot.tests.scenario_harness import Scenario

SITE_TOML = """\
anchor = "the door corner"
extent_mm = [2000, 2000]

[areas.field]
x = 0
y = 0
w = 2000
h = 2000
"""

A = "BADCAFE111111111"


@pytest_asyncio.fixture
async def scenario(tmp_path):
    pack = tmp_path / "lab"
    pack.mkdir()
    (pack / "site.toml").write_text(SITE_TOML)
    site = pack_at(str(pack)).site()
    s = Scenario(
        tmp_path,
        [{"address": A, "pos_x": 500, "pos_y": 500, "direction": 0}],
        site=site,
    )
    local = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://127.0.0.1"
    )
    yield s, local, pack
    await local.aclose()
    await s.close()


@pytest.mark.asyncio
async def test_the_panel_edits_the_controller_s_pack(scenario):
    s, local, pack = scenario
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    assert loaded["path"] == str(pack / "site.toml")
    site = loaded["site"]
    for area in site["areas"]:
        area["was"] = area["name"]
    site["walls"] = [{"points": [[0, 1000], [2000, 1000]]}]
    saved = await local.put(
        "/controller/site-editor/api/site",
        json={"revision": loaded["revision"], "site": site},
    )
    assert saved.json()["written"] is True
    # The reload is handed to the controller's loop
    await asyncio.sleep(0.05)
    served = (await local.get("/controller/site")).json()
    assert served["walls"][0]["points"] == [[0, 1000], [2000, 1000]]
    _, name, event = s.controller.events["site"]
    assert name == "site" and event["walls"] == served["walls"]
    assert s.sim.plant.barriers is not None


@pytest.mark.asyncio
async def test_a_robot_stops_at_a_wall_drawn_while_it_runs(scenario):
    s, local, _ = scenario
    await s.run(1.0)
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    site = loaded["site"]
    for area in site["areas"]:
        area["was"] = area["name"]
    site["walls"] = [{"points": [[0, 1000], [2000, 1000]]}]
    await local.put(
        "/controller/site-editor/api/site",
        json={"revision": loaded["revision"], "site": site},
    )
    await asyncio.sleep(0.05)
    await s.waypoints(A, [(500, 1500)], threshold=20)
    await s.run(10.0)
    assert s.robots[A].pos_y < 1000 - 47.5 - 24.5 + 1


@pytest.mark.asyncio
async def test_the_panel_refuses_a_write_for_another_host(scenario):
    s, _, _ = scenario
    assert (await s.client.get("/controller/site-editor/api/site")).status_code == 200
    response = await s.client.post("/controller/site-editor/api/done")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_panel_refuses_another_machine_whatever_its_host(scenario):
    _, _, pack = scenario
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, client=("192.0.2.7", 5000)),
        base_url="http://localhost",
    ) as remote:
        assert (await remote.get("/controller/site-editor/api/site")).status_code == 200
        response = await remote.post("/controller/site-editor/api/done")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_page_on_another_site_cannot_save_through_the_console_s_cors(scenario):
    _, local, pack = scenario
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    loaded["site"]["anchor"] = "moved"
    response = await local.put(
        "/controller/site-editor/api/site",
        json={"revision": loaded["revision"], "site": loaded["site"]},
        headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403
    assert "moved" not in (pack / "site.toml").read_text()


@pytest.mark.asyncio
async def test_a_reload_reaches_the_calibration_session(scenario):
    s, local, _ = scenario
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    loaded["site"]["extent_mm"] = [4000, 3000]
    for area in loaded["site"]["areas"]:
        area["was"] = area["name"]
    await local.put(
        "/controller/site-editor/api/site",
        json={"revision": loaded["revision"], "site": loaded["site"]},
    )
    await asyncio.sleep(0.05)
    assert s.controller.calibration_session.site.extent_mm == (4000, 3000)


@pytest.mark.asyncio
async def test_a_pack_that_no_longer_reads_keeps_the_site(scenario):
    s, _, pack = scenario
    before = s.controller.site
    (pack / "site.toml").write_text("[areas.field\n")
    s.controller.reload_site()
    assert s.controller.site is before


@pytest.mark.asyncio
async def test_the_panel_reboxes_a_calibration_of_its_site(scenario, monkeypatch):
    from dotbot.calibration import conics, lighthouse2
    from dotbot.calibration.lighthouse2 import read_calibration_file
    from dotbot.calibration.placement import Rigid2D, place_calibration, save_new
    from dotbot.site import Site
    from dotbot.tests.test_calibration_conics import CENTRES, track_samples

    s, local, pack = scenario
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", pack.parent / "home")
    spun, _, _ = conics.solve_calibration(track_samples(CENTRES), Site(name="lab"))
    placed, _ = save_new(place_calibration(spun, s.controller.site, Rigid2D(100, 200)))
    response = await local.post(
        f"/controller/site-editor/api/calibrations/{placed.id}/boxes",
        json={"stations": {"0": [0, 0, 1000, 2000]}},
    )
    assert response.status_code == 200, response.text
    boxed = read_calibration_file(response.json()["path"])
    assert boxed.station(0).valid_mm == (0, 0, 1000, 2000)
    assert boxed.edited_from == placed.id


@pytest.mark.asyncio
async def test_a_site_without_a_pack_has_no_panel(tmp_path):
    s = Scenario(tmp_path, [{"address": A, "pos_x": 500, "pos_y": 500}])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://127.0.0.1"
    ) as local:
        response = await local.get("/controller/site-editor/api/site")
    await s.close()
    assert response.status_code == 404


def test_barriers_swapped_away_during_a_tick_leave_the_tick_whole():
    import numpy as np

    from dotbot.sim.barriers import Barriers
    from dotbot.sim.plant import FleetPlant

    barriers = Barriers(walls=[[(0, 1000), (2000, 1000)]])
    plant = FleetPlant(x=[500.0], y=[930.0], heading_deg=[0.0], barriers=barriers)
    refused = barriers.refused

    def swapped(*args):
        plant.barriers = None
        return refused(*args)

    barriers.refused = swapped
    plant.pwm[:] = 60.0
    plant.step(np.zeros(1, dtype=bool))
    assert plant.y[0] == 930.0


@pytest.mark.asyncio
async def test_the_editor_opened_from_the_controller_names_it(scenario):
    _, local, _ = scenario
    body = (await local.get("/controller/site-editor/api/context")).json()
    assert body["mode"] == "controller"
    assert body["served"] is None and body["next_start"] is None
    assert body["controller"]["version"]


def test_the_context_names_the_served_calibration_and_its_source():
    from types import SimpleNamespace

    from dotbot.controller import Controller, ControllerSettings

    settings = ControllerSettings(
        lh2_calibration="4640cfde",
        lh2_calibration_source="the command line",
        lh2_calibration_next="a1b41f12",
        lh2_calibration_next_source="dotbot.local.toml",
    )
    cal = SimpleNamespace(
        id="4640cfde014c7232",
        id8="4640cfde",
        tag="r3",
        created_at="2026-11-09T08:12:50Z",
    )
    fake = SimpleNamespace(settings=settings, calibration=cal)
    body = Controller.editor_context(fake)
    assert body["served"]["id"] == cal.id
    assert body["served"]["source"] == "the command line"
    assert body["next_start"] == {"spec": "a1b41f12", "source": "dotbot.local.toml"}


@pytest_asyncio.fixture
async def served(scenario, tmp_path, monkeypatch):
    from dotbot.calibration import conics, lighthouse2
    from dotbot.site import Site
    from dotbot.tests import lh2_multi_fixture as F
    from dotbot.tests.test_calibration_multi_station import floor_grid, two_stations

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    a, b = two_stations()
    samples = F.samples(F.spins([a, b], floor_grid([a, b]), noise=0.5, seed=5))
    import dataclasses

    cal, _, _ = conics.solve_calibration(samples, Site(name="lab"))
    # Placed in the lab's frame: the anchor is outside the id
    cal = dataclasses.replace(cal, site=Site(name="lab", anchor="the door corner"))
    lighthouse2.write_calibration(cal)
    return (*scenario, cal)


@pytest.mark.asyncio
async def test_serve_switches_the_controller_for_this_run_only(served):
    s, local, _, cal = served
    response = await local.put(
        "/controller/site-editor/api/served", json={"spec": cal.id8}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["served"]["id"] == cal.id
    assert body["served"]["source"] == "the site editor, for this run"
    assert (await local.get("/controller/site")).json()["calibration"]["id"] == cal.id
    assert s.controller.settings.lh2_calibration_next is None


@pytest.mark.asyncio
async def test_serve_at_the_next_start_writes_the_config(served, tmp_path):
    s, local, _, cal = served
    config = tmp_path / "dotbot.local.toml"
    s.controller.settings.lh2_calibration_persist_path = str(config)
    response = await local.put(
        "/controller/site-editor/api/served", json={"spec": cal.id8, "persist": True}
    )
    assert response.status_code == 200, response.text
    assert f'lh2_calibration = "{cal.id8}"' in config.read_text()
    assert response.json()["next_start"]["spec"] == cal.id8


@pytest.mark.asyncio
async def test_serve_refuses_an_unknown_id_and_a_remote_peer(served):
    s, local, _, cal = served
    unknown = await local.put("/controller/site-editor/api/served", json={"spec": "deadbeef"})
    assert unknown.status_code == 422
    remote = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, client=("192.168.1.30", 5000)),
        base_url="http://192.168.1.10",
    )
    refused = await remote.put("/controller/site-editor/api/served", json={"spec": cal.id8})
    await remote.aclose()
    assert refused.status_code == 403
    assert s.controller.calibration is None or s.controller.calibration.id != cal.id


@pytest.mark.asyncio
async def test_a_live_controller_keeps_its_calibration_when_the_note_changes(served):
    from dotbot.calibration.lighthouse2 import check_calibration_site

    s, local, pack, cal = served
    await local.put("/controller/site-editor/api/served", json={"spec": cal.id8})
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    site = loaded["site"]
    for area in site["areas"]:
        area["was"] = area["name"]
    site["anchor"] = "the door corner, under the clock"
    saved = await local.put(
        "/controller/site-editor/api/site",
        json={"revision": loaded["revision"], "site": site},
    )
    assert saved.status_code == 200, saved.text
    await asyncio.sleep(0.05)
    assert s.controller.site.anchor == "the door corner, under the clock"
    assert s.controller.site.frame is not None
    check_calibration_site(s.controller.calibration.site, s.controller.site, None)


@pytest.mark.asyncio
async def test_a_frame_change_is_named_until_robots_hold_it(served):
    s, local, pack, cal = served
    await local.put("/controller/site-editor/api/served", json={"spec": cal.id8})
    revision = (await local.get("/controller/site-editor/api/site")).json()["revision"]
    body = (
        await local.post(
            "/controller/site-editor/api/frame",
            json={"calibration": cal.id8, "theta_deg": 0, "dx_mm": -20, "dy_mm": -20, "revision": revision},
        )
    ).json()
    assert body["ok"] is True, body
    await asyncio.sleep(0.05)
    context = (await local.get("/controller/site-editor/api/context")).json()
    assert context["served"]["id"] == body["calibration"]["id"]
    assert context["frame_change"]["to_frame"] == body["frame"]
    assert context["frame_change"]["from_id"] == cal.id
