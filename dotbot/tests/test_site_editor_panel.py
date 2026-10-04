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
async def test_the_panel_refuses_another_host(scenario):
    s, _, _ = scenario
    response = await s.client.get("/controller/site-editor/api/site")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_panel_refuses_another_machine_whatever_its_host(scenario):
    _, _, pack = scenario
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, client=("192.0.2.7", 5000)),
        base_url="http://localhost",
    ) as remote:
        response = await remote.get("/controller/site-editor/api/site")
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
