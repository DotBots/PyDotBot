"""Shared fixtures for the test suite."""

import pytest

from dotbot.tests.camera_fixtures import synthetic_camera  # noqa: F401


@pytest.fixture(autouse=True)
def never_open_a_browser(monkeypatch):
    """Keep the suite from opening real browser windows.

    The controller opens the web UI on start unless `headless` is set, so a
    test that drives the full run loop reaches `webbrowser.open` for real and
    puts a tab on the developer's screen for every run.
    """
    monkeypatch.setattr("webbrowser.open", lambda *args, **kwargs: True)


@pytest.fixture(scope="session")
def _empty_user_sites(tmp_path_factory):
    return tmp_path_factory.mktemp("user-sites")


@pytest.fixture(autouse=True)
def no_user_site_packs(monkeypatch, _empty_user_sites):
    """Keep every test away from this machine's ~/.dotbot/sites packs."""
    monkeypatch.setattr("dotbot.site_packs.USER_SITES_DIR", _empty_user_sites)
