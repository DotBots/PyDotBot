# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `dotbot` CLI dispatcher.

Goal: lock the discovery surface (the four top-level groups + the `run`
process group + --help) so a future refactor doesn't silently drop a
command. We're NOT testing the underlying subcommand behavior here — that
lives in each subcommand's own test module (test_controller_app.py etc.).
"""

import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from dotbot.cli import _lazy
from dotbot.cli.main import _SUBCOMMANDS, cli
from dotbot.cli.run import _RUN_SUBCOMMANDS

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


# The top level is exactly four object-namespaces.
EXPECTED_SUBCOMMANDS = {
    "fw",
    "device",
    "swarm",
    "run",
}

# `run` groups the host-side processes (the former flat top-level verbs).
EXPECTED_RUN_SUBCOMMANDS = {
    "controller",
    "gateway",
    "simulator",
    "lh2-calibration",
    "demo",
    "keyboard",
    "joystick",
}

# Top-level groups whose --help backend lives in OTHER packages with their
# own protocol registries (swarmit). When pytest pre-loads dotbot.protocol
# via test_controller etc., importing swarmit in the same process triggers
# a duplicate payload-type registration (ValueError 0x81 already
# registered). This is the known cross-package protocol duplication
# captured in the consolidation roadmap §1; it never happens in real
# `dotbot <sub>` invocations (each shell run is a fresh process). We verify
# these in a subprocess.
_CROSS_PACKAGE_SUBS = {"swarm"}

# `run` subcommands whose lazy import is hostile to an in-process headless
# test: keyboard/joystick import pygame/pynput at module load;
# controller/simulator trigger dotbot.server's StaticFiles import-time mount.
_TELEOP_SUBS = {"keyboard", "joystick"}
_FRONTEND_DEPENDENT = {"controller", "simulator"}


@pytest.fixture
def runner():
    return CliRunner()


def test_root_help_lists_the_four_namespaces(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    # Check the rendered "Commands:" section specifically — the root help
    # prose also names the four groups, so a bare full-output substring
    # check would pass even if a command were dropped from the list.
    commands = result.output.split("Commands:", 1)[1]
    for name in EXPECTED_SUBCOMMANDS:
        assert name in commands, f"namespace `{name}` missing from rendered list"


def test_subcommand_table_matches_expected_set():
    """The static top-level `_SUBCOMMANDS` tuple is the wiring contract."""
    declared = {name for name, _, _ in _SUBCOMMANDS}
    assert declared == EXPECTED_SUBCOMMANDS


def test_run_help_lists_every_process(runner):
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0, result.output
    # Same as the root: assert against the rendered command list, not the
    # prose (which contains "controller"/"gateway"/"simulator"/"demo" as words).
    commands = result.output.split("Commands:", 1)[1]
    for name in EXPECTED_RUN_SUBCOMMANDS:
        assert name in commands, f"`run {name}` missing from rendered list"


def test_run_subcommand_table_matches_expected_set():
    """The static `_RUN_SUBCOMMANDS` tuple is the `run`-group contract."""
    declared = {name for name, _, _ in _RUN_SUBCOMMANDS}
    assert declared == EXPECTED_RUN_SUBCOMMANDS


def test_no_flat_process_verbs_at_top_level(runner):
    """The host-process verbs must NOT be reachable at the top level —
    they moved under `run`. This is the regression guard for the reorg."""
    for name in EXPECTED_RUN_SUBCOMMANDS:
        result = runner.invoke(cli, [name, "--help"])
        assert result.exit_code != 0, f"`dotbot {name}` should no longer exist"
        # Assert it failed because the command is GONE, not because a
        # re-added verb's backend errored at import (which also exits != 0).
        assert (
            "No such command" in result.output
        ), f"`dotbot {name}` failed for the wrong reason:\n{result.output}"


def test_version_flag(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "dotbot" in result.output


@pytest.mark.parametrize(
    "subcommand",
    sorted(EXPECTED_SUBCOMMANDS - _CROSS_PACKAGE_SUBS),
)
def test_top_level_group_help_works(runner, subcommand):
    """Every in-process top-level group's --help runs cleanly.

    swarm is excluded (its swarmit backend collides with PyDotBot's
    protocol registry inside a single pytest process — covered separately
    by the subprocess test). fw/device/run import no heavy backend at
    --help time.
    """
    result = runner.invoke(cli, [subcommand, "--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "subcommand",
    sorted(EXPECTED_RUN_SUBCOMMANDS - _TELEOP_SUBS),
)
def test_run_subcommand_help_works(runner, subcommand):
    """Every in-process `run` subcommand's --help runs cleanly.

    keyboard/joystick are excluded because they import pygame/pynput at
    module load time (headless-CI hostile). controller/sim trigger
    dotbot.server's StaticFiles import-time mount; skipped if the frontend
    bundle hasn't been built.
    """
    if subcommand in _FRONTEND_DEPENDENT and not _FRONTEND_PRESENT:
        pytest.skip(
            "frontend bundle missing; run `cd dotbot/frontend && npm run build`"
        )
    result = runner.invoke(cli, ["run", subcommand, "--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("subcommand", sorted(_CROSS_PACKAGE_SUBS))
def test_cross_package_subcommand_help_works(subcommand):
    """`dotbot swarm --help` in a clean process.

    A subprocess avoids the swarmit vs PyDotBot protocol-registry
    collision that only manifests inside pytest's shared-process test
    session. See _CROSS_PACKAGE_SUBS comment above.
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


def test_run_help_does_not_import_controller_app():
    """`dotbot run --help` must NOT eagerly import the heavy controller
    backend — that's the whole point of the lazy `run` group.

    Run in a fresh subprocess so sys.modules is clean (other test modules
    in the shared pytest process may already have imported it).
    """
    code = (
        "import sys;"
        "from click.testing import CliRunner;"
        "from dotbot.cli.main import cli;"
        "r = CliRunner().invoke(cli, ['run', '--help']);"
        "assert r.exit_code == 0, r.output;"
        "heavy = [m for m in ('dotbot.controller_app','dotbot.server',"
        "'pygame','pynput','dotbot.calibration') if m in sys.modules];"
        "assert not heavy, f'run --help eagerly imported: {heavy}';"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_fw_make_is_mounted_under_fw(runner):
    """The make escape hatch lives at `dotbot fw make`, not top-level."""
    result = runner.invoke(cli, ["fw", "make", "--help"])
    assert result.exit_code == 0, result.output
    assert "SEGGER_DIR" in result.output
    # And it is gone from the top level.
    assert runner.invoke(cli, ["make", "--help"]).exit_code != 0


def test_fw_mock_exits_nonzero(runner):
    """fw stubs must surface that they're not implemented (exit 2)."""
    result = runner.invoke(cli, ["fw", "new", "myapp"])
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()


def test_demo_list(runner):
    """`dotbot run demo --list` enumerates demos including `qr`."""
    result = runner.invoke(cli, ["run", "demo", "--list"])
    assert result.exit_code == 0
    assert "qr" in result.output


def test_demo_default_lists(runner):
    """`dotbot run demo` with no subcommand also lists (discoverability)."""
    result = runner.invoke(cli, ["run", "demo"])
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


def test_lh2_calibration_missing_extras_prints_hint(runner, monkeypatch):
    """When [calibrate] extras aren't installed, `dotbot run lh2-calibration`
    (default `collect`) exits 1 with a pip-install hint instead of a
    traceback."""
    # Simulate the dotbot.calibration.cli module being unavailable.
    # `monkeypatch.setitem(sys.modules, name, None)` makes
    # `from name import ...` raise ImportError per CPython's import
    # protocol — same condition as a real missing extra.
    monkeypatch.setitem(sys.modules, "dotbot.calibration.cli", None)
    result = runner.invoke(cli, ["run", "lh2-calibration"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_lh2_calibration_collect_missing_extras_prints_hint(runner, monkeypatch):
    """`dotbot run lh2-calibration collect` is the explicit alias for the
    default; same install-hint fallback when extras are missing."""
    monkeypatch.setitem(sys.modules, "dotbot.calibration.cli", None)
    result = runner.invoke(cli, ["run", "lh2-calibration", "collect"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_lh2_calibration_apply_missing_extras_prints_hint(runner, monkeypatch):
    """`dotbot run lh2-calibration apply` falls back to the install hint
    when the calibration runtime deps aren't available."""
    monkeypatch.setitem(sys.modules, "dotbot.calibration.exporter", None)
    monkeypatch.setitem(sys.modules, "dotbot.calibration.lighthouse2", None)
    result = runner.invoke(cli, ["run", "lh2-calibration", "apply", "/tmp/lh2.h"])
    assert result.exit_code == 1, result.output
    assert "pip install dotbot[calibrate]" in result.output


def test_lh2_calibration_apply_no_saved_calibration(runner, tmp_path, monkeypatch):
    """`apply` exits 1 with a clear message when no saved calibration
    exists at the expected location."""
    # Point LighthouseManager at an empty tmp dir so load_calibration
    # finds nothing.
    monkeypatch.setattr("dotbot.calibration.lighthouse2.CALIBRATION_DIR", tmp_path)
    result = runner.invoke(
        cli, ["run", "lh2-calibration", "apply", str(tmp_path / "out.h")]
    )
    assert result.exit_code == 1, result.output
    assert "No saved calibration" in result.output
