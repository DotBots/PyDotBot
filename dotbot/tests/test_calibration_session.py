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
import re
import threading
from types import SimpleNamespace

import pytest

from dotbot.area import Area
from dotbot.calibration import lighthouse2
from dotbot.calibration.driver import SessionDriver
from dotbot.calibration.ota import (
    ButtonCapture,
    CaptureSession,
    parse_capture_payload,
)
from dotbot.calibration.points import CORNERS
from dotbot.calibration.session import CalibrationSession, SessionError
from dotbot.site import Site

_TAG = 0xCA

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


def _payload(*records: bytes) -> bytes:
    return bytes([_TAG]) + b"".join(records)


def _reads(lh_index: int, count1: int, count2: int, n: int = 1) -> list:
    """One capture's worth of decoded records, `n` of them."""
    return parse_capture_payload(_payload(_record(lh_index, count1, count2)), _TAG)


def _press(lh_index: int, count1: int, count2: int, n: int = 1) -> ButtonCapture:
    """One button capture of `n` identical reads from one station."""
    return ButtonCapture(
        device="ABCD", press=0, reads=[_reads(lh_index, count1, count2)] * n
    )


def _info(version=2, site="", calibration_id=""):
    """A robot's device info as swarmit decodes it."""
    return SimpleNamespace(
        info_version=version, lh2_site_name=site, lh2_calibration_id=calibration_id
    )


class _FakeClient:
    """Emits one tagged event per trigger, for whichever counts are set.

    Mirrors the firmware contract: raw counts only arrive in reply to a
    request, so the drain-then-trigger ordering is exercised as on a bot.
    """

    def __init__(self, device: str = "ABCD"):
        self.device = device.upper()
        self.records = _record(0, *CORNER_COUNTS[0])
        self.triggers = 0
        self.pushed: list[bytes] = []
        self.entered = 0
        self._triggered = threading.Event()
        self.infos = {self.device: _info()}

    def at_corner(self, index: int, station: int = 0) -> None:
        self.records = _record(station, *CORNER_COUNTS[index])

    def request_lh2_capture(self, device: str) -> None:
        self.triggers += 1
        self._triggered.set()

    def send_lh2_calibration(self, payload: bytes, devices=None) -> None:
        self.pushed.append(payload)
        self.pushed_to = devices
        # The bot commits the push and reports its site and id from then on.
        for info in self.infos.values():
            if info is not None and info.info_version >= 2:
                info.lh2_site_name = payload[60:76].rstrip(b"\x00").decode()
                info.lh2_calibration_id = payload[76:84].hex()

    def refresh_device_info(self, devices=None) -> None:
        pass

    def status(self):
        return {
            addr: SimpleNamespace(info_gen=1, info=info)
            for addr, info in self.infos.items()
        }

    def watch_log_events(self):
        while True:
            if self._triggered.wait(timeout=0.05):
                self._triggered.clear()
                yield {"addr": self.device, "data_hex": _payload(self.records).hex()}

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
        client_factory=lambda device: client,
        notify=notify or record,
        site=site,
        stream_factory=lambda c, device, on_button: CaptureSession(
            c, device, _TAG, on_button_capture=on_button
        ),
    )
    return driver, client, seen


async def _walk(driver, client, reads=1):
    """Capture all four corners, one per corner's counts."""
    driver.session.reads = reads
    driver.session.timeout = 2.0
    driver.session.retries = 0
    for index in range(4):
        client.at_corner(index)
        await driver.capture("ABCD")


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


def test_fewer_than_four_points_is_refused_with_the_span_rule():
    with pytest.raises(SessionError) as exc:
        CalibrationSession.resolve(["arena:top-left"], site=C405)
    assert "at least 4 points" in str(exc.value)
    assert "Span the area you will drive in" in str(exc.value)


# --- capture, redo, advance -------------------------------------------------


@pytest.mark.asyncio
async def test_capture_stores_the_reads_and_advances_to_the_next_point():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 25
    driver.session.timeout = 2.0
    driver.session.retries = 0

    state = await driver.capture("abcd")

    assert client.triggers == 25
    assert state["outstanding"] == 1
    assert state["captured"] == 1
    assert state["device"] == "ABCD"
    assert state["points"][0]["captured"] is True
    assert state["points"][0]["reads"] == [{"station": 0, "reads": 25, "target": 25}]
    assert state["points"][1]["captured"] is False


@pytest.mark.asyncio
async def test_capture_keeps_every_visible_station_and_drops_the_impossible():
    """Two stations in view are two sample entries; a phantom is not a third."""
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 4
    driver.session.timeout = 2.0
    driver.session.retries = 0
    # Station 1 is real; station 4's two sweeps share an LFSR index, which no
    # real pair of sweeps can produce.
    client.records = (
        _record(0, 41290, 51728) + _record(1, 88102, 97640) + _record(4, 129713, 129713)
    )

    state = await driver.capture("ABCD")

    assert [r["station"] for r in state["points"][0]["reads"]] == [0, 1]
    assert state["points"][0]["dropped"] == 4


@pytest.mark.asyncio
async def test_redo_discards_the_last_point_and_re_opens_it():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 1
    driver.session.timeout = 2.0
    driver.session.retries = 0
    await driver.capture("ABCD")
    await driver.capture("ABCD")
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


@pytest.mark.asyncio
async def test_a_capture_with_no_robot_chosen_is_refused():
    driver, _, _ = _driver()
    await driver.start(["arena:corners"])
    with pytest.raises(SessionError) as exc:
        await driver.capture()
    assert "no robot chosen" in str(exc.value)


@pytest.mark.asyncio
async def test_a_capture_timeout_is_reported_as_a_line_not_an_exception():
    class _Silent(_FakeClient):
        def request_lh2_capture(self, device):
            self.triggers += 1

    driver, _, _ = _driver(client=_Silent())
    await driver.start(["arena:corners"])
    driver.session.reads = 1
    driver.session.timeout = 0.2
    driver.session.retries = 0

    state = await driver.capture("ABCD")

    assert state["outstanding"] == 0
    assert "no LH2 samples" in state["error"]


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
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 1
    driver.session.timeout = 2.0
    driver.session.retries = 0
    await driver.capture("ABCD")  # point 0 the requested way
    assert driver.state()["outstanding"] == 1

    driver.on_button_capture(_press(0, *CORNER_COUNTS[1]))

    state = driver.state()
    assert state["outstanding"] == 2
    assert state["points"][1]["captured"] is True
    assert state["points"][1]["reads"] == [{"station": 0, "reads": 1, "target": 1}]


def test_a_capture_arriving_with_no_session_is_dropped():
    driver, _, _ = _driver()
    assert driver.session is None
    driver.on_button_capture(_press(0, 41290, 51728))
    assert driver.state() is None


@pytest.mark.asyncio
async def test_a_capture_arriving_with_every_point_captured_is_dropped():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver, client)
    before = driver.state()

    driver.on_button_capture(_press(0, 44444, 55555))

    assert driver.state() == before


# --- solving, saving, pushing -----------------------------------------------


@pytest.mark.asyncio
async def test_four_points_carry_a_residual_per_station_and_no_expected_error(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver, client)

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
async def test_save_writes_a_schema_2_file_under_the_site_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    await _walk(driver, client)

    saved = await driver.save(tag="arena-relay")

    path = tmp_path / "calibrations" / "c405-arena" / saved["path"].split("/")[-1]
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "schema_version = 2" in body
    assert f'id = "{saved["id"]}"' in body
    assert saved["id8"] == saved["id"][:8]


@pytest.mark.asyncio
async def test_solving_before_every_point_is_captured_is_refused():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 1
    driver.session.timeout = 2.0
    driver.session.retries = 0
    await driver.capture("ABCD")
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
    await _walk(driver, client)
    await driver.save()

    pushed = await driver.push()

    assert client.pushed[0] == lighthouse2.calibration_payload(driver.session.saved)
    assert pushed["bytes"] == len(client.pushed[0]) == 84
    # The robot now reports the pushed id, so nothing is left to re-push.
    assert pushed["stale"] == []
    assert client.pushed_to == [driver.session.device]


@pytest.mark.asyncio
async def test_a_console_push_to_a_robot_of_another_site_is_refused(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    driver, client, _ = _driver()
    client.infos["ABCD"] = _info(site="demo-dcoss-2026", calibration_id="00" * 8)
    await driver.start(["arena:corners"])
    await _walk(driver, client)
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
    await _walk(driver, client)

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
    await _walk(driver, client)
    from_console = await driver.save()
    console_body = _undated(open(driver.session.saved_path, encoding="utf-8").read())

    # The same reads, taken the way `collect` takes them: one session object,
    # one CaptureSession stream, the same prompt order.
    direct = CalibrationSession.resolve(["arena:corners"], site=C405)
    direct.reads, direct.timeout, direct.retries = 1, 2.0, 0
    cli_client = _FakeClient()
    with CaptureSession(cli_client, "ABCD", _TAG) as stream:
        for index in range(4):
            cli_client.at_corner(index)
            direct.capture(stream)
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

    driver, client, _ = _driver(notify=notify)
    await driver.start(["arena:corners"])
    driver.session.reads = 2
    driver.session.timeout = 2.0
    driver.session.retries = 0
    client.at_corner(0)
    await driver.capture("ABCD")
    await driver.redo()
    await driver.abandon()

    # start, two read-progress events, the finished capture, redo, abandon.
    assert [_phase(s) for s in sent] == [
        (0, 0),
        (0, 0),
        (0, 0),
        (1, 1),
        (0, 0),
        None,
    ]
    # The progress events carry the reads as they land, never out of order.
    assert [s["points"][0]["reads"] for s in sent[1:3]] == [
        [{"station": 0, "reads": 1, "target": 2}],
        [{"station": 0, "reads": 2, "target": 2}],
    ]


def _phase(state):
    return None if state is None else (state["outstanding"], state["captured"])


@pytest.mark.asyncio
async def test_the_session_survives_a_client_that_is_built_only_once():
    """The transport is built at start, for the button, and reused by captures."""
    driver, client, _ = _driver()
    await driver.start(["arena:corners"], device="ABCD")
    assert client.entered == 1
    driver.session.reads = 1
    driver.session.timeout = 2.0
    driver.session.retries = 0
    await driver.capture("ABCD")
    await driver.capture("ABCD")
    assert client.entered == 1


# --- keeping the loop honest under concurrency ------------------------------


@pytest.mark.asyncio
async def test_two_captures_at_once_do_not_share_a_point():
    """The session serialises: the second call takes the next point, not the same."""
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    driver.session.reads = 1
    driver.session.timeout = 2.0
    driver.session.retries = 0

    await asyncio.gather(driver.capture("ABCD"), driver.capture("ABCD"))

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

    controller.calibration_session.session.reads = 1
    controller.calibration_session.session.timeout = 2.0
    controller.calibration_session.session.retries = 0
    for index in range(4):
        client.at_corner(index)
        body = (
            await http.post(
                "/controller/calibration/session/capture", json={"device": "ABCD"}
            )
        ).json()
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

    assert (await http.delete("/controller/calibration/session")).json() == {
        "session": None
    }
    assert (await http.get("/controller/calibration/session/state")).json() is None


@pytest.mark.asyncio
async def test_a_route_that_needs_a_session_refuses_without_one(rest):
    http, _, _ = rest
    for path in ("capture", "redo", "save", "push"):
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
async def test_the_simulated_client_answers_the_point_the_session_is_asking_about(
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
        client_factory=lambda device: SimulatedCaptureClient(
            device,
            lambda: (
                holder["driver"].session.outstanding.mm
                if holder["driver"].session
                and holder["driver"].session.outstanding is not None
                else None
            ),
        ),
        notify=_noop,
        site=C405,
        stream_factory=lambda c, device, on_button: CaptureSession(
            c, device, _TAG, on_button_capture=on_button
        ),
    )
    holder["driver"] = driver
    monkeypatch.setattr("dotbot.calibration.simulated._SAMPLE_TAG", _TAG)

    await driver.start(["arena:corners"])
    driver.session.reads = 3
    driver.session.timeout = 2.0
    driver.session.retries = 0
    for _ in range(4):
        await driver.capture("ABCD")

    saved = await driver.save()
    stations = saved["session"]["stations"]
    assert [s["index"] for s in stations] == [0, 1]
    assert all(s["residual_mm"] < 1.0 for s in stations)


async def _noop(_state):
    return None


def test_a_button_capture_missing_a_station_an_earlier_point_saw_is_not_stored():
    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    two = parse_capture_payload(
        _payload(_record(0, 41290, 51728), _record(1, 30000, 40000)), _TAG
    )
    assert session.store_reads([two] * 3).index == 0

    with pytest.raises(SessionError, match="missing station 1"):
        session.store_reads([_reads(0, *CORNER_COUNTS[1])] * 3)

    assert session.outstanding.index == 1
    assert session.points[1].capture is None


@pytest.mark.asyncio
async def test_a_refused_button_capture_leaves_the_point_outstanding_with_the_error():
    driver, client, _ = _driver()
    await driver.start(["arena:corners"])
    two = parse_capture_payload(
        _payload(_record(0, 41290, 51728), _record(1, 30000, 40000)), _TAG
    )
    driver.on_button_capture(ButtonCapture(device="ABCD", press=0, reads=[two]))
    driver.on_button_capture(_press(0, *CORNER_COUNTS[1]))

    state = driver.state()
    assert state["outstanding"] == 1
    assert "missing station 1" in state["error"]


def test_collect_takes_a_button_press_as_the_outstanding_point(capsys):
    import queue

    from dotbot.cli.swarm_lh2 import _await_point

    session = CalibrationSession.resolve(["arena:corners"], site=C405)
    stream = SimpleNamespace(expired_presses=lambda: [("FEED", 7)])
    arrivals: queue.Queue = queue.Queue()
    arrivals.put(
        (
            "button",
            ButtonCapture(
                device="FEED", press=2, reads=[_reads(0, *CORNER_COUNTS[0])] * 3, lost=1
            ),
        )
    )

    point = _await_point(session, stream, arrivals)

    assert point.index == 0
    captured = capsys.readouterr()
    assert "received from FEED as point 0" in captured.out
    assert "1 capture(s) lost before press 2" in captured.err
