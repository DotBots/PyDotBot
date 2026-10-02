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


@pytest.fixture(autouse=True)
def no_user_config(monkeypatch, tmp_path_factory):
    """Keep every test away from this machine's ~/.dotbot/dotbot.toml, and
    from a ~/.dotbot/config.toml still under its former name."""
    home = tmp_path_factory.mktemp("home-dotbot")
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", home / "dotbot.toml")


@pytest.fixture(autouse=True)
def no_swarm_server(monkeypatch):
    """Keep `run controller` from probing or starting a real swarm server;
    returns the mock standing in for `swarm_serve.start`."""
    from unittest.mock import MagicMock

    start = MagicMock(name="swarm_serve.start")
    for name in (
        "DOTBOT_SWARMIT_URL",
        "DOTBOT_SWARM_SERVE",
        "DOTBOT_RUN_CONTROLLER_SWARM_SERVE",
        "SWARMIT_SERVER_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("dotbot.swarm_serve.server_settings", lambda *a, **k: None)
    monkeypatch.setattr("dotbot.swarm_serve.start", start)
    monkeypatch.setattr("dotbot.swarm_serve.watch", lambda *a, **k: None)
    monkeypatch.setattr("dotbot.swarm_serve.port_taken", lambda *a: False)
    return start
