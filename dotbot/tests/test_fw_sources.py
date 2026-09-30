# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for building firmware sets from local source folders (`fw build`).

No SES and no real source folder: `make` and emBuild are stubbed, and the build
trees are tmp directories with the files SES would write.
"""

import os
import shutil
import signal
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from dotbot.cli import _fw_helpers
from dotbot.cli import _fw_sources as fs
from dotbot.cli.fw import cmd as fw_cmd
from dotbot.config import DotbotConfig

SWARMIT_NAMES = {"bootloader-dotbot-v3.hex", "netcore-nrf5340-net.hex"}
MARI_NAMES = {
    "03app_gateway_app-nrf5340-app.hex",
    "03app_gateway_net-nrf5340-net.hex",
}
# The .hex assets of the swarmit 0.10.0 release a dotbot-v3 + gateway bench
# uses: the bootloader, the net core, and the Mari gateway it carries.
SWARMIT_RELEASE_HEX = SWARMIT_NAMES | MARI_NAMES

MAIN_C = """extern schedule_t schedule_tiny, schedule_medium, schedule_big, schedule_huge;
schedule_t       *schedule_app = &schedule_huge;
"""

# What the fake Makefile reports, per BUILD_TARGET. The Makefile leaves the
# legacy lh2_calibration out of its project list; an older checkout still
# releases it.
PROJECTS = {
    "dotbot-v3": ["dotbot", "log_dump"],
    "sandbox-dotbot-v3": ["calibrate", "dotbot", "rgbled"],
}
RELEASE_PROJECTS = {
    "dotbot-v3": ["dotbot", "lh2_calibration"],
    "sandbox-dotbot-v3": ["calibrate", "dotbot", "rgbled"],
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No real config, env or cache: a tmp cwd, user file and artifacts dir."""
    for var in (
        "DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE",
        "DOTBOT_FW_SOURCES_SWARMIT",
        "DOTBOT_FW_SOURCES_MARI",
        "DOTBOT_CONFIG",
    ):
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
    monkeypatch.setenv("DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE", str(repo))
    return repo


@pytest.fixture
def swarmit_repo(isolated, monkeypatch):
    repo = _repo(isolated / "swarmit")
    monkeypatch.setenv("DOTBOT_FW_SOURCES_SWARMIT", str(repo))
    return repo


@pytest.fixture
def mari_repo(isolated, monkeypatch):
    repo = isolated / "mari"
    fw = _repo(repo / "firmware")
    for name in (
        "mari-gateway-app-nrf5340dk.emProject",
        "mari-gateway-net-nrf5340dk.emProject",
    ):
        (fw / name).write_text("")
    main_c = fw / "app" / "03app_gateway_net" / "main.c"
    main_c.parent.mkdir(parents=True)
    main_c.write_text(MAIN_C)
    monkeypatch.setenv("DOTBOT_FW_SOURCES_MARI", str(repo))
    return repo


@pytest.fixture
def fake_make(monkeypatch):
    """Stub the Makefile: project lists, release lists, and builds.

    A build writes each requested app's SES output, so collection can be
    checked end to end.
    """
    import subprocess

    calls = []
    real_run = subprocess.run

    def target_of(cmd):
        return next(a.split("=", 1)[1] for a in cmd if a.startswith("BUILD_TARGET="))

    def fake_run(cmd, cwd=None, env=None, **kw):
        if cmd[0] != "make":
            return real_run(cmd, cwd=cwd, env=env, **kw)
        target = target_of(cmd)
        names = (RELEASE_PROJECTS if "print-release-projects" in cmd else PROJECTS).get(
            target, []
        )

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
        if project in ("bootloader", "netcore"):
            steps = fs.swarmit_steps(Path(cwd), "dotbot-v3", config)
        else:
            steps = fs.mari_steps(Path(cwd).parent, config)
        content = project
        main_c = Path(cwd) / "app" / "03app_gateway_net" / "main.c"
        if project == "03app_gateway_net":
            content += " " + main_c.read_text().splitlines()[1].split("&")[1]
        for step in steps:
            if step.project == project and step.cwd == Path(cwd):
                out = step.cwd / step.output
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(content.encode())
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
    return swarmit_repo


def _git_init(repo: Path) -> str:
    import subprocess

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
                "HOME": str(repo),
                "PATH": "/usr/bin:/bin",
            },
        ).stdout

    git("init", "-q")
    (repo / ".gitignore").write_text("Output/\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return git("rev-parse", "HEAD").strip()


def build(*args, **kw):
    return CliRunner().invoke(fw_cmd, ["build", *args], **kw)


# --- default app set ---------------------------------------------------------


def test_default_set_is_the_release_set_without_legacy_apps(firmware_repo, fake_make):
    assert fs.default_apps("dotbot-v3") == ["dotbot"]
    assert "calibrate" in fs.default_apps("sandbox-dotbot-v3")


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_release_projects_are_read_from_the_makefile(tmp_path):
    (tmp_path / "Makefile").write_text(
        "ifeq (dotbot-v3,$(BUILD_TARGET))\n"
        "  ARTIFACT_PROJECTS := dotbot\n"
        "else\n"
        "  ARTIFACT_PROJECTS := dotbot_gateway dotbot_gateway_lr\n"
        "endif\n"
        "all: ; @echo built\n"
    )
    assert _fw_helpers.list_release_projects("dotbot-v3", tmp_path) == ["dotbot"]
    assert _fw_helpers.list_release_projects("nrf52840dk", tmp_path) == [
        "dotbot_gateway",
        "dotbot_gateway_lr",
    ]


def test_legacy_app_builds_when_named_and_stays_out_of_help(
    isolated, firmware_repo, fake_make
):
    result = build("lh2_calibration", "--bare")
    assert result.exit_code == 0, result.output
    assert "PROJECTS=lh2_calibration" in fake_make[0]
    local = isolated / "cache" / "dotbot-firmware-local"
    assert (local / "lh2_calibration-dotbot-v3.hex").is_file()
    assert "lh2_calibration" not in build("--help").output


def test_named_apps_are_checked_against_the_target(firmware_repo, fake_make):
    assert fs.dotbot_firmware_apps("dotbot-v3", ["lh2_calibration"]) == [
        "lh2_calibration"
    ]
    with pytest.raises(click.ClickException, match="nope"):
        fs.dotbot_firmware_apps("sandbox-dotbot-v3", ["nope"])


def test_an_app_named_like_a_role_is_refused(firmware_repo, fake_make):
    PROJECTS["dotbot-v3"].append("mari-gateway")
    try:
        with pytest.raises(click.ClickException, match="also a role name"):
            fs.dotbot_firmware_apps("dotbot-v3", ["dotbot"])
    finally:
        PROJECTS["dotbot-v3"].remove("mari-gateway")


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
    assert {s.output.name for s in steps} == SWARMIT_NAMES
    assert all("Debug" in s.output.parts for s in steps)


def test_build_and_flash_use_the_release_file_names(tmp_path):
    from dotbot.firmware.flash import DEVICE_ASSETS
    from dotbot.firmware.schedules import MARI_SCHEDULES, net_image_name

    swarmit = fs.swarmit_steps(tmp_path, "dotbot-v3", "Debug")
    mari = fs.mari_steps(tmp_path, "Debug")
    built = {fs.collected_name(step) for step in swarmit + mari}
    assert built == SWARMIT_RELEASE_HEX
    roles = DEVICE_ASSETS["dotbot-v3"], DEVICE_ASSETS["gateway"]
    assert {role[core] for role in roles for core in ("app", "net")} == built
    scheduled = fs.mari_steps(tmp_path, "Debug", schedules=list(MARI_SCHEDULES))
    assert [fs.collected_name(step) for step in scheduled[1:]] == [
        net_image_name(name) for name in MARI_SCHEDULES
    ]


def test_swarmit_rejects_a_board_without_bootloader(tmp_path):
    with pytest.raises(click.ClickException):
        fs.swarmit_steps(tmp_path, "nrf5340dk-app", "Release")


def test_swarmit_parts_select_steps_and_swarmit_has_no_gateway(tmp_path):
    steps = fs.swarmit_steps(tmp_path, "nrf5340dk-app", "Debug", ["netcore"])
    assert [s.output.name for s in steps] == ["netcore-nrf5340-net.hex"]
    with pytest.raises(click.ClickException, match="swarmit-sandbox has no part"):
        fs.swarmit_steps(tmp_path, "dotbot-v3", "Debug", ["gateway"])


def test_mari_gateway_is_both_images_from_the_mari_firmware_dir(tmp_path):
    steps = fs.mari_steps(tmp_path, "Debug")
    assert {s.output.name for s in steps} == MARI_NAMES
    assert {s.cwd for s in steps} == {tmp_path / "firmware"}


def test_schedule_all_expands_in_ladder_order():
    from dotbot.firmware.schedules import MARI_SCHEDULES

    assert fs.resolve_schedules(["all"]) == list(MARI_SCHEDULES)
    assert fs.resolve_schedules([]) == []
    last, first = list(MARI_SCHEDULES)[-1], list(MARI_SCHEDULES)[0]
    assert fs.resolve_schedules([last, first]) == [first, last]


# --- `fw build` ---------------------------------------------------------------


def test_build_swarmit_defaults_to_debug_into_the_local_set(
    isolated, emprojects, fake_embuild
):
    result = build("swarmit-sandbox")
    assert result.exit_code == 0, result.output
    assert "Building swarmit-sandbox for dotbot-v3" in result.output
    local = isolated / "cache" / "swarmit-local"
    assert {p.name for p in local.iterdir()} == SWARMIT_NAMES | {"manifest.json"}
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Debug" for cmd in cmds)
    assert not any("-rebuild" in cmd for cmd in cmds)


def test_build_mari_gateway_defaults_to_debug_into_the_mari_set(
    isolated, mari_repo, fake_embuild
):
    import json

    result = build("mari-gateway")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    assert {p.name for p in local.iterdir()} == MARI_NAMES | {"manifest.json"}
    assert {cwd for cwd, _ in fake_embuild} == {mari_repo / "firmware"}
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Debug" for cmd in cmds)
    manifest = json.loads((local / "manifest.json").read_text())
    assert manifest["board"] == "nrf5340dk"


def test_build_mari_schedule_builds_the_image_flash_reads(
    isolated, mari_repo, fake_embuild
):
    main_c = mari_repo / "firmware" / "app" / "03app_gateway_net" / "main.c"
    result = build("mari-gateway", "--schedule", "tiny")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    assert {p.name for p in local.iterdir()} == {
        "03app_gateway_app-nrf5340-app.hex",
        "03app_gateway_net-tiny.hex",
        "manifest.json",
    }
    assert (local / "03app_gateway_net-tiny.hex").read_text() == (
        "03app_gateway_net schedule_tiny;"
    )
    staged = mari_repo / "firmware" / "Output" / "schedules"
    assert (staged / "03app_gateway_net-tiny.hex").is_file()
    assert main_c.read_text() == MAIN_C


def test_build_mari_schedule_all_builds_every_schedule(
    isolated, mari_repo, fake_embuild
):
    from dotbot.firmware.schedules import MARI_SCHEDULES, net_image_name

    result = build("mari-gateway", "--schedule", "all")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    for name in MARI_SCHEDULES:
        image = local / net_image_name(name)
        assert image.read_text() == f"03app_gateway_net schedule_{name};"
    assert not (local / "03app_gateway_net-nrf5340-net.hex").exists()


def test_build_mari_schedule_restores_main_c_when_a_build_fails(
    isolated, mari_repo, monkeypatch
):
    main_c = mari_repo / "firmware" / "app" / "03app_gateway_net" / "main.c"
    monkeypatch.setattr("dotbot.cli._fw_sources.subprocess.call", lambda *a, **k: 2)
    result = build("mari-gateway", "--schedule", "big")
    assert result.exit_code != 0
    assert main_c.read_text() == MAIN_C


def test_mari_net_image_is_always_rebuilt(isolated, mari_repo, fake_embuild):
    result = build("mari-gateway", "--schedule", "tiny", "--schedule", "big")
    assert result.exit_code == 0, result.output
    result = build("mari-gateway")
    assert result.exit_code == 0, result.output
    for _, cmd in fake_embuild:
        net = cmd[cmd.index("-project") + 1] == "03app_gateway_net"
        assert ("-rebuild" in cmd) == net


# CRLF line ends and a non-UTF-8 byte: the restore must not normalise either.
_MAIN_C_BYTES = MAIN_C.replace("\n", "\r\n").encode() + b"// \xe9\r\n"


def test_build_mari_schedule_restores_main_c_on_ctrl_c(
    isolated, mari_repo, monkeypatch
):
    main_c = mari_repo / "firmware" / "app" / "03app_gateway_net" / "main.c"
    main_c.write_bytes(_MAIN_C_BYTES)
    seen = []

    def interrupted(cmd, cwd=None, **kw):
        if "03app_gateway_net" not in cmd:
            return 0
        seen.append(main_c.read_bytes())
        raise KeyboardInterrupt

    monkeypatch.setattr("dotbot.cli._fw_sources.subprocess.call", interrupted)
    with pytest.raises(KeyboardInterrupt):
        fs.build_mari("Debug", schedules=["tiny"])
    assert b"&schedule_tiny;" in seen[0]
    assert main_c.read_bytes() == _MAIN_C_BYTES


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX signals")
@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP"])
def test_build_mari_schedule_restores_main_c_on_termination(
    isolated, mari_repo, monkeypatch, signame
):
    main_c = mari_repo / "firmware" / "app" / "03app_gateway_net" / "main.c"
    main_c.write_bytes(_MAIN_C_BYTES)
    before = signal.getsignal(getattr(signal, signame))

    def killed(cmd, cwd=None, **kw):
        if "03app_gateway_net" in cmd:
            assert b"&schedule_tiny;" in main_c.read_bytes()
            os.kill(os.getpid(), getattr(signal, signame))
        return 0

    monkeypatch.setattr("dotbot.cli._fw_sources.subprocess.call", killed)
    with pytest.raises(KeyboardInterrupt):
        fs.build_mari("Debug", schedules=["tiny", "big"])
    assert main_c.read_bytes() == _MAIN_C_BYTES
    assert signal.getsignal(getattr(signal, signame)) == before


def test_build_schedule_without_mari_gateway_errors(isolated, emprojects):
    result = build("swarmit-sandbox", "--schedule", "tiny")
    assert result.exit_code != 0
    assert "--schedule only applies to mari-gateway" in result.output
    assert "dotbot fw build mari-gateway --schedule tiny" in result.output


def test_build_part_without_swarmit_sandbox_errors(isolated):
    result = build("mari-gateway", "-a", "netcore")
    assert result.exit_code != 0
    assert "dotbot fw build swarmit-sandbox -a netcore" in result.output
    result = build("-a", "netcore")
    assert "dotbot fw build swarmit-sandbox -a netcore" in result.output


def test_build_bare_on_a_role_only_errors(isolated):
    result = build("swarmit-sandbox", "--bare")
    assert result.exit_code != 0
    assert "--bare/--sandboxed only apply to apps" in result.output


def test_build_bare_from_config_does_not_refuse_a_role(
    isolated, emprojects, fake_embuild
):
    cfg = DotbotConfig.model_validate({"fw": {"bare": True}})
    result = build("swarmit-sandbox", obj={"config": cfg, "deployment": None})
    assert result.exit_code == 0, result.output


def test_build_schedule_rejects_an_unknown_name(isolated):
    result = build("mari-gateway", "--schedule", "gigantic")
    assert result.exit_code != 0
    assert "gigantic" in result.output


def test_build_swarmit_honors_build_config_and_rebuild(
    isolated, emprojects, fake_embuild
):
    result = build("swarmit-sandbox", "--build-config", "Release", "--rebuild")
    assert result.exit_code == 0, result.output
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Release" for cmd in cmds)
    assert all("-rebuild" in cmd for cmd in cmds)


def test_build_mari_gateway_without_a_source_says_where_to_put_it(isolated):
    result = build("mari-gateway")
    assert result.exit_code != 0
    assert "DOTBOT_FW_SOURCES_MARI" in result.output
    assert "mari under [fw.sources]" in result.output


def test_build_apps_default_to_sandboxed_release_builds(
    isolated, firmware_repo, fake_make
):
    result = build("calibrate", "dotbot", "rgbled")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "dotbot-firmware-local"
    assert {p.name for p in local.iterdir()} == {
        "calibrate-sandbox-dotbot-v3.bin",
        "dotbot-sandbox-dotbot-v3.bin",
        "rgbled-sandbox-dotbot-v3.bin",
        "manifest.json",
    }
    assert all("BUILD_CONFIG=Release" in cmd for cmd in fake_make)
    assert all("BUILD_MODE=" in cmd for cmd in fake_make)


def test_build_bare_app(isolated, firmware_repo, fake_make):
    result = build("dotbot", "--bare")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "dotbot-firmware-local"
    assert {p.name for p in local.iterdir()} == {
        "dotbot-dotbot-v3.hex",
        "manifest.json",
    }


def test_build_an_app_by_name(isolated, firmware_repo, fake_make):
    result = build("calibrate")
    assert result.exit_code == 0, result.output
    assert "Building apps for dotbot-v3" in result.output
    assert not (isolated / "cache" / "swarmit-local").exists()
    local = isolated / "cache" / "dotbot-firmware-local"
    assert (local / "calibrate-sandbox-dotbot-v3.bin").is_file()


def test_build_swarmit_sandbox_part(
    isolated, firmware_repo, emprojects, fake_make, fake_embuild
):
    result = build("swarmit-sandbox", "-a", "bootloader")
    assert result.exit_code == 0, result.output
    assert not (isolated / "cache" / "dotbot-firmware-local").exists()
    local = isolated / "cache" / "swarmit-local"
    assert {p.name for p in local.iterdir()} == {
        "bootloader-dotbot-v3.hex",
        "manifest.json",
    }


def test_build_unknown_app_errors(isolated, firmware_repo, fake_make):
    result = build("nope")
    assert result.exit_code != 0
    assert "No 'nope' app for sandbox-dotbot-v3" in result.output
    assert "Roles: swarmit-sandbox, mari-gateway." in result.output
    assert "Apps for sandbox-dotbot-v3: calibrate, dotbot, rgbled." in result.output


def test_build_roles_and_apps_together(
    isolated, firmware_repo, emprojects, mari_repo, fake_make, fake_embuild
):
    result = build("calibrate", "swarmit-sandbox", "mari-gateway")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "dotbot-firmware-local"
    assert {p.name for p in local.iterdir()} == {
        "calibrate-sandbox-dotbot-v3.bin",
        "manifest.json",
    }
    assert (isolated / "cache" / "swarmit-local").is_dir()
    assert (isolated / "cache" / "mari-local").is_dir()


def test_build_default_builds_every_source(
    isolated, firmware_repo, emprojects, mari_repo, fake_make, fake_embuild
):
    result = build()
    assert result.exit_code == 0, result.output
    assert (isolated / "cache" / "swarmit-local").is_dir()
    assert (isolated / "cache" / "mari-local").is_dir()
    assert (isolated / "cache" / "dotbot-firmware-local").is_dir()


def test_build_default_skips_swarmit_on_a_board_without_bootloader(
    isolated, firmware_repo, emprojects, mari_repo, fake_make
):
    PROJECTS["nrf52840dk"] = ["dotbot"]
    try:
        result = build("-t", "nrf52840dk", "--print-path")
    finally:
        del PROJECTS["nrf52840dk"]
    assert result.exit_code == 0, result.output
    assert "[skip] swarmit-sandbox" in result.output
    assert "dotbot-nrf52840dk.hex" in result.output


def test_build_print_path_covers_every_source_without_building(
    isolated, firmware_repo, emprojects, mari_repo, fake_make, fake_embuild
):
    result = build("--print-path", "--schedule", "huge")
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    cache = isolated / "cache"
    assert str(cache / "swarmit-local" / "bootloader-dotbot-v3.hex") in lines
    assert str(cache / "mari-local" / "03app_gateway_net-huge.hex") in lines
    assert (
        str(cache / "dotbot-firmware-local" / "calibrate-sandbox-dotbot-v3.bin")
        in lines
    )
    assert fake_make == [] and fake_embuild == []


def test_build_print_path_reflects_config_board(isolated, firmware_repo, fake_make):
    cfg = DotbotConfig.model_validate({"fw": {"board": "nrf5340dk-app"}})
    PROJECTS["nrf5340dk-app"] = ["dotbot_gateway"]
    try:
        result = build(
            "--print-path",
            "dotbot_gateway",
            obj={"config": cfg, "deployment": None},
        )
    finally:
        del PROJECTS["nrf5340dk-app"]
    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith("dotbot_gateway-nrf5340dk-app.hex")


def test_build_config_key_overrides_both_source_defaults(
    isolated, firmware_repo, emprojects, fake_make, fake_embuild
):
    cfg = DotbotConfig.model_validate({"fw": {"build_config": "Release"}})
    result = build("swarmit-sandbox", obj={"config": cfg, "deployment": None})
    assert result.exit_code == 0, result.output
    cmds = [cmd for _, cmd in fake_embuild]
    assert all(cmd[cmd.index("-config") + 1] == "Release" for cmd in cmds)


def test_build_reports_new_unchanged_and_changed(isolated, firmware_repo, fake_make):
    assert "new" in build("dotbot").output
    assert "unchanged dotbot-sandbox-dotbot-v3.bin" in build("dotbot").output
    local = isolated / "cache" / "dotbot-firmware-local"
    (local / "dotbot-sandbox-dotbot-v3.bin").write_text("stale")
    assert "changed   dotbot-sandbox-dotbot-v3.bin" in build("dotbot").output


# --- `--path` / `--as` / manifest ------------------------------------------


def test_path_and_as_build_a_named_set_from_another_folder(
    isolated, emprojects, fake_embuild, monkeypatch
):
    import json

    other = isolated / "other-swarmit"
    emprojects.rename(other)
    monkeypatch.setenv("DOTBOT_FW_SOURCES_SWARMIT", str(isolated / "gone"))
    sha = _git_init(other)
    result = build("swarmit-sandbox", "--path", str(other), "--as", "test-set")
    assert result.exit_code == 0, result.output
    out = isolated / "cache" / "swarmit-test-set"
    assert not (isolated / "cache" / "swarmit-local").exists()
    assert {cwd for cwd, _ in fake_embuild} == {other}
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["kind"] == "build"
    assert manifest["source"] == "swarmit"
    assert manifest["name"] == "test-set"
    assert manifest["repo"] == str(other)
    assert manifest["git_sha"] == sha
    assert manifest["dirty"] is False
    assert manifest["build_config"] == "Debug"
    assert manifest["board"] == "dotbot-v3"
    assert manifest["built_at"]
    assert set(manifest["files"]) == SWARMIT_NAMES
    import hashlib

    boot = out / "bootloader-dotbot-v3.hex"
    entry = manifest["files"][boot.name]
    assert entry["sha256"] == hashlib.sha256(boot.read_bytes()).hexdigest()
    assert entry["git_sha"] == sha


def test_manifest_flags_a_dirty_checkout(isolated, emprojects, fake_embuild):
    import json

    _git_init(emprojects)
    (emprojects / "untracked.c").write_text("")
    assert build("swarmit-sandbox").exit_code == 0
    manifest = json.loads(
        (isolated / "cache" / "swarmit-local" / "manifest.json").read_text()
    )
    assert manifest["dirty"] is True


def test_manifest_keeps_files_from_an_earlier_build_of_the_set(
    isolated, firmware_repo, fake_make
):
    import json

    assert build("dotbot").exit_code == 0
    assert build("rgbled").exit_code == 0
    manifest = json.loads(
        (isolated / "cache" / "dotbot-firmware-local" / "manifest.json").read_text()
    )
    assert set(manifest["files"]) == {
        "dotbot-sandbox-dotbot-v3.bin",
        "rgbled-sandbox-dotbot-v3.bin",
    }
    assert manifest["git_sha"] is None  # not a git checkout


def test_path_builds_mari_gateway_from_that_tree(isolated, mari_repo, fake_embuild):
    other = isolated / "wt-mari"
    mari_repo.rename(other)
    result = build("mari-gateway", "--path", str(other))
    assert result.exit_code == 0, result.output
    assert {cwd for cwd, _ in fake_embuild} == {other / "firmware"}


def test_path_must_be_a_folder_of_that_source(isolated, mari_repo, fake_embuild):
    result = build("mari-gateway", "--path", str(mari_repo / "firmware"))
    assert result.exit_code != 0
    assert "is not a mari source folder: it has no firmware/Makefile" in result.output
    assert fake_embuild == []


def test_default_build_says_what_can_be_named(isolated, firmware_repo, fake_make):
    result = build()
    assert result.exit_code != 0
    assert "DOTBOT_FW_SOURCES_SWARMIT" in result.output
    assert "`dotbot fw build dotbot` (an app)" in result.output


@pytest.mark.parametrize("flag", ["--repo", "--checkout"])
def test_old_source_flags_are_gone(isolated, flag):
    result = build("swarmit-sandbox", flag, ".")
    assert result.exit_code != 0
    assert "No such option" in result.output


@pytest.mark.parametrize("old", ["swarmit", "mari", "dotbot-firmware"])
def test_source_names_are_not_targets(isolated, firmware_repo, fake_make, old):
    result = build(old)
    assert result.exit_code != 0
    assert f"No '{old}' app" in result.output


@pytest.mark.parametrize(
    "args",
    [["--path", "."], ["swarmit-sandbox", "dotbot", "--path", "."]],
)
def test_path_needs_names_from_one_source(isolated, args):
    result = build(*args)
    assert result.exit_code != 0
    assert "--path overrides one source folder" in result.output


def test_path_takes_several_apps(isolated, firmware_repo, fake_make, monkeypatch):
    monkeypatch.setenv("DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE", str(isolated / "gone"))
    result = build("dotbot", "rgbled", "--path", str(firmware_repo), "--print-path")
    assert result.exit_code == 0, result.output
    assert len(result.output.strip().splitlines()) == 2


@pytest.mark.parametrize("name", ["latest", "1.23.0", "v2", "a/b", "-x"])
def test_as_rejects_names_that_read_as_a_tag_or_path(isolated, name):
    result = build("swarmit-sandbox", f"--as={name}")
    assert result.exit_code != 0
    assert "cannot name a firmware set" in result.output


def test_bare_is_the_flag_and_sandbox_is_gone(isolated):
    result = build("--sandbox")
    assert result.exit_code != 0
    assert "No such option" in result.output


# --- `fw list` ------------------------------------------------------------------


def test_list_shows_sets_with_their_provenance(isolated, firmware_repo, fake_make):
    import json

    assert build("dotbot", "--as", "mine").exit_code == 0
    release = isolated / "cache" / "swarmit-0.9.0"
    release.mkdir()
    (release / "bootloader-dotbot-v3.hex").write_text("")
    (release / "config-dotbot-v3-0.9.0-0100-1.hex").write_text("")
    (release / "manifest.json").write_text(
        json.dumps({"source": "swarmit", "version": "0.9.0", "fetched_at": "t"})
    )
    result = CliRunner().invoke(fw_cmd, ["list"])
    assert result.exit_code == 0, result.output
    assert "dotbot-firmware-mine  built no git (Release, dotbot-v3)" in result.output
    assert "swarmit-0.9.0  release 0.9.0" in result.output
    assert "  dotbot-sandbox-dotbot-v3.bin" in result.output
    assert "config-" not in result.output
