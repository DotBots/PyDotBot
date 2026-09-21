"""Tests for the build identity the controller reports."""

import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from dotbot.build import build_info
from dotbot.server import api

PACKAGE_DIR = Path(__file__).resolve().parent.parent
CHECKOUT = PACKAGE_DIR.parent

client = AsyncClient(transport=ASGITransport(app=api), base_url="http://testserver")


@pytest.fixture(autouse=True)
def fresh_cache():
    """The answer is cached for the process, so each test starts from none."""
    build_info.cache_clear()
    yield
    build_info.cache_clear()


def fake_git(answers, calls=None):
    """Stand in for subprocess.run, answering git by its arguments.

    `answers` maps the arguments after `git -C <package dir>` to a
    `(returncode, stdout)` pair; an argument tuple that is not in the map
    answers like git does for an unknown object, with a non-zero code.
    """

    def run(cmd, **kwargs):
        assert cmd[:3] == ["git", "-C", str(PACKAGE_DIR)]
        args = tuple(cmd[3:])
        if calls is not None:
            calls.append(args)
        code, out = answers.get(args, (128, ""))
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

    return run


CLEAN_CHECKOUT = {
    ("rev-parse", "--show-toplevel"): (0, f"{CHECKOUT}\n"),
    ("rev-parse", "--short", "HEAD"): (0, "6573d53\n"),
    ("status", "--porcelain"): (0, ""),
}


def test_a_checkout_reports_its_commit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_git(CLEAN_CHECKOUT))

    info = build_info()

    assert info["commit"] == "6573d53"
    assert info["dirty"] is False
    assert isinstance(info["version"], str)


def test_uncommitted_changes_make_the_checkout_dirty(monkeypatch):
    answers = dict(CLEAN_CHECKOUT)
    answers[("status", "--porcelain")] = (0, " M dotbot/server.py\n")
    monkeypatch.setattr(subprocess, "run", fake_git(answers))

    assert build_info()["dirty"] is True


def test_git_is_consulted_once(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", fake_git(CLEAN_CHECKOUT, calls))

    build_info()
    build_info()

    assert len(calls) == 3


def test_a_missing_git_reports_the_version_alone(monkeypatch):
    def no_git(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(subprocess, "run", no_git)

    info = build_info()

    assert set(info) == {"version"}


def test_a_directory_that_is_not_a_repository_reports_the_version_alone(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_git({}))

    assert set(build_info()) == {"version"}


def test_a_hanging_git_reports_the_version_alone(monkeypatch):
    def hangs(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", hangs)

    assert set(build_info()) == {"version"}


def test_an_install_inside_an_unrelated_repository_reports_no_commit(monkeypatch):
    """A wheel installed under someone else's clone is not that clone's build."""
    answers = dict(CLEAN_CHECKOUT)
    answers[("rev-parse", "--show-toplevel")] = (0, "/home/someone/other-repo\n")
    monkeypatch.setattr(subprocess, "run", fake_git(answers))

    assert set(build_info()) == {"version"}


@pytest.mark.asyncio
async def test_the_build_route_reports_the_checkout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_git(CLEAN_CHECKOUT))

    result = await client.get("/controller/build")

    assert result.status_code == 200
    body = result.json()
    assert body["commit"] == "6573d53"
    assert body["dirty"] is False


@pytest.mark.asyncio
async def test_the_build_route_omits_the_commit_without_git(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_git({}))

    result = await client.get("/controller/build")

    assert result.status_code == 200
    assert set(result.json()) == {"version"}
