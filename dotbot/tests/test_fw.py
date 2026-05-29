# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot fw` (bare firmware build/clean/targets/artifacts).

These tests stub `subprocess.call` / `subprocess.run` so they don't
need a SEGGER install or a DotBot-firmware checkout — they verify the
CLI's argument shape, validations, and the command line passed to
make, not the actual build.
"""


import click
import pytest
from click.testing import CliRunner

from dotbot.cli import _fw_helpers
from dotbot.cli.fw import cmd as fw_cmd


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Pretend repos/DotBot-firmware exists at a tmp path with a Makefile."""
    repo = tmp_path / "fake-dotbot-firmware"
    repo.mkdir()
    (repo / "Makefile").write_text("# fake\n")
    monkeypatch.setenv("DOTBOT_FIRMWARE_REPO", str(repo))
    return repo


@pytest.fixture
def fake_segger(tmp_path, monkeypatch):
    """Pretend SES is installed at a tmp path with a runnable emBuild."""
    segger = tmp_path / "fake-segger"
    (segger / "bin").mkdir(parents=True)
    embuild = segger / "bin" / "emBuild"
    embuild.write_text("#!/bin/sh\nexit 0\n")
    embuild.chmod(0o755)
    monkeypatch.setenv("SEGGER_DIR", str(segger))
    return segger


@pytest.fixture
def capture_make(monkeypatch):
    """Replace `subprocess.call` so we capture the make command line."""
    calls = []

    def fake_call(cmd, cwd=None, env=None):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env})
        return 0

    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.call", fake_call)
    return calls


def test_fw_help_lists_real_subcommands(runner):
    result = runner.invoke(fw_cmd, ["--help"])
    assert result.exit_code == 0
    for sub in ("build", "clean", "targets", "artifacts"):
        assert sub in result.output
    # Cross-reference to the sandbox path:
    assert "swarm fw" in result.output


def test_fw_targets_lists_bare_targets_one_per_line(runner):
    result = runner.invoke(fw_cmd, ["targets"])
    assert result.exit_code == 0
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    assert "dotbot-v3" in lines
    assert "sailbot-v1" in lines
    # No sandbox-* targets under the bare namespace:
    assert not any(ln.startswith("sandbox-") for ln in lines)
    # One target per line, no decoration:
    assert all(ln == ln.strip() for ln in lines)


def test_fw_build_rejects_sandbox_target_with_redirect_hint(runner):
    """Sandbox targets must be rejected with a pointer to `swarm fw`."""
    result = runner.invoke(fw_cmd, ["build", "sandbox-dotbot-v3"])
    assert result.exit_code != 0
    assert "swarm fw build dotbot-v3" in result.output


def test_fw_build_rejects_unknown_target_with_suggestion(runner):
    result = runner.invoke(fw_cmd, ["build", "dotbotv3"])  # missing dash
    assert result.exit_code != 0
    assert "dotbot-v3" in result.output  # didyoumean suggestion


def test_fw_build_default_target_is_dotbot_v3(
    runner, fake_repo, fake_segger, capture_make
):
    """No-arg build defaults to dotbot-v3 (Geovane's daily target)."""
    result = runner.invoke(fw_cmd, ["build"])
    assert result.exit_code == 0, result.output
    assert len(capture_make) == 1
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=dotbot-v3" in cmd
    assert "BUILD_CONFIG=Release" in cmd  # default per the plan


def test_fw_build_passes_incremental_by_default(
    runner, fake_repo, fake_segger, capture_make
):
    """Default is `BUILD_MODE=-build` (incremental) for fast edit/build loop."""
    result = runner.invoke(fw_cmd, ["build", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_MODE=-build" in cmd
    assert "BUILD_MODE=-rebuild" not in cmd


def test_fw_build_rebuild_flag_forces_full_rebuild(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["build", "dotbot-v3", "--rebuild"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_MODE=-rebuild" in cmd


def test_fw_build_quiet_by_default(runner, fake_repo, fake_segger, capture_make):
    """Default is `QUIET=1` to suppress SES `-verbose -echo` flood."""
    result = runner.invoke(fw_cmd, ["build", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "QUIET=1" in cmd


def test_fw_build_verbose_drops_quiet(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(fw_cmd, ["build", "dotbot-v3", "-v"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "QUIET=1" not in cmd


def test_fw_build_with_app_appends_project_name(
    runner, fake_repo, fake_segger, capture_make, monkeypatch
):
    """`--app NAME` appends the project so make builds only that one."""
    monkeypatch.setattr(
        "dotbot.cli.fw.list_projects", lambda target: ["dotbot", "lh2_calibration"]
    )
    result = runner.invoke(fw_cmd, ["build", "dotbot-v3", "--app", "dotbot"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert cmd[-1] == "dotbot"


def test_fw_build_rejects_unavailable_project(
    runner, fake_repo, fake_segger, monkeypatch
):
    """Project not in the post-filter list is rejected pre-make."""
    monkeypatch.setattr("dotbot.cli.fw.list_projects", lambda target: ["dotbot"])
    result = runner.invoke(fw_cmd, ["build", "dotbot-v1", "--app", "dotbot_gateway"])
    assert result.exit_code != 0
    assert "not available" in result.output


def test_fw_clean_invokes_make_clean(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(fw_cmd, ["clean", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=dotbot-v3" in cmd
    assert "clean" in cmd


def test_fw_artifacts_invokes_make_artifacts(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["artifacts", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "artifacts" in cmd


def test_fw_artifacts_print_path_requires_app(runner, fake_repo, fake_segger):
    """`--print-path` without `--app` exits with a hint."""
    result = runner.invoke(fw_cmd, ["artifacts", "dotbot-v3", "--print-path"])
    assert result.exit_code != 0
    assert "--app" in result.output


def test_fw_artifacts_print_path_returns_makefile_formula(
    runner, fake_repo, fake_segger
):
    result = runner.invoke(
        fw_cmd, ["artifacts", "dotbot-v3", "--app", "dotbot", "--print-path"]
    )
    assert result.exit_code == 0, result.output
    out = result.output.strip()
    assert out.endswith("apps/dotbot/Output/dotbot-v3/Release/Exe/dotbot-dotbot-v3.hex")


def test_fw_new_still_not_implemented(runner):
    """`new` is deferred to a separate templates plan."""
    result = runner.invoke(fw_cmd, ["new", "my-experiment"])
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()


def test_fw_flash_still_not_implemented(runner):
    """`flash` is deferred; SES + J-Link cover the bare path today."""
    result = runner.invoke(fw_cmd, ["flash", "/tmp/dummy.hex"])
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()


# ── Sandbox subgroup (`dotbot swarm fw`) ────────────────────────────────
# These tests invoke the sandbox-fw Click group directly, bypassing the
# `dotbot swarm` parent (which loads swarmit and triggers the
# protocol-registry collision documented in test_cli_dispatcher.py).


from dotbot.cli._sandbox_fw import cmd as sandbox_fw_cmd  # noqa: E402


def test_sandbox_fw_help_lists_real_subcommands(runner):
    result = runner.invoke(sandbox_fw_cmd, ["--help"])
    assert result.exit_code == 0
    for sub in ("build", "clean", "targets", "artifacts"):
        assert sub in result.output
    # Cross-reference to the bare path:
    assert "dotbot fw" in result.output
    # `new` and `flash` aren't valid sandbox subcommands (no scaffolding,
    # OTA flash lives under `dotbot swarm flash`).
    assert "new" not in result.output
    assert "flash" not in result.output


def test_sandbox_fw_targets_lists_boards(runner):
    result = runner.invoke(sandbox_fw_cmd, ["targets"])
    assert result.exit_code == 0
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    assert "dotbot-v3" in lines
    assert "nrf5340dk" in lines
    # User-facing names — no `sandbox-` prefix:
    assert not any(ln.startswith("sandbox-") for ln in lines)


def test_sandbox_fw_build_rejects_sandbox_prefix(runner):
    """User shouldn't pass `sandbox-dotbot-v3` — drop the prefix."""
    result = runner.invoke(sandbox_fw_cmd, ["build", "sandbox-dotbot-v3"])
    assert result.exit_code != 0
    assert "Drop the `sandbox-` prefix" in result.output


def test_sandbox_fw_build_rejects_unknown_board(runner):
    result = runner.invoke(sandbox_fw_cmd, ["build", "dotbot-v9"])
    assert result.exit_code != 0
    assert "Unknown sandbox board" in result.output


def test_sandbox_fw_build_prepends_sandbox_prefix_to_target(
    runner, fake_repo, fake_segger, capture_make
):
    """User-typed `dotbot-v3` becomes `BUILD_TARGET=sandbox-dotbot-v3`."""
    result = runner.invoke(sandbox_fw_cmd, ["build", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=sandbox-dotbot-v3" in cmd


def test_sandbox_fw_build_default_board(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(sandbox_fw_cmd, ["build"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=sandbox-dotbot-v3" in cmd
    assert "BUILD_CONFIG=Release" in cmd


def test_sandbox_fw_artifacts_print_path_uses_bin_extension(
    runner, fake_repo, fake_segger
):
    """Sandbox artifacts are `.bin` (what swarmit OTA flashes), not `.hex`."""
    result = runner.invoke(
        sandbox_fw_cmd,
        ["artifacts", "dotbot-v3", "--app", "dotbot", "--print-path"],
    )
    assert result.exit_code == 0, result.output
    out = result.output.strip()
    assert out.endswith(
        "apps-sandbox/dotbot/Output/sandbox-dotbot-v3/Release/Exe/"
        "dotbot-sandbox-dotbot-v3.bin"
    )


def test_sandbox_fw_clean_invokes_make_clean(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(sandbox_fw_cmd, ["clean", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=sandbox-dotbot-v3" in cmd
    assert "clean" in cmd


# ── Helper-level tests ──────────────────────────────────────────────────


def test_resolve_segger_dir_uses_env_first(tmp_path, monkeypatch):
    monkeypatch.setenv("SEGGER_DIR", str(tmp_path))
    assert _fw_helpers.resolve_segger_dir() == tmp_path


def test_resolve_segger_dir_errors_when_unset_on_linux(monkeypatch):
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    monkeypatch.setattr("dotbot.cli._fw_helpers.sys.platform", "linux")
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_segger_dir()
    assert "SEGGER_DIR" in str(excinfo.value)


def test_resolve_firmware_repo_walks_up_from_cwd(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    repo = workspace / "repos" / "DotBot-firmware"
    repo.mkdir(parents=True)
    (repo / "Makefile").touch()
    inner = workspace / "deep" / "subdir"
    inner.mkdir(parents=True)
    monkeypatch.chdir(inner)
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    assert _fw_helpers.resolve_firmware_repo() == repo


def test_resolve_firmware_repo_errors_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    with pytest.raises(click.ClickException):
        _fw_helpers.resolve_firmware_repo()
