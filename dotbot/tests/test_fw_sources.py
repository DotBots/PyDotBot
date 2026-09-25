# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for building a release's firmware set locally (`fw artifacts`).

No SES and no real checkout: `make` and emBuild are stubbed, and the build
trees are tmp directories with the files SES would write.
"""

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from dotbot.cli import _fw_helpers
from dotbot.cli import _fw_sources as fs
from dotbot.cli.fw import cmd as fw_cmd
from dotbot.config import DotbotConfig

RELEASE_NAMES = {
    "bootloader-dotbot-v3.hex",
    "netcore-nrf5340-net.hex",
    "03app_gateway_app-nrf5340-app.hex",
    "03app_gateway_net-nrf5340-net.hex",
}

# What the fake Makefile reports, per BUILD_TARGET.
PROJECTS = {
    "dotbot-v3": ["dotbot", "lh2_calibration", "log_dump"],
    "sandbox-dotbot-v3": ["calibrate", "dotbot", "rgbled"],
}
RELEASE_PROJECTS = {
    "dotbot-v3": ["dotbot", "lh2_calibration"],
    "sandbox-dotbot-v3": ["calibrate", "dotbot", "rgbled"],
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No real config, env or cache: a tmp cwd, user file and artifacts dir."""
    for var in ("DOTBOT_FIRMWARE_REPO", "DOTBOT_SWARMIT_REPO", "DOTBOT_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("dotbot.config.USER_CONFIG_PATH", tmp_path / "no-user.toml")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path / "cache"))
    segger = tmp_path / "segger"
    (segger / "bin").mkdir(parents=True)
    (segger / "bin" / "emBuild").write_text("#!/bin/sh\n")
    monkeypatch.setenv("SEGGER_DIR", str(segger))
    return tmp_path


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "Makefile").write_text("# fake\n")
    return path


@pytest.fixture
def firmware_repo(isolated, monkeypatch):
    repo = _repo(isolated / "DotBot-firmware")
    monkeypatch.setenv("DOTBOT_FIRMWARE_REPO", str(repo))
    return repo


@pytest.fixture
def swarmit_repo(isolated, monkeypatch):
    repo = _repo(isolated / "swarmit")
    _repo(repo / "mari" / "firmware")
    monkeypatch.setenv("DOTBOT_SWARMIT_REPO", str(repo))
    return repo


@pytest.fixture
def fake_make(monkeypatch):
    """Stub the Makefile: project lists, release lists, and builds.

    A build writes each requested app's SES output, so collection can be
    checked end to end.
    """
    calls = []

    def target_of(cmd):
        return next(a.split("=", 1)[1] for a in cmd if a.startswith("BUILD_TARGET="))

    def fake_run(cmd, cwd=None, env=None, **kw):
        target = target_of(cmd)
        names = (
            RELEASE_PROJECTS if "print-release-projects" in cmd else PROJECTS
        ).get(target, [])

        class _R:
            returncode = 0
            stdout = "\n".join(names) + "\n"
            stderr = ""

        return _R()

    def fake_call(cmd, cwd=None, env=None, **kw):
        calls.append(cmd)
        target = target_of(cmd)
        config = next(a.split("=", 1)[1] for a in cmd if a.startswith("BUILD_CONFIG="))
        apps = [a for a in cmd[1:] if "=" not in a]
        for app in apps:
            out = _fw_helpers.artifact_path(target, app, config)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(app.encode())
        return 0

    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.run", fake_run)
    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.call", fake_call)
    return calls


@pytest.fixture
def fake_embuild(monkeypatch):
    """Stub emBuild: record the command and write the step's output file."""
    import subprocess

    calls = []
    # `subprocess` is one module object, so a `make` stub installed by
    # `fake_make` is the same attribute; hand `make` commands back to it.
    make_call = subprocess.call

    def fake_call(cmd, cwd=None, **kw):
        if cmd[0] == "make":
            return make_call(cmd, cwd=cwd, **kw)
        calls.append((Path(cwd), cmd))
        config = cmd[cmd.index("-config") + 1]
        project = cmd[cmd.index("-project") + 1]
        repo = Path(cwd) if project in ("bootloader", "netcore") else Path(cwd).parents[1]
        for step in fs.swarmit_steps(repo, "dotbot-v3", config):
            if step.project == project and step.cwd == Path(cwd):
                out = step.cwd / step.output
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(project.encode())
        return 0

    monkeypatch.setattr("dotbot.cli._fw_sources.subprocess.call", fake_call)
    return calls


@pytest.fixture
def emprojects(swarmit_repo):
    for name in (
        "swarmit-bootloader-dotbot-v3.emProject",
        "swarmit-netcore.emProject",
    ):
        (swarmit_repo / name).write_text("")
    mari = swarmit_repo / "mari" / "firmware"
    for name in (
        "mari-gateway-app-nrf5340dk.emProject",
        "mari-gateway-net-nrf5340dk.emProject",
    ):
        (mari / name).write_text("")
    return swarmit_repo


# --- default app set ---------------------------------------------------------


def test_default_set_is_the_release_set_without_legacy_apps(firmware_repo, fake_make):
    assert fs.default_apps("dotbot-v3") == ["dotbot"]
    assert "calibrate" in fs.default_apps("sandbox-dotbot-v3")


def test_default_plan_builds_both_flavors_with_calibrate_not_lh2(
    firmware_repo, fake_make
):
    plan = dict(fs.dotbot_firmware_plan("dotbot-v3", fs.FLAVORS))
    assert plan["dotbot-v3"] == ["dotbot"]
    assert plan["sandbox-dotbot-v3"] == ["calibrate", "dotbot", "rgbled"]


def test_legacy_app_still_builds_when_named(firmware_repo, fake_make):
    plan = fs.dotbot_firmware_plan("dotbot-v3", fs.FLAVORS, "lh2_calibration")
    assert plan == [("dotbot-v3", ["lh2_calibration"])]


def test_named_app_missing_everywhere_errors(firmware_repo, fake_make):
    with pytest.raises(click.ClickException):
        fs.dotbot_firmware_plan("dotbot-v3", fs.FLAVORS, "nope")


# --- collection ---------------------------------------------------------------


def test_collect_copies_under_the_ses_name(tmp_path):
    src = tmp_path / "Output" / "Release" / "Exe" / "bootloader-dotbot-v3.hex"
    src.parent.mkdir(parents=True)
    src.write_text("new")
    out = tmp_path / "swarmit-local"
    assert fs.collect([src], out) == [out / "bootloader-dotbot-v3.hex"]
    assert (out / "bootloader-dotbot-v3.hex").read_text() == "new"


def test_collect_replaces_a_symlink_without_writing_through_it(tmp_path):
    old_target = tmp_path / "tree" / "bootloader-dotbot-v3.hex"
    old_target.parent.mkdir()
    old_target.write_text("debug build")
    out = tmp_path / "swarmit-local"
    out.mkdir()
    (out / "bootloader-dotbot-v3.hex").symlink_to(old_target)
    src = tmp_path / "release" / "bootloader-dotbot-v3.hex"
    src.parent.mkdir()
    src.write_text("release build")
    fs.collect([src], out)
    dst = out / "bootloader-dotbot-v3.hex"
    assert not dst.is_symlink()
    assert dst.read_text() == "release build"
    assert old_target.read_text() == "debug build"


def test_collect_errors_on_a_missing_output(tmp_path):
    with pytest.raises(click.ClickException):
        fs.collect([tmp_path / "missing.hex"], tmp_path / "out")


def test_swarmit_outputs_carry_the_release_names_for_the_build_config(tmp_path):
    steps = fs.swarmit_steps(tmp_path, "dotbot-v3", "Debug")
    assert {s.output.name for s in steps} == RELEASE_NAMES
    assert all("Debug" in s.output.parts for s in steps)


def test_swarmit_rejects_a_board_without_bootloader(tmp_path):
    with pytest.raises(click.ClickException):
        fs.swarmit_steps(tmp_path, "nrf5340dk-app", "Release")


# --- `fw artifacts` ------------------------------------------------------------


def test_artifacts_swarmit_builds_and_collects_release_names(
    isolated, emprojects, fake_embuild
):
    result = CliRunner().invoke(fw_cmd, ["artifacts", "--source", "swarmit"])
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "swarmit-local"
    assert {p.name for p in local.iterdir()} == RELEASE_NAMES
    # Release config by default, incremental, gateway from the mari submodule.
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Release" for cmd in cmds)
    assert not any("-rebuild" in cmd for cmd in cmds)
    gateway_cwds = {cwd for cwd, cmd in fake_embuild if "03app_gateway_app" in cmd}
    assert gateway_cwds == {emprojects / "mari" / "firmware"}


def test_artifacts_swarmit_honors_build_config_and_rebuild(
    isolated, emprojects, fake_embuild
):
    result = CliRunner().invoke(
        fw_cmd,
        ["artifacts", "-S", "swarmit", "--build-config", "Debug", "--rebuild"],
    )
    assert result.exit_code == 0, result.output
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Debug" for cmd in cmds)
    assert all("-rebuild" in cmd for cmd in cmds)


def test_artifacts_swarmit_missing_submodule_hints_init(isolated, swarmit_repo):
    (swarmit_repo / "swarmit-bootloader-dotbot-v3.emProject").write_text("")
    (swarmit_repo / "swarmit-netcore.emProject").write_text("")
    result = CliRunner().invoke(fw_cmd, ["artifacts", "-S", "swarmit"])
    assert result.exit_code != 0
    assert "submodule" in result.output


def test_artifacts_dotbot_firmware_default_set(isolated, firmware_repo, fake_make):
    result = CliRunner().invoke(fw_cmd, ["artifacts", "-S", "dotbot-firmware"])
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "dotbot-firmware-local"
    assert {p.name for p in local.iterdir()} == {
        "dotbot-dotbot-v3.hex",
        "calibrate-sandbox-dotbot-v3.bin",
        "dotbot-sandbox-dotbot-v3.bin",
        "rgbled-sandbox-dotbot-v3.bin",
    }
    assert all("BUILD_MODE=" in cmd for cmd in fake_make)


def test_artifacts_sandbox_app(isolated, firmware_repo, fake_make):
    result = CliRunner().invoke(
        fw_cmd, ["artifacts", "-S", "dotbot-firmware", "--sandbox", "-a", "dotbot"]
    )
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "dotbot-firmware-local"
    assert [p.name for p in local.iterdir()] == ["dotbot-sandbox-dotbot-v3.bin"]


def test_artifacts_app_alone_selects_dotbot_firmware(
    isolated, firmware_repo, fake_make
):
    result = CliRunner().invoke(fw_cmd, ["artifacts", "--bare", "-a", "dotbot"])
    assert result.exit_code == 0, result.output
    assert not (isolated / "cache" / "swarmit-local").exists()


def test_artifacts_default_builds_every_source(
    isolated, firmware_repo, emprojects, fake_make, fake_embuild
):
    result = CliRunner().invoke(fw_cmd, ["artifacts"])
    assert result.exit_code == 0, result.output
    assert (isolated / "cache" / "swarmit-local").is_dir()
    assert (isolated / "cache" / "dotbot-firmware-local").is_dir()


def test_artifacts_print_path_covers_every_source_without_building(
    isolated, firmware_repo, emprojects, fake_make, fake_embuild
):
    result = CliRunner().invoke(fw_cmd, ["artifacts", "--print-path"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    cache = isolated / "cache"
    assert str(cache / "swarmit-local" / "bootloader-dotbot-v3.hex") in lines
    assert str(cache / "dotbot-firmware-local" / "calibrate-sandbox-dotbot-v3.bin") in lines
    assert fake_make == [] and fake_embuild == []


def test_artifacts_print_path_reflects_config_board(isolated, firmware_repo, fake_make):
    cfg = DotbotConfig.model_validate({"fw": {"board": "nrf5340dk-app"}})
    PROJECTS["nrf5340dk-app"] = ["dotbot_gateway"]
    try:
        result = CliRunner().invoke(
            fw_cmd,
            ["artifacts", "--print-path", "-a", "dotbot_gateway"],
            obj={"config": cfg, "deployment": None},
        )
    finally:
        del PROJECTS["nrf5340dk-app"]
    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith("dotbot_gateway-nrf5340dk-app.hex")


def test_artifacts_out_collects_everything_there(isolated, firmware_repo, fake_make):
    out = isolated / "elsewhere"
    result = CliRunner().invoke(
        fw_cmd, ["artifacts", "-S", "dotbot-firmware", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "dotbot-dotbot-v3.hex" in {p.name for p in out.iterdir()}
    assert "✓ Collected 4 artifact(s)" in result.output


def test_artifacts_sandbox_and_bare_are_exclusive(isolated, firmware_repo):
    result = CliRunner().invoke(fw_cmd, ["artifacts", "--sandbox", "--bare"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output
