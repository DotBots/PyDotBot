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
    (folder / "site.toml").write_text(ARENA)
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
    preview = client.post("/api/preview", json=body["site"]).json()
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
        lambda name, pack, sock, headless: calls.append((name, pack, headless)),
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


def test_a_request_for_another_host_is_refused(client):
    response = client.get("/api/site", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_a_request_from_another_machine_is_refused_whatever_its_host(pack, page):
    app = create_app(EditorState("arena", pack), page)
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.7", 5))
    assert remote.get("/api/site").status_code == 403
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
