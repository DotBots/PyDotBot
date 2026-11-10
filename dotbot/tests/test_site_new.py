# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A new room without a terminal: the new site's pack, the controller taking
it at run time, and a spin run from the controller on simulated robots."""

import asyncio

import httpx
import pytest
import pytest_asyncio

from dotbot.calibration import lighthouse2, simulated
from dotbot.calibration.conics import is_free_mode
from dotbot.server import api
from dotbot.site_new import NewSiteRefused, write_new_site
from dotbot.site_packs import read_pack
from dotbot.tests.scenario_harness import Scenario

ROBOTS = [
    ("A0000000000000A1", 300, 300),
    ("A0000000000000B2", 800, 350),
    ("A0000000000000C3", 550, 700),
    ("A0000000000000D4", 300, 1000),
    ("A0000000000000E5", 850, 1000),
    ("A0000000000000F6", 560, 1150),
]


def test_an_empty_site_holds_its_note_and_nothing_else(tmp_path):
    written = write_new_site(tmp_path, "bench-b", "empty", note="the door's hinge")
    pack = read_pack(written.pack)
    assert pack.anchor == "the door's hinge"
    assert pack.extent_mm is None and not pack.areas


def test_a_known_size_writes_the_floor(tmp_path):
    written = write_new_site(tmp_path, "bench-b", "size", size_mm=(3000, 2000))
    assert read_pack(written.pack).extent_mm == (3000, 2000)


@pytest.mark.parametrize("name", ["a-name-of-17-char", "with space", "café"])
def test_a_name_robots_cannot_carry_is_refused(tmp_path, name):
    with pytest.raises(NewSiteRefused):
        write_new_site(tmp_path, name)
    assert not any(tmp_path.iterdir())


def test_an_existing_site_is_not_replaced(tmp_path):
    write_new_site(tmp_path, "bench-b", "size", size_mm=(1000, 1000))
    with pytest.raises(NewSiteRefused, match="already exists"):
        write_new_site(tmp_path, "bench-b")
    assert read_pack(tmp_path / "bench-b").extent_mm == (1000, 1000)


def test_a_spin_client_s_reads_solve_two_stations():
    from dotbot.calibration.conics import solve_calibration
    from dotbot.calibration.spin import SpinAssembler
    from dotbot.site import Site

    client = simulated.SimulatedSpinClient(
        lambda: {a: (x, y) for a, x, y in ROBOTS}, 51.4
    )
    assembler = SpinAssembler()
    for address, x, y in ROBOTS:
        for event in client.events_of(address, (x, y)):
            assembler.add_event(event)
    samples = [s for spin in assembler.by_device().values() for s in spin.samples(51.4)]
    calibration, _, unsolved = solve_calibration(samples, Site(name="lab"))
    assert not unsolved and is_free_mode(calibration)
    assert sorted(st.index for st in calibration.stations) == [0, 1]


@pytest_asyncio.fixture
async def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    monkeypatch.setattr(simulated, "SPIN_START_DELAY_S", 0.0)
    monkeypatch.setattr(simulated, "SPIN_CHUNK_GAP_S", 0.0)
    monkeypatch.setattr("dotbot.calibration.spin.SPIN_POLL_INTERVAL", 0.02)
    monkeypatch.setattr("dotbot.calibration.push.STOP_POLL_INTERVAL", 0.01)
    homes = tmp_path / "sites"
    homes.mkdir()
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", homes)
    s = Scenario(
        tmp_path,
        [{"address": a, "pos_x": x, "pos_y": y, "direction": 0} for a, x, y in ROBOTS],
    )
    local = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://127.0.0.1"
    )
    await s.run(1.0)
    yield s, local, homes
    await local.aclose()
    await s.close()


@pytest.mark.asyncio
async def test_with_no_site_pack_the_editor_offers_new_site_and_takes_it(lab):
    s, local, homes = lab
    context = (await local.get("/controller/site-editor/api/context")).json()
    assert context["no_site"] is True
    assert (await local.get("/controller/site-editor/api/site")).status_code == 404
    made = await local.post(
        "/controller/site-editor/api/sites",
        json={"name": "bench-b", "note": "the door's hinge", "start": "empty"},
    )
    assert made.status_code == 200, made.text
    await asyncio.sleep(0.05)
    assert (homes / "bench-b" / "site.toml").is_file()
    assert s.controller.site.name == "bench-b"
    loaded = (await local.get("/controller/site-editor/api/site")).json()
    assert loaded["site"]["anchor"] == "the door's hinge"
    listed = (await local.get("/controller/site-editor/api/sites")).json()
    assert [r["name"] for r in listed["sites"] if r["current"]] == ["bench-b"]


@pytest.mark.asyncio
async def test_new_site_refuses_another_machine(lab):
    _, _, homes = lab
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, client=("192.0.2.7", 5000)),
        base_url="http://localhost",
    ) as remote:
        response = await remote.post(
            "/controller/site-editor/api/sites", json={"name": "bench-b"}
        )
    assert response.status_code == 403
    assert not (homes / "bench-b").exists()


@pytest.mark.asyncio
async def test_a_spin_from_the_controller_saves_a_free_calibration(lab):
    s, local, _ = lab
    await local.post("/controller/site-editor/api/sites", json={"name": "bench-b"})
    await asyncio.sleep(0.05)
    started = await local.post("/controller/calibration/spin", json={"tag": "r1"})
    assert started.status_code == 200, started.text
    assert len(started.json()["robots"]) == len(ROBOTS)
    for _ in range(400):
        await asyncio.sleep(0.05)
        state = (await local.get("/controller/calibration/spin")).json()
        if state["phase"] in ("saved", "failed"):
            break
    assert state["phase"] == "saved", state["error"]
    _, name, event = s.controller.events["calibration_spin"]
    assert name == "calibration_spin" and event["phase"] == "saved"
    result = state["result"]
    assert [st["index"] for st in result["stations"]] == [0, 1]
    saved = lighthouse2.load_calibration(result["id"], site="bench-b")
    assert is_free_mode(saved) and saved.tag == "r1"
    # A second spin while none runs is fine; a mark session blocks one
    assert (await local.delete("/controller/calibration/spin")).status_code == 200
