# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the calibration session the controller owns.

The session is the capture loop with one point outstanding at a time; the
driver is the controller's side of it, with its transport and its
notifications. Both are exercised with the swarmit client faked, which
stands in for the SwarmitClient surface and never for Mari/MQTT/serial
behaviour - none of this is hardware validation.
"""

import asyncio
import queue
import re
from types import SimpleNamespace

import pytest

from dotbot.area import Area
from dotbot.calibration import lighthouse2
from dotbot.calibration.driver import SessionDriver
from dotbot.calibration.lighthouse2 import (
    LH2_CALIBRATION_MESSAGE_BYTES,
    LH2CalibrationSample,
    message_site,
    read_calibration_file,
)
from dotbot.calibration.ota import ButtonCapture, CaptureSession
from dotbot.calibration.points import CORNERS, PointsFrom
from dotbot.calibration.session import CalibrationSession, SessionError
from dotbot.site import Site

C405 = Site(
    name="c405-arena",
    anchor="the arena's top-left corner, against the door wall of C405",
    extent_mm=(2000, 4000),
    areas={
        "arena": Area(0, 0, 2000, 2000, "arena"),
        "annex": Area(0, 2000, 2000, 2000, "annex"),
    },
)

# One plausible count pair per corner, distinct enough that the four solve.
CORNER_COUNTS = [
    (41290, 51728),
    (40877, 51102),
    (43166, 75717),
    (42810, 75104),
]


def _record(lh_index: int, count1: int, count2: int) -> bytes:
    return (
        bytes([lh_index]) + count1.to_bytes(4, "little") + count2.to_bytes(4, "little")
    )


def _reads(lh_index: int, count1: int, count2: int) -> list:
    """One read: one station's record."""
    return [LH2CalibrationSample(lh_index, count1, count2)]


def _press(
    lh_index: int, count1: int, count2: int, n: int = 1, device: str = "ABCD"
) -> ButtonCapture:
    """One button capture of `n` identical reads from one station."""
    return ButtonCapture(
        device=device, press=0, reads=[_reads(lh_index, count1, count2)] * n
    )


async def _store(driver, capture: ButtonCapture) -> None:
    await asyncio.wrap_future(driver.on_button_capture(capture))


def _info(version=4, site="", calibration_id=""):
    """A robot's device info as swarmit decodes it."""
    return SimpleNamespace(
        info_version=version,
        info_gen=1,
        lh2_site_name=site,
        lh2_calibration_id=calibration_id,
        lh2_station_mask=0,
    )


class _FakeClient:
    """The swarmit client surface a session pushes and listens through."""

    def __init__(self, device: str = "ABCD"):
        self.device = device.upper()
        self.pushed: list[bytes] = []
        self.entered = 0
        self.infos = {self.device: _info()}

    def send_lh2_calibration(self, payload: bytes, devices=None) -> None:
        self.pushed.append(payload)
        self.pushed_to = devices
        # The bot commits the push, resets and reports its site, id and stations.
        for addr, info in self.infos.items():
            if devices is not None and addr not in devices:
                continue
            if info is not None and info.info_version >= 4:
                info.lh2_site_name, info.lh2_calibration_id = message_site(
                    payload[:LH2_CALIBRATION_MESSAGE_BYTES]
                )
                info.lh2_station_mask = int.from_bytes(payload[:4], "little")
                info.info_gen += 1

    def refresh_device_info(self, devices=None) -> None:
        pass

    def status(self):
        return {
            addr: SimpleNamespace(info_gen=1, info=info)
            for addr, info in self.infos.items()
        }

    def watch_log_events(self):
        return iter(())

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *exc):
        return False


def _driver(client=None, site=C405, notify=None):
    client = client or _FakeClient()
    seen: list = []

    async def record(state):
        seen.append(state)

    driver = SessionDriver(
        client_factory=lambda: client,
        notify=notify or record,
        site=site,
        stream_factory=lambda c, on_button: CaptureSession(
            c, on_button_capture=on_button
        ),
    )
    return driver, client, seen


async def _walk(driver):
    """Capture all four corners from the button, one per corner's counts."""
    for index in range(4):
        await _store(driver, _press(0, *CORNER_COUNTS[index]))


# --- the points a session opens on ------------------------------------------


def test_a_session_resolves_four_corner_points_with_point_zero_outstanding():
    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    state = session.as_dict()
    assert state["total"] == 4
    assert state["outstanding"] == 0
    assert state["captured"] == 0
    assert state["device"] == ""
    assert [p["corner"] for p in state["points"]] == list(CORNERS)
    # The edge-aligned photodiode marks of the arena, inset by the geometry.
    assert [(p["x"], p["y"]) for p in state["points"]] == [
        (47, 18.5),
        (1953, 18.5),
        (47, 1981.5),
        (1953, 1981.5),
    ]


def test_a_point_carries_the_same_placement_text_collect_prints():
    from dotbot.calibration.points import resolve_points

    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    printed = resolve_points("arena:corners", C405.registry())
    assert [p["where"] for p in session.as_dict()["points"]] == [
        p.where for p in printed
    ]
    assert [p["how"] for p in session.as_dict()["points"]] == [p.how for p in printed]


def test_a_session_given_no_points_opens_on_the_fields_corners():
    site = Site(
        name="c405-arena",
        areas={
            "staging": Area(0, 2000, 2000, 2000, "staging", "staging"),
            "field": Area(0, 0, 2000, 2000, "field", "field"),
        },
    )
    session = CalibrationSession.resolve([], site=site)
    assert session.at == "field:corners"
    assert session.points_from == PointsFrom("field")
    assert [p.mm for p in session.points][1] == (1953, 18.5)
    assert session.placement().points_from == PointsFrom("field")


def test_a_session_records_how_its_points_were_chosen():
    assert CalibrationSession.resolve(["annex:corners"], site=C405).points_from == (
        PointsFrom("over", area="annex")
    )
    typed = ["47,18.5", "1953,18.5", "47,1981.5", "1953,1981.5"]
    assert CalibrationSession.resolve(typed, site=C405).points_from == PointsFrom(
        "points"
    )
    square = CalibrationSession.resolve(
        ["750,750,500,500:corners"],
        site=C405,
        points_from=PointsFrom("square", side_mm=500),
    )
    assert square.points_from == PointsFrom("square", side_mm=500)


def test_fewer_than_four_points_is_refused_with_the_span_rule():
    with pytest.raises(SessionError) as exc:
        CalibrationSession.resolve(["arena:top-left"], site=C405)
    assert "at least 4 points" in str(exc.value)
    assert "Span the area you will drive in" in str(exc.value)


# --- capture, redo, advance -------------------------------------------------


@pytest.mark.asyncio
async def test_a_capture_stores_the_reads_and_advances_to_the_next_point():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])

    await _store(driver, _press(0, *CORNER_COUNTS[0], n=25))

    state = driver.state()
    assert state["outstanding"] == 1
    assert state["captured"] == 1
    assert state["device"] == "ABCD"
    assert state["points"][0]["captured"] is True
    assert state["points"][0]["reads"] == [{"station": 0, "reads": 25, "target": 25}]
    assert state["points"][1]["captured"] is False


@pytest.mark.asyncio
async def test_a_capture_keeps_every_visible_station_and_drops_the_impossible():
    """Two stations in view are two sample entries; a phantom is not a third."""
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    # Station 1 is real; station 4's two sweeps share an LFSR index, which no
    # real pair of sweeps can produce.
    read = [
        LH2CalibrationSample(0, 41290, 51728),
        LH2CalibrationSample(1, 88102, 97640),
        LH2CalibrationSample(4, 129713, 129713),
    ]

    await _store(driver, ButtonCapture(device="ABCD", press=0, reads=[read] * 4))

    state = driver.state()
    assert [r["station"] for r in state["points"][0]["reads"]] == [0, 1]
    assert state["points"][0]["dropped"] == 4


@pytest.mark.asyncio
async def test_redo_discards_the_last_point_and_re_opens_it():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    await _store(driver, _press(0, *CORNER_COUNTS[0]))
    await _store(driver, _press(0, *CORNER_COUNTS[1]))
    assert driver.state()["outstanding"] == 2

    state = await driver.redo()

    assert state["outstanding"] == 1
    assert state["captured"] == 1
    assert state["points"][1]["captured"] is False
    assert state["points"][1]["reads"] == []


@pytest.mark.asyncio
async def test_redo_with_nothing_captured_is_refused():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    with pytest.raises(SessionError):
        await driver.redo()


# --- the robot's own trigger ------------------------------------------------


@pytest.mark.asyncio
async def test_a_session_listens_for_the_button_before_any_capture():
    # One press, one read: a single short chunk, press 0 chunk 0.
    events = [bytes([0xCB, 0]) + _record(0, *CORNER_COUNTS[0])]
    client = _FakeClient()
    client.watch_log_events = lambda: iter(
        {"addr": "FEED", "data_hex": e.hex()} for e in events
    )
    driver, _, _ = _driver(client)
    await driver.start(["arena:corners"])
    for _ in range(100):
        if driver.state()["outstanding"] == 1:
            break
        await asyncio.sleep(0.02)
    assert driver.state()["points"][0]["captured"] is True


@pytest.mark.asyncio
async def test_a_capture_arriving_while_point_k_is_outstanding_is_point_k():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    await _store(driver, _press(0, *CORNER_COUNTS[0]))
    assert driver.state()["outstanding"] == 1

    await _store(driver, _press(0, *CORNER_COUNTS[1]))

    state = driver.state()
    assert state["outstanding"] == 2
    assert state["points"][1]["captured"] is True
    assert state["points"][1]["reads"] == [{"station": 0, "reads": 1, "target": 1}]


@pytest.mark.asyncio
async def test_a_button_capture_makes_the_pressing_robot_the_capturing_one():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"], device="1234")

    await asyncio.wrap_future(driver.on_button_capture(_press(0, *CORNER_COUNTS[0])))

    assert driver.state()["device"] == "ABCD"


@pytest.mark.asyncio
async def test_a_button_capture_waits_for_a_save_in_progress():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    async with driver._lock:
        stored = driver.on_button_capture(_press(0, *CORNER_COUNTS[0]))
        await asyncio.sleep(0.05)
        assert driver.state()["outstanding"] == 0
    await asyncio.wrap_future(stored)
    assert driver.state()["outstanding"] == 1


def test_a_capture_arriving_with_no_session_is_dropped():
    driver, _, _ = _driver()
    assert driver.session is None
    assert driver.on_button_capture(_press(0, 41290, 51728)) is None
    assert driver.state() is None


@pytest.mark.asyncio
async def test_a_capture_arriving_with_every_point_captured_is_dropped():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)
    before = driver.state()

    await asyncio.wrap_future(driver.on_button_capture(_press(0, 44444, 55555)))

    assert driver.state() == before


# --- solving, saving, pushing -----------------------------------------------


@pytest.mark.asyncio
async def test_four_points_carry_a_residual_per_station_and_no_expected_error(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)

    saved = await driver.save()
    state = saved["session"]

    assert state["status"] == "saved"
    assert [s["index"] for s in state["stations"]] == [0]
    assert state["stations"][0]["points"] == 4
    # Four points fix eight unknowns exactly, so the residual is analytically
    # zero; cv2 computes it on a matrix with 1e3-magnitude entries, which
    # leaves a couple of microns of floor.
    assert state["stations"][0]["residual_mm"] < 0.01
    # The predictor is a later phase, so the number is absent rather than
    # guessed and a renderer shows no line.
    assert state["expected_error_mm"] is None


@pytest.mark.asyncio
async def test_save_writes_a_schema_4_file_under_the_site_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)

    saved = await driver.save(tag="arena-relay")

    path = tmp_path / "calibrations" / "c405-arena" / saved["path"].split("/")[-1]
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "schema_version = 4" in body
    assert f'id = "{saved["id"]}"' in body
    assert saved["id8"] == saved["id"][:8]


@pytest.mark.asyncio
async def test_solving_before_every_point_is_captured_is_refused():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    await _store(driver, _press(0, *CORNER_COUNTS[0]))
    with pytest.raises(SessionError) as exc:
        driver.session.solve()
    assert "1 of 4 points captured" in str(exc.value)


@pytest.mark.asyncio
async def test_push_sends_the_float32_messages_and_returns_the_stale_worklist(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)
    await driver.save()

    pushed = await driver.push()

    assert client.pushed[0] == lighthouse2.calibration_payload(driver.session.saved)
    assert pushed["bytes"] == len(client.pushed[0]) == 84
    # The robot now reports the pushed id, so nothing is left to re-push.
    assert pushed["stale"] == []


@pytest.mark.asyncio
async def test_a_console_push_to_a_robot_of_another_site_is_refused(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    client.infos["ABCD"] = _info(site="demo-dcoss-2026", calibration_id="00" * 8)
    await driver.start(["arena:corners"])
    await _walk(driver)
    await driver.save()

    with pytest.raises(SessionError) as exc:
        await driver.push()
    assert "demo-dcoss-2026" in str(exc.value)
    assert client.pushed == []


@pytest.mark.asyncio
async def test_pushing_before_a_solve_is_refused():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    with pytest.raises(SessionError):
        await driver.push()


@pytest.mark.asyncio
async def test_abandoning_leaves_no_session_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)

    await driver.abandon()

    assert driver.state() is None
    assert not (tmp_path / "calibrations").exists()


# --- one file, whichever surface saved it -----------------------------------


@pytest.mark.asyncio
async def test_collect_and_a_controller_session_write_the_same_file_for_the_same_reads(
    monkeypatch, tmp_path
):
    """The byte-identity the two surfaces are meant to share, id included.

    `collect` in the CLI process and a session driven over REST run the same
    Placement, guard, solver and writer, so only the capture stamp can
    differ - and that is outside the id.
    """
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)

    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver)
    from_console = await driver.save()
    console_body = _undated(open(driver.session.saved_path, encoding="utf-8").read())

    # The same reads, taken the way `collect` takes them: one session object,
    # the same prompt order.
    direct = CalibrationSession.resolve(["arena:corners"], site=C405)
    for index in range(4):
        direct.store_reads(_press(0, *CORNER_COUNTS[index]).reads, "ABCD")
    from_cli = direct.save()
    cli_body = _undated(open(direct.saved_path, encoding="utf-8").read())

    assert from_cli.id == from_console["id"]
    assert cli_body == console_body


def _undated(body: str) -> str:
    """The file with only the two timestamps blanked; neither is hashed."""
    return re.sub(
        r'^(created_at|captured_at) = ".*"$',
        r'\1 = "STAMP"',
        body,
        flags=re.MULTILINE,
    )


# --- the WebSocket ----------------------------------------------------------


@pytest.mark.asyncio
async def test_every_state_change_is_one_notification_in_order(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    sent: list = []

    async def notify(state):
        sent.append(state)

    driver, _, _ = _driver(notify=notify)
    await driver.start(["arena:corners"])
    await _store(driver, _press(0, *CORNER_COUNTS[0], n=2))
    await driver.redo()
    await driver.abandon()

    # start, the capture, redo, abandon.
    assert [_phase(s) for s in sent] == [(0, 0), (1, 1), (0, 0), None]


def _phase(state):
    return None if state is None else (state["outstanding"], state["captured"])


@pytest.mark.asyncio
async def test_the_session_survives_a_client_that_is_built_only_once(
    monkeypatch, tmp_path
):
    """The transport is built at start, for the button, and reused by a push."""
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"], device="ABCD")
    assert client.entered == 1
    await _walk(driver)
    await driver.save()
    await driver.push()
    assert client.entered == 1


# --- keeping the loop honest under concurrency ------------------------------


@pytest.mark.asyncio
async def test_two_captures_at_once_do_not_share_a_point():
    """The session serialises: the second press takes the next point, not the same."""
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])

    await asyncio.gather(
        _store(driver, _press(0, *CORNER_COUNTS[0])),
        _store(driver, _press(0, *CORNER_COUNTS[1])),
    )

    state = driver.state()
    assert state["captured"] == 2
    assert state["outstanding"] == 2


# --- the routes -------------------------------------------------------------


class _StubController:
    """Just enough controller for the routes: a driver and a site."""

    def __init__(self, driver, site=C405):
        self.calibration_session = driver
        self.site = site
        self.notifications: list = []


@pytest.fixture
def rest():
    from httpx import ASGITransport, AsyncClient

    from dotbot.server import api

    driver, client, _ = _driver()
    previous = getattr(api, "controller", None)
    api.controller = _StubController(driver)
    yield (
        AsyncClient(transport=ASGITransport(app=api), base_url="http://testserver"),
        api.controller,
        client,
    )
    api.controller = previous


@pytest.mark.asyncio
async def test_the_routes_walk_a_session_from_start_to_push(
    rest, monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    http, controller, client = rest

    assert (await http.get("/controller/calibration/session/state")).json() is None

    body = (
        await http.post(
            "/controller/calibration/session", json={"points": "arena:corners"}
        )
    ).json()
    assert body["total"] == 4
    assert body["outstanding"] == 0
    assert body["expected_error_mm"] is None
    assert body["points"][0]["where"] == "top-left corner of arena"

    await _walk(controller.calibration_session)
    body = (await http.get("/controller/calibration/session/state")).json()
    assert body["outstanding"] is None
    assert body["captured"] == 4

    saved = (
        await http.post("/controller/calibration/session/save", json={"tag": "bench"})
    ).json()
    assert len(saved["id"]) == 16
    assert saved["session"]["status"] == "saved"

    pushed = (await http.post("/controller/calibration/session/push")).json()
    assert pushed["id"] == saved["id"]
    assert pushed["stale"] == []
    assert client.pushed_to is None

    pushed = (
        await http.post(
            "/controller/calibration/session/push", json={"devices": ["abcd"]}
        )
    ).json()
    assert pushed["stale"] == []
    assert client.pushed_to == ["ABCD"]

    assert (await http.delete("/controller/calibration/session")).json() == {
        "session": None
    }
    assert (await http.get("/controller/calibration/session/state")).json() is None


@pytest.mark.asyncio
async def test_a_start_with_no_points_opens_on_the_sites_field(rest):
    http, _, _ = rest
    body = (await http.post("/controller/calibration/session", json={})).json()
    assert body["at"] == "arena:corners"
    assert body["points"][0]["where"] == "top-left corner of arena"


@pytest.mark.asyncio
async def test_a_route_that_needs_a_session_refuses_without_one(rest):
    http, _, _ = rest
    for path in ("redo", "save", "push"):
        response = await http.post(f"/controller/calibration/session/{path}", json={})
        assert response.status_code == 409
        assert "no calibration session is open" in response.json()["detail"]


@pytest.mark.asyncio
async def test_points_that_do_not_span_are_refused_with_the_span_rule(rest):
    http, _, _ = rest
    response = await http.post(
        "/controller/calibration/session", json={"points": ["arena:top-left"]}
    )
    assert response.status_code == 409
    assert "Span the area you will drive in" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_session_stores_the_area_its_expected_error_is_for(rest):
    """The area rides the start request; nothing is computed from it yet."""
    http, _, _ = rest
    body = (
        await http.post(
            "/controller/calibration/session",
            json={"points": ["arena:corners"], "area": "annex"},
        )
    ).json()
    assert body["area"] == "annex"
    assert (await http.get("/controller/calibration/session/state")).json()[
        "area"
    ] == "annex"


@pytest.mark.asyncio
async def test_a_session_started_without_an_area_names_none(rest):
    http, _, _ = rest
    body = (
        await http.post(
            "/controller/calibration/session", json={"points": ["arena:corners"]}
        )
    ).json()
    assert body["area"] == ""


@pytest.mark.asyncio
async def test_a_preview_resolves_the_same_points_a_start_would(rest):
    http, _, _ = rest
    preview = (
        await http.get(
            "/controller/calibration/session/preview",
            params={"points": "arena:corners"},
        )
    ).json()
    started = (
        await http.post(
            "/controller/calibration/session", json={"points": ["arena:corners"]}
        )
    ).json()

    assert [(p["x"], p["y"]) for p in preview["points"]] == [
        (p["x"], p["y"]) for p in started["points"]
    ]
    assert [p["corner"] for p in preview["points"]] == list(CORNERS)
    assert preview["reads"] == started["reads"]


@pytest.mark.asyncio
async def test_a_preview_resolves_a_typed_rectangle(rest):
    """The console's typed `x,y,w,h` rectangle is a spec the resolver takes."""
    http, _, _ = rest
    preview = (
        await http.get(
            "/controller/calibration/session/preview",
            params={"points": "750,750,500,500:corners"},
        )
    ).json()
    assert [(p["x"], p["y"]) for p in preview["points"]] == [
        (797.0, 768.5),
        (1203.0, 768.5),
        (797.0, 1231.5),
        (1203.0, 1231.5),
    ]
    assert [p["area"] for p in preview["points"]] == ["750,750,500,500"] * 4


@pytest.mark.asyncio
async def test_a_preview_of_points_no_area_answers_to_is_refused(rest):
    http, _, _ = rest
    response = await http.get(
        "/controller/calibration/session/preview", params={"points": "balcony:corners"}
    )
    assert response.status_code == 422
    assert "unknown area 'balcony'" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_session_takes_the_reads_per_point_it_is_started_with(rest):
    http, _, _ = rest
    body = (
        await http.post(
            "/controller/calibration/session",
            json={"points": ["arena:corners"], "reads": 40},
        )
    ).json()
    assert body["reads"] == 40


# --- rehearsing without a fleet ---------------------------------------------


@pytest.mark.asyncio
async def test_the_simulated_robot_presses_at_the_point_the_session_is_asking_about(
    monkeypatch, tmp_path
):
    """A controller on the simulator walks the whole mode and solves.

    The counts are computed from the declared point, so they agree with it
    by construction: this rehearses the surface, it does not validate one.
    """
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    from dotbot.calibration.simulated import SimulatedCaptureClient

    holder: dict = {}
    driver = SessionDriver(
        client_factory=lambda: SimulatedCaptureClient(
            lambda: (
                (
                    holder["driver"].session.outstanding.index,
                    holder["driver"].session.outstanding.mm,
                )
                if holder["driver"].session
                and holder["driver"].session.outstanding is not None
                else None
            ),
            press_delay_s=0.0,
        ),
        notify=_noop,
        site=C405,
        stream_factory=lambda c, on_button: CaptureSession(
            c, on_button_capture=on_button
        ),
    )
    holder["driver"] = driver

    await driver.start(["arena:corners"])
    for _ in range(200):
        if driver.session.complete:
            break
        await asyncio.sleep(0.02)
    assert driver.state()["device"] == "SIMULATED"

    saved = await driver.save()
    stations = saved["session"]["stations"]
    assert [s["index"] for s in stations] == [0, 1]
    assert all(s["residual_mm"] < 1.0 for s in stations)


async def _noop(_state):
    return None


def test_the_simulated_robot_presses_once_per_opening_of_a_point():
    """A point re-opened by a redo is pressed again."""
    from dotbot.calibration.ota import parse_button_payload
    from dotbot.calibration.simulated import SimulatedCaptureClient

    opened = [(0, (47.0, 18.5))]
    client = SimulatedCaptureClient(lambda: opened[-1], press_delay_s=0.0)
    events = client.watch_log_events()

    def next_press():
        chunk = parse_button_payload(bytes.fromhex(next(events)["data_hex"]))
        assert chunk.chunk == 0 and len(chunk.records) < 13
        return chunk.press

    assert next_press() == 0
    opened.append((1, (1953.0, 18.5)))
    assert next_press() == 1
    opened.append((0, (47.0, 18.5)))
    assert next_press() == 2


def test_a_button_capture_missing_a_station_an_earlier_point_saw_is_stored():
    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    two = [LH2CalibrationSample(0, 41290, 51728), LH2CalibrationSample(1, 30000, 40000)]
    assert session.store_reads([two] * 3).index == 0

    # A station occluded at one point is the solver's concern.
    assert session.store_reads([_reads(0, *CORNER_COUNTS[1])] * 3).index == 1
    assert session.outstanding.index == 2


@pytest.mark.asyncio
async def test_a_button_press_given_up_incomplete_is_reported(monkeypatch):
    from dotbot.calibration import driver as driver_module

    monkeypatch.setattr(driver_module, "EXPIRED_PRESS_POLL_INTERVAL", 0.01)
    expired = [[("FEED", 7)]]
    stream = SimpleNamespace(
        __enter__=lambda: None,
        __exit__=lambda *exc: None,
        expired_presses=lambda: expired.pop() if expired else [],
    )
    driver = SessionDriver(
        client_factory=lambda: _FakeClient(),
        notify=_noop,
        site=C405,
        stream_factory=lambda client, on_button: stream,
    )
    await driver.start(["arena:corners"])
    for _ in range(100):
        if driver.session.error:
            break
        await asyncio.sleep(0.01)
    assert "incomplete capture from FEED (press 7)" in driver.session.error
    await driver.abandon()


def test_collect_takes_a_button_press_as_the_outstanding_point(capsys):
    import queue

    from dotbot.cli.swarm_lh2 import _await_point

    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    stream = SimpleNamespace(expired_presses=lambda: [("FEED", 7)])
    arrivals: queue.Queue = queue.Queue()
    arrivals.put(
        ButtonCapture(
            device="FEED", press=2, reads=[_reads(0, *CORNER_COUNTS[0])] * 3, lost=1
        )
    )

    point = _await_point(session, stream, arrivals)

    assert point.index == 0
    captured = capsys.readouterr()
    assert "received from FEED as point 0" in captured.out
    assert "1 capture(s) lost before press 2" in captured.err


# --- collect -----------------------------------------------------------------

_CORNER_POINTS = [
    "--points=47,18.5",
    "--points=1953,18.5",
    "--points=47,1981.5",
    "--points=1953,1981.5",
]


class _CollectClient(_FakeClient):
    """Button presses at the four corners, queued up front."""

    def __init__(
        self, presses=(("FEED", 0), ("FEED", 1), ("FEED", 2), ("FEED", 3))
    ):
        super().__init__()
        self.events: queue.Queue = queue.Queue()
        for press, (addr, corner) in enumerate(presses):
            record = _record(0, *CORNER_COUNTS[corner])
            self.events.put(
                {"addr": addr, "data_hex": (bytes([0xCB, press << 3]) + record).hex()}
            )
            self.infos[addr] = _info()

    def watch_log_events(self):
        while True:
            try:
                yield self.events.get(timeout=0.05)
            except queue.Empty:
                continue


def _collect(monkeypatch, tmp_path, client, *args):
    from click.testing import CliRunner

    from dotbot.cli import swarm_lh2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    monkeypatch.setattr(swarm_lh2, "_swarmit_client", lambda *a: client)
    return CliRunner().invoke(swarm_lh2.cmd, ["collect", *_CORNER_POINTS, *args])


def test_collect_takes_every_point_from_the_button_and_pushes_to_its_robots(
    monkeypatch, tmp_path
):
    client = _CollectClient(
        presses=[("FEED", 0), ("FEED", 1), ("BEEF", 2), ("BEEF", 3)]
    )

    result = _collect(monkeypatch, tmp_path, client, "--push")

    assert result.exit_code == 0, result.output
    assert "Press the robot's button when it is still." in result.output
    assert "received from BEEF as point 3" in result.output
    assert client.pushed_to == ["BEEF", "FEED"]


def test_collect_has_no_device_capture():
    from click.testing import CliRunner

    from dotbot.cli import swarm_lh2

    result = CliRunner().invoke(swarm_lh2.cmd, ["collect", "--device=ABCD"])

    assert result.exit_code == 2
    assert "No such option '--device'" in result.output


ROLED = Site(
    name="c405-arena",
    extent_mm=(2000, 4000),
    areas={
        "staging": Area(0, 2000, 2000, 2000, "staging", "staging"),
        "field": Area(0, 0, 2000, 2000, "field", "field"),
        "dev-corner": Area(1000, 0, 1000, 1000, "dev-corner", "corner"),
    },
)


def _collect_in(monkeypatch, tmp_path, site, *args):
    """`collect` over `site` with its own point flags, captured on the button."""
    from click.testing import CliRunner

    from dotbot.cli import swarm_lh2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    monkeypatch.setattr(swarm_lh2, "_swarmit_client", lambda *a: _CollectClient())
    monkeypatch.setattr(
        swarm_lh2, "site_from_context", lambda ctx, flag=None: (site, "the test")
    )
    return CliRunner().invoke(swarm_lh2.cmd, ["collect", *args])


def _saved_points_from(tmp_path) -> PointsFrom | None:
    (path,) = (tmp_path / "calibrations" / "c405-arena").glob("*.toml")
    return read_calibration_file(path).placements[0].points_from


def test_collect_with_no_point_flag_calibrates_over_the_field(monkeypatch, tmp_path):
    result = _collect_in(monkeypatch, tmp_path, ROLED)

    assert result.exit_code == 0, result.output
    assert "Points: field:corners (field)." in result.output
    assert "top-left corner of field" in result.output
    assert _saved_points_from(tmp_path) == PointsFrom("field")


def test_collect_over_an_area_takes_its_corners(monkeypatch, tmp_path):
    result = _collect_in(monkeypatch, tmp_path, ROLED, "--over", "dev-corner")

    assert result.exit_code == 0, result.output
    assert "top-left corner of dev-corner" in result.output
    assert _saved_points_from(tmp_path) == PointsFrom("over", area="dev-corner")


def test_collect_square_says_the_rest_of_the_field_is_extrapolated(
    monkeypatch, tmp_path
):
    result = _collect_in(monkeypatch, tmp_path, ROLED, "--square", "500")

    assert result.exit_code == 0, result.output
    assert "Points: 750,750,500,500:corners (square 500 mm)." in result.output
    assert "rest of the 2000 x 2000 mm field is extrapolated" in result.output
    assert _saved_points_from(tmp_path) == PointsFrom("square", side_mm=500)


@pytest.mark.parametrize(
    "flags",
    [
        ["--over", "dev-corner", "--square", "500"],
        ["--points", "field:corners", "--over", "dev-corner"],
        ["--points", "field:corners", "--square", "500"],
    ],
)
def test_collect_takes_one_way_of_choosing_the_points(monkeypatch, tmp_path, flags):
    result = _collect_in(monkeypatch, tmp_path, ROLED, *flags)

    assert result.exit_code == 2
    assert "each choose the points; pass one" in result.output


async def _button_session(driver, device: str) -> None:
    await driver.start(["arena:corners"])
    for corner in range(4):
        await asyncio.wrap_future(
            driver.on_button_capture(
                ButtonCapture(
                    device=device,
                    press=corner,
                    reads=[_reads(0, *CORNER_COUNTS[corner])],
                )
            )
        )
    await driver.save()


@pytest.mark.asyncio
async def test_a_console_push_with_nothing_selected_goes_to_the_whole_swarm(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    client.infos["FEED"] = _info()
    client.infos["BEEF"] = _info()
    await _button_session(driver, "FEED")

    pushed = await driver.push(devices=[])

    assert client.pushed_to is None
    wanted = lighthouse2.pushed_id(driver.session.saved)
    assert {i.lh2_calibration_id for i in client.infos.values()} == {wanted}
    assert pushed["stale"] == []


@pytest.mark.asyncio
async def test_a_console_push_goes_only_to_the_selected_robots(monkeypatch, tmp_path):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    client.infos["FEED"] = _info()
    client.infos["BEEF"] = _info()
    await _button_session(driver, "FEED")

    await driver.push(devices=["beef"])

    assert client.pushed_to == ["BEEF"]
    wanted = lighthouse2.pushed_id(driver.session.saved)
    assert client.infos["BEEF"].lh2_calibration_id == wanted
    assert client.infos["FEED"].lh2_calibration_id != wanted


def test_a_push_to_an_empty_robot_list_is_refused():
    from dotbot.calibration.push import PushRefused, gate_push

    with pytest.raises(PushRefused, match="no robot named"):
        gate_push(_FakeClient(), SimpleNamespace(), devices=[])
