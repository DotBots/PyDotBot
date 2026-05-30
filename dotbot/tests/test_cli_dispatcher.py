# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `dotbot` CLI dispatcher.

Goal: lock the discovery surface (subcommand list + --help) so a
future refactor doesn't silently drop a command. We're NOT testing
the underlying subcommand behavior here — that lives in each
subcommand's own test module (test_controller_app.py etc.).
"""

import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from dotbot.cli import _lazy
from dotbot.cli.main import _SUBCOMMANDS, cli

# Importing dotbot.controller (transitively, dotbot.server) blows up at
# module-import time if the React UI hasn't been built — FastAPI's
# StaticFiles mount asserts the directory exists. That's a pre-existing
# import-time side effect, not something the CLI scaffold introduced.
# Skip the subcommands whose lazy import triggers it when the bundle
# isn't built (typical for fresh editable installs).
_FRONTEND_BUILD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
    "build",
)
_FRONTEND_PRESENT = os.path.isdir(_FRONTEND_BUILD)
_needs_frontend = pytest.mark.skipif(
    not _FRONTEND_PRESENT,
    reason=(
        "frontend bundle missing — run `cd dotbot/frontend && npm run build`. "
        "The CLI scaffold itself does not depend on the bundle; this skip "
        "exists because dotbot.server.api.mount(StaticFiles) runs at import."
    ),
)


EXPECTED_SUBCOMMANDS = {
    "controller",
    "sim",
    "gateway",
    "device",
    "swarm",
    "calibrate-lh2",
    "demo",
    "fw",
    "make",
    "keyboard",
    "joystick",
}

# Subcommands whose --help backends live in OTHER packages with their
# own protocol registries (swarmit). When pytest pre-loads
# dotbot.protocol via test_controller etc., importing swarmit in the
# same process triggers a duplicate payload-type registration
# (ValueError 0x81 already registered). This is the known cross-package
# protocol duplication captured in the consolidation roadmap §1; it
# never happens in real `dotbot <sub>` invocations (each shell run is
# a fresh process). We verify these in a subprocess.
#
# `calibrate` used to be in this set; after Phase 2's fold it's in-tree
# and uses dotbot's own (vendored) modules, no collision possible.
_CROSS_PACKAGE_SUBS = {"swarm"}


@pytest.fixture
def runner():
    return CliRunner()


def test_root_help_lists_every_subcommand(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    for name in EXPECTED_SUBCOMMANDS:
        assert name in result.output, f"subcommand `{name}` missing from --help"


def test_subcommand_table_matches_expected_set():
    """The static `_SUBCOMMANDS` tuple is the wiring contract."""
    declared = {name for name, _, _ in _SUBCOMMANDS}
    assert declared == EXPECTED_SUBCOMMANDS


def test_version_flag(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "dotbot" in result.output


_FRONTEND_DEPENDENT = {"controller", "sim"}


@pytest.mark.parametrize(
    "subcommand",
    sorted(EXPECTED_SUBCOMMANDS - {"keyboard", "joystick"} - _CROSS_PACKAGE_SUBS),
)
def test_subcommand_help_works(runner, subcommand):
    """Every in-process subcommand's --help runs cleanly.

    keyboard/joystick are excluded because they import pygame/pynput at
    module load time (headless-CI hostile). swarm is excluded because
    its swarmit backend collides with PyDotBot's protocol registry
    inside a single pytest process — covered separately by
    test_cross_package_subcommand_help_works in a subprocess.
    controller/sim trigger dotbot.server's StaticFiles import-time mount;
    skipped if the frontend bundle hasn't been built.
    """
    if subcommand in _FRONTEND_DEPENDENT and not _FRONTEND_PRESENT:
        pytest.skip(
            "frontend bundle missing; run `cd dotbot/frontend && npm run build`"
        )
    result = runner.invoke(cli, [subcommand, "--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("subcommand", sorted(_CROSS_PACKAGE_SUBS))
def test_cross_package_subcommand_help_works(subcommand):
    """`dotbot swarm --help` in a clean process.

    A subprocess avoids the swarmit/lh2-calibration vs PyDotBot
    protocol-registry collision that only manifests inside pytest's
    shared-process test session. See _CROSS_PACKAGE_SUBS comment above.
    """
    result = subprocess.run(
        [sys.executable, "-m", "dotbot.cli", subcommand, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    # Sanity: the help text should mention the subcommand or its purpose.
    combined = result.stdout + result.stderr
    assert "Usage" in combined


def test_fw_mock_exits_nonzero(runner):
    """fw stubs must surface that they're not implemented (exit 2)."""
    result = runner.invoke(cli, ["fw", "new", "myapp"])
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()


def test_demo_list(runner):
    """`dotbot demo --list` enumerates demos including `qr`."""
    result = runner.invoke(cli, ["demo", "--list"])
    assert result.exit_code == 0
    assert "qr" in result.output


def test_demo_default_lists(runner):
    """`dotbot demo` with no subcommand also lists (discoverability)."""
    result = runner.invoke(cli, ["demo"])
    assert result.exit_code == 0
    assert "qr" in result.output


def test_lazy_subcommand_missing_extra_exits_with_hint():
    """A subcommand whose backend isn't installed prints an install hint."""

    def loader():
        raise ImportError("simulated missing dep")

    stub = _lazy.lazy_subcommand(
        name="fake",
        extra="fake-extra",
        package="fake-pkg",
        help="A fake subcommand for the test.",
        loader=loader,
    )

    runner = CliRunner()
    result = runner.invoke(stub, [])
    assert result.exit_code == 1
    assert "pip install dotbot[fake-extra]" in result.output
    assert "fake-pkg" in result.output


def test_python_m_dotbot_cli_entrypoint(runner):
    """`python -m dotbot.cli` must dispatch through the same group."""
    # In-process check that the __main__ module routes to the same group.
    from dotbot.cli import __main__ as cli_main_module

    assert cli_main_module.cli is cli


def test_python_m_dotbot_cli_help_subprocess():
    """End-to-end: `python -m dotbot.cli --help` runs in a fresh process."""
    result = subprocess.run(
        [sys.executable, "-m", "dotbot.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    for name in EXPECTED_SUBCOMMANDS:
        assert name in result.stdout, f"`{name}` missing from `python -m` help"


def test_python_m_dotbot_cli_version_subprocess():
    """End-to-end: `python -m dotbot.cli --version` prints a version line."""
    result = subprocess.run(
        [sys.executable, "-m", "dotbot.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "dotbot" in result.stdout


@_needs_frontend
def test_legacy_console_scripts_still_resolve():
    """Backwards-compat aliases (dotbot-controller, dotbot-keyboard,
    dotbot-joystick) must still resolve to importable Click commands.

    Checks the entry-point targets via direct import. Skipped without
    the frontend bundle because dotbot.controller_app pulls in
    dotbot.server which mounts StaticFiles at import.
    """
    import click

    from dotbot.controller_app import main as controller_main
    from dotbot.joystick import main as joystick_main
    from dotbot.keyboard import main as keyboard_main

    for cmd in (controller_main, keyboard_main, joystick_main):
        assert isinstance(cmd, click.Command), f"{cmd!r} is not a Click cmd"


def test_calibrate_lh2_missing_extras_prints_hint(runner, monkeypatch):
    """When [calibrate] extras aren't installed, `dotbot calibrate-lh2`
    (default `collect`) exits 1 with a pip-install hint instead of a
    traceback."""
    # Simulate the dotbot.calibration.cli module being unavailable.
    # `monkeypatch.setitem(sys.modules, name, None)` makes
    # `from name import ...` raise ImportError per CPython's import
    # protocol — same condition as a real missing extra.
    monkeypatch.setitem(sys.modules, "dotbot.calibration.cli", None)
    result = runner.invoke(cli, ["calibrate-lh2"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_calibrate_lh2_collect_missing_extras_prints_hint(runner, monkeypatch):
    """`dotbot calibrate-lh2 collect` is the explicit alias for the
    default; same install-hint fallback when extras are missing."""
    monkeypatch.setitem(sys.modules, "dotbot.calibration.cli", None)
    result = runner.invoke(cli, ["calibrate-lh2", "collect"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_calibrate_lh2_apply_missing_extras_prints_hint(runner, monkeypatch):
    """`dotbot calibrate-lh2 apply` falls back to the install hint
    when the calibration runtime deps aren't available."""
    monkeypatch.setitem(sys.modules, "dotbot.calibration.exporter", None)
    monkeypatch.setitem(sys.modules, "dotbot.calibration.lighthouse2", None)
    result = runner.invoke(cli, ["calibrate-lh2", "apply", "/tmp/lh2.h"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_calibrate_lh2_apply_no_saved_calibration(runner, tmp_path, monkeypatch):
    """`apply` exits 1 with a clear message when no saved calibration
    exists at the expected location."""
    # Point LighthouseManager at an empty tmp dir so load_calibration
    # finds nothing.
    monkeypatch.setattr("dotbot.calibration.lighthouse2.CALIBRATION_DIR", tmp_path)
    result = runner.invoke(cli, ["calibrate-lh2", "apply", str(tmp_path / "out.h")])
    assert result.exit_code == 1, result.output
    assert "No saved calibration" in result.output
