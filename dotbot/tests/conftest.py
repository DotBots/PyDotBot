"""Shared fixtures for the test suite."""

import pytest


@pytest.fixture(autouse=True)
def never_open_a_browser(monkeypatch):
    """Keep the suite from opening real browser windows.

    The controller opens the web UI on start unless `headless` is set, so a
    test that drives the full run loop reaches `webbrowser.open` for real and
    puts a tab on the developer's screen for every run.
    """
    monkeypatch.setattr("webbrowser.open", lambda *args, **kwargs: True)
