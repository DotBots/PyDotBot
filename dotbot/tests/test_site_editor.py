# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's server: read, preview and save one pack, refusing a save
made against a file that has changed since."""

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from dotbot.cli import site_cmd
from dotbot.site_editor import EditorState, create_app
from dotbot.tests.test_site_toml import ARENA


@pytest.fixture
def pack(tmp_path):
    folder = tmp_path / "arena"
    folder.mkdir()
    (folder / "site.toml").write_text(ARENA, newline="\n")
    return folder


@pytest.fixture
def page(tmp_path):
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "site-editor.html").write_text("<html>editor</html>")
    return folder


def local_client(app) -> TestClient:
    """A client calling `app` from this machine, as the editor's page does."""
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


@pytest.fixture
def client(pack, page, tmp_path):
    calibrations = tmp_path / "home-calibrations" / "arena"
    return local_client(create_app(EditorState("arena", pack, [calibrations]), page))


def _loaded(client):
    body = client.get("/api/site").json()
    for area in body["site"]["areas"]:
        area["was"] = area["name"]
    return body


def test_the_page_and_the_site_are_served(client, pack):
    assert client.get("/").text == "<html>editor</html>"
    body = client.get("/api/site").json()
    assert body["name"] == "arena"
    assert body["path"] == str(pack / "site.toml")
    assert body["site"]["extent_mm"] == [2000, 4000]
    assert [c["count"] for c in body["calibrations"]] == [0, 0]


def test_the_calibrations_are_counted(client, pack):
    (pack / "calibrations").mkdir()
    (pack / "calibrations" / "lh2-1.toml").write_text("")
    assert client.get("/api/site").json()["calibrations"][0]["count"] == 1


def test_a_save_writes_only_what_changed(client, pack):
    body = _loaded(client)
    body["site"]["areas"][3]["x"] = 1050
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": body["site"]}
    )
    assert response.status_code == 200
    assert response.json()["written"] is True
    assert (pack / "site.toml").read_text() == ARENA.replace(
        'role = "corner"\nx = 1000', 'role = "corner"\nx = 1050'
    )
    assert response.json()["revision"] != body["revision"]
    assert not [p for p in pack.iterdir() if p.name.startswith(".")]


def test_a_save_with_nothing_changed_writes_nothing(client, pack):
    before = (pack / "site.toml").stat().st_mtime_ns
    body = _loaded(client)
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": body["site"]}
    )
    assert response.json()["written"] is False
    assert (pack / "site.toml").stat().st_mtime_ns == before


def test_a_save_against_a_changed_file_is_refused(client, pack):
    body = _loaded(client)
    (pack / "site.toml").write_text(ARENA + "\n# edited by hand\n")
    body["site"]["areas"][0]["w"] = 1500
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": body["site"]}
    )
    assert response.status_code == 409
    assert (pack / "site.toml").read_text().endswith("# edited by hand\n")


def test_a_site_the_schema_refuses_is_a_422_and_the_file_is_untouched(client, pack):
    body = _loaded(client)
    body["site"]["areas"][1]["role"] = "field"
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": body["site"]}
    )
    assert response.status_code == 422
    assert "at most one field" in response.json()["detail"]
    assert (pack / "site.toml").read_text() == ARENA


def test_the_preview_is_the_file_as_it_would_be_written(client, pack):
    body = _loaded(client)
    body["site"]["anchor"] = "the door"
    preview = client.post("/api/preview", json={"site": body["site"]}).json()
    assert preview["changed"] is True
    assert 'anchor = "the door"' in preview["text"]
    assert (pack / "site.toml").read_text() == ARENA


def test_done_runs_the_callback(pack, page):
    calls = []
    app = create_app(EditorState("arena", pack), page, on_done=lambda: calls.append(1))
    client = local_client(app)
    assert client.post("/api/done").status_code == 200
    assert calls == [1]


@pytest.fixture
def served(monkeypatch):
    calls = []
    monkeypatch.setattr(site_cmd, "_editor_socket", lambda port: port)
    monkeypatch.setattr(
        site_cmd,
        "_serve_editor",
        lambda name, pack, sock, headless, configured=None: calls.append(
            (name, pack, headless)
        ),
    )
    return calls


def test_site_new_writes_a_pack_in_the_user_home_outside_a_project(
    tmp_path, monkeypatch, served
):
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path / "home-sites")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        site_cmd.cmd, ["new", "lab", "--field", "3m", "--headless"], obj={}
    )
    assert result.exit_code == 0, result.output
    pack = tmp_path / "home-sites" / "lab"
    assert "extent_mm = [6000, 6000]" in (pack / "site.toml").read_text()
    assert served == [("lab", pack, True)]
    assert "dotbot site use lab" in result.output


def test_site_new_writes_a_pack_beside_the_project(tmp_path, monkeypatch, served):
    from dotbot.config import load_discovered

    (tmp_path / "dotbot.toml").write_text("")
    config = load_discovered(environ={}, start_dir=tmp_path)
    result = CliRunner().invoke(site_cmd.cmd, ["new", "lab"], obj={"config": config})
    assert result.exit_code == 0, result.output
    assert (tmp_path.resolve() / "sites" / "lab" / "site.toml").is_file()


def test_site_new_refuses_an_existing_folder(tmp_path, monkeypatch, served):
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path)
    (tmp_path / "lab").mkdir()
    result = CliRunner().invoke(site_cmd.cmd, ["new", "lab"], obj={})
    assert result.exit_code != 0 and "already exists" in result.output
    assert served == []


def test_site_new_writes_nothing_when_the_page_is_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path / "home-sites")
    monkeypatch.setattr("dotbot.site_editor.EDITOR_DIR", tmp_path / "no-dist")
    result = CliRunner().invoke(site_cmd.cmd, ["new", "lab", "--headless"], obj={})
    assert result.exit_code != 0 and "not built" in result.output
    assert not (tmp_path / "home-sites" / "lab").exists()


def test_site_new_refuses_a_port_that_cannot_be(served):
    result = CliRunner().invoke(site_cmd.cmd, ["new", "lab", "--port", "70000"])
    assert result.exit_code == 2
    assert served == []


def test_site_new_refuses_a_name_too_long_to_reach_a_robot(
    tmp_path, monkeypatch, served
):
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path)
    result = CliRunner().invoke(site_cmd.cmd, ["new", "a_very_long_site_name"], obj={})
    assert result.exit_code != 0 and "to reach a robot" in result.output
    assert served == [] and not (tmp_path / "a_very_long_site_name").exists()


def test_site_new_refuses_a_name_another_home_has(tmp_path, monkeypatch, served):
    from dotbot.config import load_discovered

    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path / "home-sites")
    (tmp_path / "home-sites" / "lab").mkdir(parents=True)
    (tmp_path / "home-sites" / "lab" / "site.toml").write_text(ARENA)
    project = tmp_path / "project"
    project.mkdir()
    (project / "dotbot.toml").write_text("")
    config = load_discovered(environ={}, start_dir=project)
    result = CliRunner().invoke(site_cmd.cmd, ["new", "lab"], obj={"config": config})
    assert result.exit_code != 0 and "dotbot site edit lab" in result.output
    assert served == [] and not (project / "sites" / "lab").exists()


def test_site_edit_takes_a_pack_folder(pack, served):
    result = CliRunner().invoke(site_cmd.cmd, ["edit", str(pack)], obj={})
    assert result.exit_code == 0, result.output
    assert served == [("arena", pack.resolve(), False)]


def test_site_edit_refuses_an_unknown_site(tmp_path, monkeypatch, served):
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path)
    result = CliRunner().invoke(site_cmd.cmd, ["edit", "bench"], obj={})
    assert result.exit_code != 0
    assert "dotbot site new" in result.output
    assert served == []


def test_site_edit_defaults_to_the_active_pack_even_by_path(
    tmp_path, pack, monkeypatch, served
):
    from dotbot.config import load_discovered

    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", tmp_path / "home-sites")
    project = tmp_path / "project"
    project.mkdir()
    (project / "dotbot.toml").write_text(f"site = {str(pack)!r}\n")
    config = load_discovered(environ={}, start_dir=project)
    result = CliRunner().invoke(site_cmd.cmd, ["edit"], obj={"config": config})
    assert result.exit_code == 0, result.output
    assert [(name, path.resolve()) for name, path, _ in served] == [
        ("arena", pack.resolve())
    ]


def test_a_write_for_another_host_is_refused_and_a_read_is_served(client):
    assert client.post("/api/done", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/site", headers={"host": "evil.example"}).status_code == 200


def test_a_write_from_another_machine_is_refused_whatever_its_host(pack, page):
    app = create_app(EditorState("arena", pack), page)
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.7", 5))
    assert remote.get("/api/site").status_code == 200
    assert remote.post("/api/done").status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://evil.example"},
        {"origin": "null"},
        {"origin": "http://127.0.0.1:9999"},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
    ],
)
def test_a_save_from_another_page_is_refused(client, pack, headers):
    body = _loaded(client)
    body["site"]["anchor"] = "moved"
    response = client.put(
        "/api/site",
        json={"revision": body["revision"], "site": body["site"]},
        headers=headers,
    )
    assert response.status_code == 403
    assert (pack / "site.toml").read_text() == ARENA


def test_a_save_from_the_editors_own_page_is_taken(client, pack):
    body = _loaded(client)
    body["site"]["anchor"] = "moved"
    response = client.put(
        "/api/site",
        json={"revision": body["revision"], "site": body["site"]},
        headers={"origin": "http://127.0.0.1", "sec-fetch-site": "same-origin"},
    )
    assert response.status_code == 200
    assert 'anchor = "moved"' in (pack / "site.toml").read_text()


def test_a_request_from_an_ipv6_loopback_client_is_taken(pack, page):
    app = create_app(EditorState("arena", pack), page)
    for address in ("::1", "::ffff:127.0.0.1"):
        local = TestClient(app, base_url="http://localhost", client=(address, 5))
        assert local.get("/api/site").status_code == 200


def test_a_pack_the_editor_cannot_draw_is_a_422(pack, client):
    (pack / "site.toml").write_text(
        "areas = { field = { x = 0, y = 0, w = 1, h = 1 } }\n"
    )
    response = client.get("/api/site")
    assert response.status_code == 422
    assert "edit it by hand" in response.json()["detail"]
    (pack / "site.toml").write_bytes(b"anchor = '\xff'\n")
    assert client.get("/api/site").status_code == 422
    (pack / "site.toml").write_text("[areas.field\n")
    assert client.get("/api/site").status_code == 422


def test_two_saves_against_one_revision_take_one(client, pack, monkeypatch):
    import threading
    import time

    from dotbot import site_toml

    patched = site_toml.patched_text

    def slow(text, model):
        time.sleep(0.2)
        return patched(text, model)

    monkeypatch.setattr(site_toml, "patched_text", slow)
    body = _loaded(client)
    statuses = []

    def save(x):
        site = {**body["site"], "areas": [dict(a) for a in body["site"]["areas"]]}
        site["areas"][0]["x"] = x
        statuses.append(
            client.put(
                "/api/site", json={"revision": body["revision"], "site": site}
            ).status_code
        )

    threads = [threading.Thread(target=save, args=(x,)) for x in (100, 200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 409]


def test_a_save_through_a_symlink_writes_its_target(tmp_path, page):
    pack = tmp_path / "linked"
    pack.mkdir()
    target = tmp_path / "checkout.toml"
    target.write_text(ARENA)
    (pack / "site.toml").symlink_to(target)
    client = local_client(create_app(EditorState("linked", pack), page))
    body = _loaded(client)
    body["site"]["anchor"] = "moved"
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": body["site"]}
    )
    assert response.status_code == 200
    assert (pack / "site.toml").is_symlink()
    assert 'anchor = "moved"' in target.read_text()


def test_a_save_that_leaves_out_the_walls_keeps_them(client, pack):
    (pack / "site.toml").write_text(ARENA + "\n[[walls]]\npoints = [[0, 0], [1, 1]]\n")
    body = _loaded(client)
    site = {k: v for k, v in body["site"].items() if k not in ("walls", "obstacles")}
    site["anchor"] = "moved"
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": site}
    )
    assert response.status_code == 200
    assert "[[walls]]" in (pack / "site.toml").read_text()


def test_a_save_that_leaves_out_the_objects_keeps_them(client, pack):
    (pack / "site.toml").write_text(
        ARENA + '\n[objects.pad]\nkind = "charger"\nx = 1\ny = 1\n'
    )
    body = _loaded(client)
    site = {k: v for k, v in body["site"].items() if k != "objects"}
    site["anchor"] = "moved"
    response = client.put(
        "/api/site", json={"revision": body["revision"], "site": site}
    )
    assert response.status_code == 200
    assert "[objects.pad]" in (pack / "site.toml").read_text()


def test_a_hand_edited_text_is_what_the_save_patches(client, pack):
    body = _loaded(client)
    edited = ARENA.replace("# the 2 x 2 m square at the top", "# typed on the page")
    edited = edited.replace("# encloses every area below", "# and a note")
    site = client.post("/api/parse", json={"text": edited}).json()["site"]
    for area in site["areas"]:
        area["was"] = area["name"]
    response = client.put(
        "/api/site",
        json={"revision": body["revision"], "site": site, "text": edited},
    )
    assert response.status_code == 200
    assert (pack / "site.toml").read_text() == edited


def test_a_hand_edited_text_that_does_not_read_is_refused(client, pack):
    body = _loaded(client)
    preview = client.post(
        "/api/preview", json={"site": body["site"], "text": "extent_mm = ["}
    )
    assert preview.status_code == 422
    assert "does not read" in preview.json()["detail"]
    assert client.post("/api/parse", json={"text": "extent_mm = ["}).status_code == 422
    parsed = client.post("/api/parse", json={"text": ARENA}).json()
    assert parsed["site"]["extent_mm"] == [2000, 4000]


def test_the_revision_follows_an_edit_made_elsewhere(client, pack):
    before = client.get("/api/revision").json()["revision"]
    assert before == client.get("/api/site").json()["revision"]
    (pack / "site.toml").write_text(ARENA + "\n# edited by hand\n")
    assert client.get("/api/revision").json()["revision"] != before


def test_open_runs_the_named_editor_on_site_toml(client, pack, monkeypatch):
    monkeypatch.setenv("DOTBOT_EDITOR", "true --wait")
    body = client.post("/api/open").json()
    assert body["command"] == f"true --wait {pack / 'site.toml'}"


def test_reads_reach_the_page_off_loopback_and_writes_do_not(pack, page, tmp_path):
    app = create_app(EditorState("arena", pack, [tmp_path / "c"]), page)
    lan = TestClient(
        app, base_url="http://bench-host:8000", client=("192.168.1.30", 50000)
    )
    origin = {"Origin": "http://bench-host:8000"}
    body = lan.get("/api/site", headers=origin)
    assert body.status_code == 200
    assert lan.get("/api/context", headers=origin).json()["can_write"] is False
    site = body.json()
    refused = lan.put(
        "/api/site",
        headers=origin,
        json={"revision": site["revision"], "site": site["site"]},
    )
    assert refused.status_code == 403
    assert (
        lan.get("/api/site", headers={"Origin": "http://example.org"}).status_code
        == 403
    )
    assert local_client(app).get("/api/context").json()["can_write"] is True


def test_a_check_is_appended_and_no_calibration_is_rewritten(
    client, tmp_path, monkeypatch
):
    from dotbot.calibration import checks, lighthouse2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    first = client.post(
        "/api/checks",
        json={
            "calibration": "4640cfde014c7232",
            "mark_mm": [500, 600],
            "measured_mm": [502.4, 598.1],
            "robot": "222a34f9458e8aad",
        },
    ).json()
    assert first["error_mm"] == 3.06 and first["robot"] == "222A34F9458E8AAD"
    path = checks.checks_path("arena")
    before = path.read_text()
    client.post(
        "/api/checks",
        json={
            "calibration": "4640cfde014c7232",
            "mark_mm": [0, 0],
            "measured_mm": [1, 0],
            "robot": "c999",
        },
    )
    after = path.read_text()
    assert after.startswith(before)
    assert [c["error_mm"] for c in client.get("/api/checks").json()["checks"]] == [
        3.06,
        1.0,
    ]
    assert (
        list((tmp_path / "home" / "calibrations" / "arena").glob("calibration*")) == []
    )


def test_a_restore_point_puts_site_toml_back(client, pack, tmp_path, monkeypatch):
    from dotbot.calibration import lighthouse2

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path / "home")
    point = client.post("/api/points", json={"name": "Monday class"}).json()
    assert point["name"] == "Monday class"
    body = _loaded(client)
    body["site"]["areas"][0]["w"] = 1500
    client.put("/api/site", json={"revision": body["revision"], "site": body["site"]})
    assert "w = 1500" in (pack / "site.toml").read_text()
    revision = client.get("/api/site").json()["revision"]
    back = client.post(
        f"/api/points/{point['id']}/restore", json={"revision": revision}
    ).json()
    assert (pack / "site.toml").read_text() == ARENA
    assert back["steps"][0]["status"] == "written"
    assert [p["name"] for p in client.get("/api/points").json()] == ["Monday class"]


SERVED = {"id": "4640cfde014c7232", "id8": "4640cfde", "tag": "r3"}


@pytest.fixture
def serving(pack, page):
    """An editor opened by a controller serving SERVED; `calls` records
    every switch it is asked for."""
    calls = []

    def serve(spec, persist):
        calls.append((spec, persist))
        return {"served": {"id": "a1b41f12deadbeef", "id8": "a1b41f12"}}

    app = create_app(
        EditorState("arena", pack),
        page,
        context=lambda: {"mode": "controller", "served": SERVED},
        serve=serve,
    )
    return local_client(app), calls


def test_a_switch_from_the_served_calibration_the_page_saw_is_taken(serving):
    client, calls = serving
    response = client.put(
        "/api/served", json={"spec": "a1b41f12", "expected": "4640CFDE"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["served"]["id8"] == "a1b41f12"
    assert calls == [("a1b41f12", False)]


def test_a_switch_from_a_calibration_no_longer_served_is_refused(serving):
    client, calls = serving
    response = client.put(
        "/api/served", json={"spec": "a1b41f12", "expected": "ffffffff"}
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == (
        "the controller now uses 4640cfde, not ffffffff: look again before switching"
    )
    assert detail["served"] == SERVED
    assert calls == []
    nothing = client.put("/api/served", json={"spec": "a1b41f12", "expected": ""})
    assert nothing.status_code == 409
    assert "now uses 4640cfde, not nothing" in nothing.json()["detail"]["message"]


def test_a_switch_without_an_expectation_is_taken_as_before(serving):
    client, calls = serving
    assert client.put("/api/served", json={"spec": "a1b41f12"}).status_code == 200
    assert calls == [("a1b41f12", False)]


def test_expecting_nothing_served_matches_a_controller_serving_nothing(pack, page):
    app = create_app(
        EditorState("arena", pack),
        page,
        context=lambda: {"mode": "controller", "served": None},
        serve=lambda spec, persist: {"served": {"id": spec}},
    )
    client = local_client(app)
    assert (
        client.put("/api/served", json={"spec": "a1", "expected": "none"}).status_code
        == 200
    )
    refused = client.put("/api/served", json={"spec": "a1", "expected": "4640cfde"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["served"] is None
