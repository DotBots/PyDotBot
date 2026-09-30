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


@pytest.fixture
def client(pack, page, tmp_path):
    calibrations = tmp_path / "home-calibrations" / "arena"
    return TestClient(create_app(EditorState("arena", pack, [calibrations]), page))


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
    assert TestClient(app).post("/api/done").status_code == 200
    assert calls == [1]


@pytest.fixture
def served(monkeypatch):
    calls = []
    monkeypatch.setattr(
        site_cmd,
        "_serve_editor",
        lambda name, pack, port, headless: calls.append((name, pack, headless)),
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
