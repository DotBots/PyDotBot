# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `dotbot` CLI dispatcher.

Goal: lock the discovery surface (subcommand list + --help) so a
future refactor doesn't silently drop a command. We're NOT testing
the underlying subcommand behavior here — that lives in each
subcommand's own test module (test_controller_app.py etc.).
"""

import subprocess
import sys

import pytest
from click.testing import CliRunner

from dotbot.cli import _lazy
from dotbot.cli.main import _SUBCOMMANDS, cli

EXPECTED_SUBCOMMANDS = {
    "controller",
    "sim",
    "testbed",
    "calibrate",
    "demo",
    "fw",
    "keyboard",
    "joystick",
}

# Subcommands whose --help backends live in OTHER packages with their
# own protocol registries (swarmit, dotbot-lh2-calibration). When
# pytest pre-loads dotbot.protocol via test_controller etc., importing
# those packages in the same process triggers a duplicate payload-type
# registration (ValueError 0x81 already registered). This is the known
# cross-package protocol duplication captured in the consolidation
# roadmap §1; it never happens in real `dotbot <sub>` invocations
# (each shell run is a fresh process). We verify these in a subprocess.
_CROSS_PACKAGE_SUBS = {"testbed", "calibrate"}


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


@pytest.mark.parametrize(
    "subcommand",
    sorted(EXPECTED_SUBCOMMANDS - {"keyboard", "joystick"} - _CROSS_PACKAGE_SUBS),
)
def test_subcommand_help_works(runner, subcommand):
    """Every in-process subcommand's --help runs cleanly.

    keyboard/joystick are excluded because they import pygame/pynput at
    module load time (headless-CI hostile). testbed/calibrate are
    excluded because their backends collide with PyDotBot's protocol
    registry inside a single pytest process — covered separately by
    test_cross_package_subcommand_help_works in a subprocess.
    """
    result = runner.invoke(cli, [subcommand, "--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("subcommand", sorted(_CROSS_PACKAGE_SUBS))
def test_cross_package_subcommand_help_works(subcommand):
    """`dotbot testbed --help` / `dotbot calibrate --help` in a clean process.

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
    # The __main__ module's behavior is tested by importing and asserting
    # it references the same cli object — running it as a subprocess
    # would slow tests down without adding coverage.
    from dotbot.cli import __main__ as cli_main_module

    assert cli_main_module.cli is cli
