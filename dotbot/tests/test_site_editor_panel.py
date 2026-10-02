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
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_site_without_a_pack_has_no_panel(tmp_path):
    s = Scenario(tmp_path, [{"address": A, "pos_x": 500, "pos_y": 500}])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://127.0.0.1"
    ) as local:
        response = await local.get("/controller/site-editor/api/site")
    await s.close()
    assert response.status_code == 404
