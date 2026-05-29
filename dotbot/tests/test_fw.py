# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot fw` (bare firmware build/clean/targets/artifacts).

These tests stub `subprocess.call` / `subprocess.run` so they don't
need a SEGGER install or a DotBot-firmware checkout — they verify the
CLI's argument shape, validations, and the command line passed to
make, not the actual build.

The single exception is `test_bare_targets_match_makefile_list_targets`,
which shells out to `make list-targets` in the real DotBot-firmware
repo to catch silent drift between the CLI's hardcoded enums and the
Makefile. It self-skips if the workspace layout or the `list-targets`
rule isn't available.
"""

import subprocess
from pathlib import Path

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
    """Stub `subprocess.call` (the actual `make` invocation) and
    `subprocess.run` (used by `list_projects` to enumerate buildable
    apps) so the test never touches a real Makefile.
    """
    calls = []

    def fake_call(cmd, cwd=None, env=None):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env})
        return 0

    def fake_run(cmd, cwd=None, env=None, **kw):
        # Mimic `make -s list-projects` returning a small default set
        # so build() can enumerate "apps to build" without erroring.
        class _R:
            returncode = 0
            stdout = "dotbot\nlh2_calibration\nlog_dump\n"
            stderr = ""

        return _R()

    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.call", fake_call)
    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.run", fake_run)
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
    result = runner.invoke(fw_cmd, ["build", "--target", "sandbox-dotbot-v3"])
    assert result.exit_code != 0
    assert "swarm fw build dotbot-v3" in result.output


def test_fw_build_rejects_unknown_target_with_suggestion(runner):
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbotv3"])  # missing dash
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
    """Default is `BUILD_MODE=` (empty → emBuild's natural incremental
    mode) for fast edit/build loop. SES 8.22a has no `-build` flag; the
    only valid action flag is `-rebuild`."""
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_MODE=" in cmd
    assert "BUILD_MODE=-rebuild" not in cmd


def test_fw_build_rebuild_flag_forces_full_rebuild(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3", "--rebuild"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_MODE=-rebuild" in cmd


def test_fw_build_quiet_by_default(runner, fake_repo, fake_segger, capture_make):
    """Default is `QUIET=1` to suppress SES `-verbose -echo` flood."""
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "QUIET=1" in cmd


def test_fw_build_verbose_drops_quiet(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3", "-v"])
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
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3", "--app", "dotbot"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert cmd[-1] == "dotbot"


def test_fw_build_rejects_unavailable_project(
    runner, fake_repo, fake_segger, monkeypatch
):
    """Project not in the post-filter list is rejected pre-make."""
    monkeypatch.setattr("dotbot.cli.fw.list_projects", lambda target: ["dotbot"])
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v1", "--app", "dotbot_gateway"])
    assert result.exit_code != 0
    assert "not available" in result.output


def test_fw_clean_invokes_make_clean(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(fw_cmd, ["clean", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=dotbot-v3" in cmd
    assert "clean" in cmd


def test_fw_artifacts_builds_then_collects_to_user_dir(
    runner, fake_repo, fake_segger, capture_make, tmp_path
):
    """`dotbot fw artifacts` no longer runs `make artifacts` (whose path
    formula is buggy for sandbox and writes to the firmware repo's
    `artifacts/`). It does a regular build, then copies the produced
    artifacts to the user-chosen out dir (default `./artifacts/`)."""
    out = tmp_path / "user-artifacts"
    result = runner.invoke(
        fw_cmd, ["artifacts", "--target", "dotbot-v3", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    # Builds (no explicit make target), doesn't invoke `make artifacts`.
    assert "artifacts" not in cmd
    assert "BUILD_TARGET=dotbot-v3" in cmd
    # The user-chosen out dir was created.
    assert out.is_dir()


def test_fw_artifacts_print_path_requires_app(runner, fake_repo, fake_segger):
    """`--print-path` without `--app` exits with a hint."""
    result = runner.invoke(fw_cmd, ["artifacts", "--target", "dotbot-v3", "--print-path"])
    assert result.exit_code != 0
    assert "--app" in result.output


def test_fw_artifacts_print_path_returns_makefile_formula(
    runner, fake_repo, fake_segger
):
    result = runner.invoke(
        fw_cmd, ["artifacts", "--target", "dotbot-v3", "--app", "dotbot", "--print-path"]
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
    result = runner.invoke(sandbox_fw_cmd, ["build", "--target", "sandbox-dotbot-v3"])
    assert result.exit_code != 0
    assert "Drop the `sandbox-` prefix" in result.output


def test_sandbox_fw_build_rejects_unknown_board(runner):
    result = runner.invoke(sandbox_fw_cmd, ["build", "--target", "dotbot-v9"])
    assert result.exit_code != 0
    assert "Unknown sandbox board" in result.output


def test_sandbox_fw_build_prepends_sandbox_prefix_to_target(
    runner, fake_repo, fake_segger, capture_make
):
    """User-typed `dotbot-v3` becomes `BUILD_TARGET=sandbox-dotbot-v3`."""
    result = runner.invoke(sandbox_fw_cmd, ["build", "--target", "dotbot-v3"])
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
        ["artifacts", "--target", "dotbot-v3", "--app", "dotbot", "--print-path"],
    )
    assert result.exit_code == 0, result.output
    out = result.output.strip()
    # SES's `$(BuildTarget)` macro now matches the make-level BUILD_TARGET
    # (including the `sandbox-` prefix), so Output paths are flavor-distinct.
    assert out.endswith(
        "apps-sandbox/dotbot/Output/sandbox-dotbot-v3/Release/Exe/"
        "dotbot-sandbox-dotbot-v3.bin"
    )


def test_sandbox_fw_clean_invokes_make_clean(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(sandbox_fw_cmd, ["clean", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=sandbox-dotbot-v3" in cmd
    assert "clean" in cmd


def test_sandbox_fw_artifacts_collected_filename_distinct_from_bare(
    runner, fake_repo, fake_segger, capture_make, tmp_path, monkeypatch
):
    """Sandbox artifacts land in `./artifacts/` with a filename naturally
    distinct from any bare equivalent — `dotbot-sandbox-dotbot-v3.bin`
    vs bare `dotbot-dotbot-v3.hex` — because SES's `$(BuildTarget)` macro
    now includes the `sandbox-` prefix. No CLI-side mangling required;
    the user types `--app dotbot` in either namespace."""
    src_dir = (
        fake_repo
        / "apps-sandbox"
        / "dotbot"
        / "Output"
        / "sandbox-dotbot-v3"
        / "Release"
        / "Exe"
    )
    src_dir.mkdir(parents=True)
    (src_dir / "dotbot-sandbox-dotbot-v3.bin").write_bytes(b"\xde\xad\xbe\xef")
    monkeypatch.setattr(
        "dotbot.cli._sandbox_fw.list_projects", lambda target: ["dotbot"]
    )
    out = tmp_path / "user-artifacts"
    result = runner.invoke(
        sandbox_fw_cmd,
        ["artifacts", "--target", "dotbot-v3", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    collected = list(out.iterdir())
    assert len(collected) == 1
    assert collected[0].name == "dotbot-sandbox-dotbot-v3.bin"


# ── Output polish: preamble, timing, gated make-line echo ───────────────


def test_fw_build_quiet_does_not_echo_make_line(
    runner, fake_repo, fake_segger, capture_make
):
    """Default (no -v): make command line stays out of output."""
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    assert "$ make" not in result.output


def test_fw_build_verbose_echoes_make_line(
    runner, fake_repo, fake_segger, capture_make
):
    """-v echoes the full make command so it's copy-pasteable."""
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3", "-v"])
    assert result.exit_code == 0, result.output
    assert "$ make" in result.output
    assert "BUILD_TARGET=dotbot-v3" in result.output


def test_fw_build_prints_preamble_and_success(
    runner, fake_repo, fake_segger, capture_make
):
    """Happy path: preamble before make, success line with timing after."""
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    assert "Building" in result.output
    assert "dotbot-v3" in result.output
    assert "Release" in result.output
    assert "incremental" in result.output
    # Success line uses a check mark + timing.
    assert "✓" in result.output
    assert "Built dotbot-v3" in result.output


def test_fw_build_rebuild_says_rebuild_in_preamble(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbot-v3", "--rebuild"])
    assert result.exit_code == 0, result.output
    assert "rebuild" in result.output
    assert "incremental" not in result.output


def test_fw_clean_prints_cleaned_success_line(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["clean", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    assert "Cleaning dotbot-v3" in result.output
    assert "✓ Cleaned" in result.output


def test_fw_artifacts_prints_collected_success_line(
    runner, fake_repo, fake_segger, capture_make, tmp_path
):
    result = runner.invoke(
        fw_cmd,
        ["artifacts", "--target", "dotbot-v3", "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.output
    assert "Building + collecting artifacts" in result.output
    assert "✓ Collected" in result.output


def test_run_make_returns_elapsed_seconds(fake_repo, fake_segger, monkeypatch):
    """`run_make` must return a float so subcommands can format the timing."""
    monkeypatch.setattr(
        "dotbot.cli._fw_helpers.subprocess.call", lambda *a, **kw: 0
    )
    elapsed = _fw_helpers.run_make("dotbot-v3", "Release", "dotbot")
    assert isinstance(elapsed, float)
    assert elapsed >= 0


def test_sandbox_fw_build_prints_preamble(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(sandbox_fw_cmd, ["build", "--target", "dotbot-v3"])
    assert result.exit_code == 0, result.output
    assert "Building" in result.output
    assert "sandbox" in result.output.lower()
    assert "✓ Built" in result.output


# ── `dotbot make` escape hatch ──────────────────────────────────────────


from dotbot.cli.make import cmd as make_cmd  # noqa: E402


@pytest.fixture
def capture_make_passthrough(monkeypatch):
    """Capture `subprocess.call` in dotbot.cli.make (the escape hatch).

    Distinct from `capture_make` (which patches `_fw_helpers.subprocess`)
    because `make.py` imports `subprocess` directly.
    """
    calls = []

    def fake_call(cmd, cwd=None, env=None):
        calls.append({"cmd": cmd, "cwd": cwd, "env": env})
        return 0

    monkeypatch.setattr("dotbot.cli.make.subprocess.call", fake_call)
    return calls


def test_dotbot_make_help_lists_examples(runner):
    result = runner.invoke(make_cmd, ["--help"])
    assert result.exit_code == 0
    # Help should call out the workspace-resolved SEGGER_DIR — that's the
    # entire point vs. raw `cd repos/DotBot-firmware && make ...`.
    assert "SEGGER_DIR" in result.output


def test_dotbot_make_forwards_args_verbatim(
    runner, fake_repo, fake_segger, capture_make_passthrough
):
    """`dotbot make foo bar BAZ=qux` invokes `make foo bar BAZ=qux`."""
    result = runner.invoke(
        make_cmd, ["help", "BUILD_TARGET=dotbot-v3", "PACKAGES_DIR_OPT=-p /opt"]
    )
    assert result.exit_code == 0
    assert len(capture_make_passthrough) == 1
    cmd = capture_make_passthrough[0]["cmd"]
    assert cmd[0] == "make"
    assert "help" in cmd
    assert "BUILD_TARGET=dotbot-v3" in cmd
    assert "PACKAGES_DIR_OPT=-p /opt" in cmd


def test_dotbot_make_runs_in_firmware_repo(
    runner, fake_repo, fake_segger, capture_make_passthrough
):
    result = runner.invoke(make_cmd, ["list-targets"])
    assert result.exit_code == 0
    assert capture_make_passthrough[0]["cwd"] == fake_repo


def test_dotbot_make_injects_segger_dir(
    runner, fake_repo, fake_segger, capture_make_passthrough
):
    """SEGGER_DIR is set in the make env regardless of what the user passes."""
    result = runner.invoke(make_cmd, ["help"])
    assert result.exit_code == 0
    env = capture_make_passthrough[0]["env"]
    assert env["SEGGER_DIR"] == str(fake_segger)


def test_dotbot_make_propagates_make_exit_code(
    runner, fake_repo, fake_segger, monkeypatch
):
    monkeypatch.setattr("dotbot.cli.make.subprocess.call", lambda *a, **kw: 7)
    result = runner.invoke(make_cmd, ["bogus-target"])
    assert result.exit_code == 7


# ── Help-text footer pointing at the escape hatch ───────────────────────


def test_fw_help_points_at_dotbot_make(runner):
    result = runner.invoke(fw_cmd, ["--help"])
    assert result.exit_code == 0
    assert "dotbot make" in result.output


def test_sandbox_fw_help_points_at_dotbot_make(runner):
    result = runner.invoke(sandbox_fw_cmd, ["--help"])
    assert result.exit_code == 0
    assert "dotbot make" in result.output


# ── Helper-level tests ──────────────────────────────────────────────────


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point `~/.dotbot/` at a tmp dir so config tests don't see the
    real user's `~/.dotbot/config.toml`."""
    home = tmp_path / "home"
    (home / ".dotbot").mkdir(parents=True)
    monkeypatch.setattr(
        "dotbot.cli._fw_helpers._CONFIG_PATH",
        home / ".dotbot" / "config.toml",
    )
    return home


def _write_config(home, toml_body):
    (home / ".dotbot" / "config.toml").write_text(toml_body)


def test_resolve_segger_dir_uses_env_first(tmp_path, monkeypatch, isolated_home):
    """Env var beats config file beats glob."""
    _write_config(isolated_home, '[fw]\nsegger_dir = "/from/config"\n')
    monkeypatch.setenv("SEGGER_DIR", str(tmp_path))
    assert _fw_helpers.resolve_segger_dir() == tmp_path


def test_resolve_segger_dir_falls_back_to_config(monkeypatch, isolated_home):
    """When SEGGER_DIR is unset, `[fw].segger_dir` from the config wins."""
    _write_config(isolated_home, '[fw]\nsegger_dir = "/from/config"\n')
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    assert _fw_helpers.resolve_segger_dir() == Path("/from/config")


def test_resolve_segger_dir_uses_macos_glob_when_no_env_or_config(
    tmp_path, monkeypatch, isolated_home
):
    """macOS fallback: glob `/Applications/SEGGER/SEGGER Embedded Studio*`."""
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    fake_install = tmp_path / "SEGGER Embedded Studio 9.99"
    (fake_install / "bin").mkdir(parents=True)
    (fake_install / "bin" / "emBuild").touch()
    monkeypatch.setattr("dotbot.cli._fw_helpers.sys.platform", "darwin")
    monkeypatch.setattr(
        "dotbot.cli._fw_helpers._SEGGER_MACOS_GLOB",
        str(tmp_path / "SEGGER Embedded Studio*"),
    )
    assert _fw_helpers.resolve_segger_dir() == fake_install


def test_resolve_segger_dir_picks_latest_glob_match(
    tmp_path, monkeypatch, isolated_home
):
    """Multiple SES installs → lexicographically-latest wins (newer version)."""
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    for v in ("8.22a", "8.30a", "9.10"):
        d = tmp_path / f"SEGGER Embedded Studio {v}" / "bin"
        d.mkdir(parents=True)
        (d / "emBuild").touch()
    monkeypatch.setattr("dotbot.cli._fw_helpers.sys.platform", "darwin")
    monkeypatch.setattr(
        "dotbot.cli._fw_helpers._SEGGER_MACOS_GLOB",
        str(tmp_path / "SEGGER Embedded Studio*"),
    )
    picked = _fw_helpers.resolve_segger_dir()
    assert picked.name == "SEGGER Embedded Studio 9.10"


def test_resolve_segger_dir_errors_when_nothing_found(monkeypatch, isolated_home):
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    monkeypatch.setattr("dotbot.cli._fw_helpers.sys.platform", "linux")
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_segger_dir()
    # Error message must surface BOTH escape hatches so the user can fix
    # whichever they prefer.
    msg = str(excinfo.value)
    assert "SEGGER_DIR" in msg
    assert "~/.dotbot/config.toml" in msg


def test_resolve_firmware_repo_walks_up_from_cwd(tmp_path, monkeypatch, isolated_home):
    workspace = tmp_path / "ws"
    repo = workspace / "repos" / "DotBot-firmware"
    repo.mkdir(parents=True)
    (repo / "Makefile").touch()
    inner = workspace / "deep" / "subdir"
    inner.mkdir(parents=True)
    monkeypatch.chdir(inner)
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    assert _fw_helpers.resolve_firmware_repo() == repo


def test_resolve_firmware_repo_uses_config_file(
    tmp_path, monkeypatch, isolated_home
):
    """`[fw].firmware_repo` in the config beats workspace walk-up."""
    real_repo = tmp_path / "outside-workspace" / "DotBot-firmware"
    real_repo.mkdir(parents=True)
    (real_repo / "Makefile").touch()
    _write_config(isolated_home, f'[fw]\nfirmware_repo = "{real_repo}"\n')
    monkeypatch.chdir(tmp_path)  # not inside any workspace
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    assert _fw_helpers.resolve_firmware_repo() == real_repo


def test_resolve_firmware_repo_config_pointing_at_no_makefile_errors(
    tmp_path, monkeypatch, isolated_home
):
    """If the config points at a bad path, fail loudly — don't silently fall
    through to the workspace walk-up."""
    bad = tmp_path / "no-makefile-here"
    bad.mkdir()
    _write_config(isolated_home, f'[fw]\nfirmware_repo = "{bad}"\n')
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_firmware_repo()
    assert "firmware_repo" in str(excinfo.value)


def test_resolve_firmware_repo_errors_outside_workspace(
    tmp_path, monkeypatch, isolated_home
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOTBOT_FIRMWARE_REPO", raising=False)
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_firmware_repo()
    msg = str(excinfo.value)
    # Both escape hatches surfaced.
    assert "DOTBOT_FIRMWARE_REPO" in msg
    assert "~/.dotbot/config.toml" in msg


def test_malformed_config_raises_with_path(monkeypatch, isolated_home):
    _write_config(isolated_home, "this is not [valid toml\n")
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.load_config()
    assert str(_fw_helpers._CONFIG_PATH) in str(excinfo.value)


def test_missing_config_returns_empty_dict(isolated_home):
    """No `~/.dotbot/config.toml` is the common case — must not error."""
    assert _fw_helpers.load_config() == {}


# ── Parity guard against silent drift ───────────────────────────────────


def _real_firmware_repo_or_skip():
    """Find the real DotBot-firmware repo for the parity test, or skip."""
    import os
    from pathlib import Path

    env = os.environ.get("DOTBOT_FIRMWARE_REPO")
    if env and (Path(env) / "Makefile").is_file():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "repos" / "DotBot-firmware"
        if (candidate / "Makefile").is_file():
            return candidate
    pytest.skip(
        "Could not locate the real DotBot-firmware repo; set "
        "DOTBOT_FIRMWARE_REPO or run from inside the workspace."
    )


def test_targets_match_makefile_list_targets():
    """`set(BARE_TARGETS) | set('sandbox-'+SANDBOX_BOARDS)` must equal what
    the Makefile reports via `make list-targets`.

    Catches the silent drift case where someone adds e.g. dotbot-v4 to
    the Makefile and forgets to update the CLI's hardcoded enum.

    Self-skips if the real DotBot-firmware repo or the `list-targets`
    Make rule isn't available (older checkout pre-dating that commit).
    """
    repo = _real_firmware_repo_or_skip()
    try:
        result = subprocess.run(
            ["make", "-s", "list-targets"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("`make list-targets` not runnable in this environment.")
    if result.returncode != 0:
        pytest.skip(
            "`make list-targets` rule not present in this DotBot-firmware "
            "checkout. Bump the submodule / pull a newer Makefile to enable "
            "this parity guard."
        )
    makefile_targets = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    cli_targets = set(_fw_helpers.BARE_TARGETS) | {
        f"sandbox-{b}" for b in _fw_helpers.SANDBOX_BOARDS
    }
    assert makefile_targets == cli_targets, (
        f"CLI hardcoded targets drifted from Makefile.\n"
        f"In CLI but not Makefile: {cli_targets - makefile_targets}\n"
        f"In Makefile but not CLI: {makefile_targets - cli_targets}"
    )
