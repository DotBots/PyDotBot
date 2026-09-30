# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for building firmware sets from local source folders (`fw build`).

No SES and no real source folder: the build commands are stubbed, and the build
trees are tmp directories with the files SES would write.
"""

import shlex
import shutil
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
    (fw / "build-schedules.sh").write_text("# fake\n")
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
def fake_build(monkeypatch):
    """Stub the swarmit and mari entry points: record each command as
    (cwd, argv, env) and write the files it would leave."""
    from dotbot.firmware.schedules import net_image_name

    calls = []

    def var(argv, name):
        return next(a.split("=", 1)[1] for a in argv if a.startswith(f"{name}="))

    def fake(argv, cwd, env, capture):
        calls.append((Path(cwd), list(argv), env))
        written = []
        if argv[0] == "bash":
            fw = Path(argv[1]).parent
            for schedule in argv[2:]:
                image = fw / "Output" / "schedules" / net_image_name(schedule)
                written.append((image, f"net {schedule} {env['BUILD_CONFIG']}"))
        else:
            root = Path(argv[2])
            config = var(argv, "BUILD_CONFIG")
            targets = [a for a in argv[3:] if "=" not in a]
            if (root / "build-schedules.sh").exists():
                app, net = fs.mari_plan(root.parent, config).outputs
                wanted = {"gateway": [app, net], "gateway-app": [app]}
                written += [(p, p.stem) for t in targets for p in wanted[t]]
            else:
                plan = fs.swarmit_plan(root, var(argv, "BUILD_TARGET"), config, targets)
                written += [(p, p.stem) for p in plan.outputs]
        for path, content in written:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return 0, "compiler output\n"

    monkeypatch.setattr(fs, "_execute", fake)
    return calls


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
    plan = fs.swarmit_plan(tmp_path, "dotbot-v3", "Debug")
    assert {p.name for p in plan.outputs} == SWARMIT_NAMES
    assert all("Debug" in p.parts for p in plan.outputs)


def test_swarmit_is_built_by_its_makefile(tmp_path):
    (command,) = fs.swarmit_plan(tmp_path, "dotbot-v3", "Debug").commands
    assert command.argv == (
        "make",
        "-C",
        str(tmp_path),
        "bootloader",
        "netcore",
        "BUILD_TARGET=dotbot-v3",
        "BUILD_CONFIG=Debug",
    )


def test_build_and_flash_use_the_release_file_names(tmp_path):
    from dotbot.firmware.flash import DEVICE_ASSETS
    from dotbot.firmware.schedules import MARI_SCHEDULES, net_image_name

    swarmit = fs.swarmit_plan(tmp_path, "dotbot-v3", "Debug").outputs
    mari = fs.mari_plan(tmp_path, "Debug").outputs
    built = {p.name for p in swarmit + mari}
    assert built == SWARMIT_RELEASE_HEX
    roles = DEVICE_ASSETS["dotbot-v3"], DEVICE_ASSETS["gateway"]
    assert {role[core] for role in roles for core in ("app", "net")} == built
    scheduled = fs.mari_plan(tmp_path, "Debug", schedules=list(MARI_SCHEDULES))
    assert [p.name for p in scheduled.outputs[1:]] == [
        net_image_name(name) for name in MARI_SCHEDULES
    ]


def test_swarmit_rejects_a_board_without_bootloader(tmp_path):
    with pytest.raises(click.ClickException):
        fs.swarmit_plan(tmp_path, "nrf5340dk-app", "Release")


def test_swarmit_parts_select_make_targets_and_swarmit_has_no_gateway(tmp_path):
    plan = fs.swarmit_plan(tmp_path, "nrf5340dk-app", "Debug", ["netcore"])
    assert [p.name for p in plan.outputs] == ["netcore-nrf5340-net.hex"]
    assert [a for a in plan.commands[0].argv[3:] if "=" not in a] == ["netcore"]
    with pytest.raises(click.ClickException, match="swarmit-sandbox has no part"):
        fs.swarmit_plan(tmp_path, "dotbot-v3", "Debug", ["gateway"])


def test_mari_gateway_is_make_gateway_in_the_mari_firmware_dir(tmp_path):
    plan = fs.mari_plan(tmp_path, "Debug")
    assert {p.name for p in plan.outputs} == MARI_NAMES
    (command,) = plan.commands
    assert command.argv == (
        "make",
        "-C",
        str(tmp_path / "firmware"),
        "gateway",
        "BUILD_CONFIG=Debug",
    )


def test_mari_schedules_are_built_by_maris_script(tmp_path):
    plan = fs.mari_plan(tmp_path, "Debug", ["tiny", "big"])
    make, script = plan.commands
    assert make.argv[3] == "gateway-app"
    assert script.argv == (
        "bash",
        str(tmp_path / "firmware" / "build-schedules.sh"),
        "tiny",
        "big",
    )
    assert script.env == {"BUILD_CONFIG": "Debug"}
    staged = tmp_path / "firmware" / "Output" / "schedules"
    assert plan.outputs[1:] == [
        staged / "03app_gateway_net-tiny.hex",
        staged / "03app_gateway_net-big.hex",
    ]


def test_schedule_all_expands_in_ladder_order():
    from dotbot.firmware.schedules import MARI_SCHEDULES

    assert fs.resolve_schedules(["all"]) == list(MARI_SCHEDULES)
    assert fs.resolve_schedules([]) == []
    last, first = list(MARI_SCHEDULES)[-1], list(MARI_SCHEDULES)[0]
    assert fs.resolve_schedules([last, first]) == [first, last]


# --- `fw build` ---------------------------------------------------------------


def test_build_swarmit_defaults_to_debug_into_the_local_set(
    isolated, swarmit_repo, fake_build
):
    result = build("swarmit-sandbox")
    assert result.exit_code == 0, result.output
    assert "Building swarmit-sandbox for dotbot-v3" in result.output
    local = isolated / "cache" / "swarmit-local"
    assert {p.name for p in local.iterdir()} == SWARMIT_NAMES | {"manifest.json"}
    assert [argv for _, argv, _ in fake_build] == [
        [
            "make",
            "-C",
            str(swarmit_repo),
            "bootloader",
            "netcore",
            "BUILD_TARGET=dotbot-v3",
            "BUILD_CONFIG=Debug",
        ]
    ]
    assert fake_build[0][2]["SEGGER_DIR"] == str(isolated / "segger")


def test_build_mari_gateway_defaults_to_debug_into_the_mari_set(
    isolated, mari_repo, fake_build
):
    import json

    result = build("mari-gateway")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    assert {p.name for p in local.iterdir()} == MARI_NAMES | {"manifest.json"}
    assert [argv[2:] for _, argv, _ in fake_build] == [
        [str(mari_repo / "firmware"), "gateway", "BUILD_CONFIG=Debug"]
    ]
    manifest = json.loads((local / "manifest.json").read_text())
    assert manifest["board"] == "nrf5340dk"


def test_build_mari_schedule_builds_the_image_flash_reads(
    isolated, mari_repo, fake_build
):
    result = build("mari-gateway", "--schedule", "tiny")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    assert {p.name for p in local.iterdir()} == {
        "03app_gateway_app-nrf5340-app.hex",
        "03app_gateway_net-tiny.hex",
        "manifest.json",
    }
    assert (local / "03app_gateway_net-tiny.hex").read_text() == "net tiny Debug"
    assert [argv[1:] for _, argv, _ in fake_build][-1] == [
        str(mari_repo / "firmware" / "build-schedules.sh"),
        "tiny",
    ]


def test_build_mari_schedule_all_builds_every_schedule(isolated, mari_repo, fake_build):
    from dotbot.firmware.schedules import MARI_SCHEDULES, net_image_name

    result = build("mari-gateway", "--schedule", "all")
    assert result.exit_code == 0, result.output
    local = isolated / "cache" / "mari-local"
    for name in MARI_SCHEDULES:
        assert (local / net_image_name(name)).read_text() == f"net {name} Debug"
    assert not (local / "03app_gateway_net-nrf5340-net.hex").exists()
    assert fake_build[-1][1][2:] == list(MARI_SCHEDULES)


def test_build_mari_schedule_needs_maris_script(isolated, mari_repo, fake_build):
    (mari_repo / "firmware" / "build-schedules.sh").unlink()
    result = build("mari-gateway", "--schedule", "tiny")
    assert result.exit_code != 0
    assert "has no firmware/build-schedules.sh" in result.output
    assert fake_build == []


def test_a_failing_build_shows_the_tail_of_its_output(
    isolated, swarmit_repo, monkeypatch
):
    output = "".join(f"line {i}\n" for i in range(100))
    monkeypatch.setattr(fs, "_execute", lambda argv, cwd, env, capture: (2, output))
    result = build("swarmit-sandbox")
    assert result.exit_code != 0
    assert "line 99" in result.output and "line 40" in result.output
    assert "line 39" not in result.output
    assert "Building bootloader netcore exited 2" in result.output
    assert "rerun with -v" in result.output


def test_verbose_streams_the_build_and_prints_the_command(
    isolated, swarmit_repo, monkeypatch
):
    seen = []
    monkeypatch.setattr(
        fs,
        "_execute",
        lambda argv, cwd, env, capture: seen.append(capture) or (0, ""),
    )
    result = build("swarmit-sandbox", "-v")
    assert seen == [False]
    segger, repo = (shlex.quote(str(p)) for p in (isolated / "segger", swarmit_repo))
    assert f"$ SEGGER_DIR={segger} make -C {repo} bootloader netcore" in result.output


@pytest.mark.parametrize("capture", [True, False])
def test_a_missing_build_tool_is_named(tmp_path, monkeypatch, capture):
    def missing(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory", "bash")

    monkeypatch.setattr(fs.subprocess, "run", missing)
    monkeypatch.setattr(fs.subprocess, "call", missing)
    with pytest.raises(click.ClickException) as exc:
        fs._execute(("bash", "build-schedules.sh"), tmp_path, {}, capture)
    message = exc.value.format_message()
    assert "`bash` was not found on PATH" in message
    assert "Git Bash or WSL" in message


@pytest.mark.parametrize("names", [[], ["swarmit-sandbox"], ["spin"]])
def test_build_schedule_without_mari_gateway_named_errors(
    isolated, swarmit_repo, fake_build, names
):
    result = build(*names, "--schedule", "tiny")
    assert result.exit_code != 0
    assert "--schedule only applies to mari-gateway" in result.output
    assert "dotbot fw build mari-gateway --schedule tiny" in result.output
    assert fake_build == []


def test_build_part_without_swarmit_sandbox_errors(isolated):
    result = build("mari-gateway", "--part", "netcore")
    assert result.exit_code != 0
    assert "dotbot fw build swarmit-sandbox --part netcore" in result.output
    result = build("--part", "netcore")
    assert "dotbot fw build swarmit-sandbox --part netcore" in result.output


@pytest.mark.parametrize("names", [[], ["swarmit-sandbox"]])
def test_build_part_that_names_an_app_points_at_the_argument(isolated, names):
    result = build(*names, "--part", "spin")
    assert result.exit_code != 0
    assert "--part takes bootloader or netcore" in result.output
    assert "`dotbot fw build spin`" in result.output


def test_build_bare_on_a_role_only_errors(isolated):
    result = build("swarmit-sandbox", "--bare")
    assert result.exit_code != 0
    assert "--bare/--sandboxed only apply to apps" in result.output


def test_build_bare_from_config_does_not_refuse_a_role(
    isolated, swarmit_repo, fake_build
):
    cfg = DotbotConfig.model_validate({"fw": {"bare": True}})
    result = build("swarmit-sandbox", obj={"config": cfg, "deployment": None})
    assert result.exit_code == 0, result.output


def test_build_schedule_rejects_an_unknown_name(isolated):
    result = build("mari-gateway", "--schedule", "gigantic")
    assert result.exit_code != 0
    assert "gigantic" in result.output


def test_build_swarmit_honors_build_config(isolated, swarmit_repo, fake_build):
    result = build("swarmit-sandbox", "--build-config", "Release", "--rebuild")
    assert result.exit_code == 0, result.output
    assert all("BUILD_CONFIG=Release" in argv for _, argv, _ in fake_build)


def test_build_mari_gateway_without_a_source_says_where_to_put_it(isolated):
    result = build("mari-gateway")
    assert result.exit_code != 0
    assert "DOTBOT_FW_SOURCES_MARI" in result.output
    assert "mari under [fw.sources]" in result.output
    assert "--path /path/to/mari" in result.output


def test_build_names_the_repos_folder_it_looked_in(isolated):
    config = isolated / "work" / "dotbot.toml"
    config.write_text("")
    result = build("mari-gateway")
    assert result.exit_code != 0
    output = " ".join(result.output.split())
    looked = str(Path("work", "repos", "mari"))
    assert f"{looked} (next to " in output
    assert f"{config.name}) has no firmware/Makefile" in output
    assert "--path /path/to/mari" in output


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
    isolated, firmware_repo, swarmit_repo, fake_make, fake_build
):
    result = build("swarmit-sandbox", "--part", "bootloader")
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
    isolated, firmware_repo, swarmit_repo, mari_repo, fake_make, fake_build
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
    isolated, firmware_repo, swarmit_repo, mari_repo, fake_make, fake_build
):
    result = build()
    assert result.exit_code == 0, result.output
    assert (isolated / "cache" / "swarmit-local").is_dir()
    assert (isolated / "cache" / "mari-local").is_dir()
    assert (isolated / "cache" / "dotbot-firmware-local").is_dir()


def test_build_default_skips_swarmit_on_a_board_without_bootloader(
    isolated, firmware_repo, swarmit_repo, mari_repo, fake_make
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
    isolated, firmware_repo, swarmit_repo, mari_repo, fake_make, fake_build
):
    result = build(
        "--print-path",
        "swarmit-sandbox",
        "mari-gateway",
        "calibrate",
        "--schedule",
        "huge",
    )
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    cache = isolated / "cache"
    assert str(cache / "swarmit-local" / "bootloader-dotbot-v3.hex") in lines
    assert str(cache / "mari-local" / "03app_gateway_net-huge.hex") in lines
    assert (
        str(cache / "dotbot-firmware-local" / "calibrate-sandbox-dotbot-v3.bin")
        in lines
    )
    assert fake_make == [] and fake_build == []


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
    isolated, firmware_repo, swarmit_repo, fake_make, fake_build
):
    cfg = DotbotConfig.model_validate({"fw": {"build_config": "Release"}})
    result = build("swarmit-sandbox", obj={"config": cfg, "deployment": None})
    assert result.exit_code == 0, result.output
    assert all("BUILD_CONFIG=Release" in argv for _, argv, _ in fake_build)


def test_build_reports_new_unchanged_and_changed(isolated, firmware_repo, fake_make):
    assert "new" in build("dotbot").output
    assert "unchanged dotbot-sandbox-dotbot-v3.bin" in build("dotbot").output
    local = isolated / "cache" / "dotbot-firmware-local"
    (local / "dotbot-sandbox-dotbot-v3.bin").write_text("stale")
    assert "changed   dotbot-sandbox-dotbot-v3.bin" in build("dotbot").output


# --- `--path` / `--as` / manifest ------------------------------------------


def test_path_and_as_build_a_named_set_from_another_folder(
    isolated, swarmit_repo, fake_build, monkeypatch
):
    import json

    other = isolated / "other-swarmit"
    swarmit_repo.rename(other)
    monkeypatch.setenv("DOTBOT_FW_SOURCES_SWARMIT", str(isolated / "gone"))
    sha = _git_init(other)
    result = build("swarmit-sandbox", "--path", str(other), "--as", "test-set")
    assert result.exit_code == 0, result.output
    out = isolated / "cache" / "swarmit-test-set"
    assert not (isolated / "cache" / "swarmit-local").exists()
    assert {cwd for cwd, _, _ in fake_build} == {other}
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


def test_manifest_flags_a_dirty_checkout(isolated, swarmit_repo, fake_build):
    import json

    _git_init(swarmit_repo)
    (swarmit_repo / "untracked.c").write_text("")
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


def test_path_builds_mari_gateway_from_that_tree(isolated, mari_repo, fake_build):
    other = isolated / "wt-mari"
    mari_repo.rename(other)
    result = build("mari-gateway", "--path", str(other))
    assert result.exit_code == 0, result.output
    assert {cwd for cwd, _, _ in fake_build} == {other / "firmware"}


@pytest.mark.parametrize("env_var", [False, True])
def test_a_relative_source_folder_resolves_against_the_cwd(
    isolated, mari_repo, fake_build, monkeypatch, env_var
):
    """make and build-schedules.sh run in the source folder, so a relative
    --path or env var reaches them as an absolute path."""
    monkeypatch.chdir(isolated)
    if env_var:
        monkeypatch.setenv("DOTBOT_FW_SOURCES_MARI", "mari")
        result = build("mari-gateway", "--schedule", "tiny")
    else:
        monkeypatch.setenv("DOTBOT_FW_SOURCES_MARI", str(isolated / "gone"))
        result = build("mari-gateway", "--schedule", "tiny", "--path", "mari")
    assert result.exit_code == 0, result.output
    fw = mari_repo / "firmware"
    assert [(cwd, argv[:3]) for cwd, argv, _ in fake_build] == [
        (fw, ["make", "-C", str(fw)]),
        (fw, ["bash", str(fw / "build-schedules.sh"), "tiny"]),
    ]


def test_path_must_be_a_folder_of_that_source(isolated, mari_repo, fake_build):
    result = build("mari-gateway", "--path", str(mari_repo / "firmware"))
    assert result.exit_code != 0
    assert "is not a mari source folder: it has no firmware/Makefile" in result.output
    assert fake_build == []


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


def test_part_has_no_short_form(isolated):
    result = build("swarmit-sandbox", "-a", "netcore")
    assert result.exit_code != 0
    assert "No such option '-a'" in result.output


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
    assert (
        "dotbot-firmware-mine  built from DotBot-firmware (not a git checkout)  "
        "just now"
    ) in result.output
    assert "swarmit-0.9.0  release 0.9.0" in result.output
    assert "  dotbot-sandbox-dotbot-v3.bin" in result.output
    assert "config-" not in result.output


def test_list_names_the_commit_and_dirty_state_a_set_was_built_from(
    isolated, swarmit_repo, fake_build
):
    sha = _git_init(swarmit_repo)
    (swarmit_repo / "untracked.c").write_text("")
    assert build("swarmit-sandbox").exit_code == 0
    result = CliRunner().invoke(fw_cmd, ["list"])
    assert f"swarmit-local  built from swarmit@{sha[:7]} (dirty)  just now" in (
        result.output
    )


@pytest.mark.parametrize(
    "age, shown",
    [(0, "just now"), (125, "2m ago"), (2 * 3600 + 5, "2h ago"), (3 * 86400, "3d ago")],
)
def test_list_says_how_long_ago_a_set_was_built(age, shown):
    from datetime import datetime, timedelta, timezone

    from dotbot.cli.fw import _ago

    then = datetime.now(timezone.utc) - timedelta(seconds=age)
    assert _ago(then.isoformat(timespec="seconds")) == shown
    assert _ago(None) == ""


@pytest.mark.parametrize(
    "manifest",
    [
        "[]",
        '"text"',
        '{"kind": "build", "git_sha": 7, "repo": 3, "files": []}',
        '{"kind": "build", "built_at": "yesterday"}',
    ],
)
def test_list_survives_a_malformed_manifest(isolated, manifest):
    folder = isolated / "cache" / "swarmit-odd"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(manifest)
    (folder / "netcore-nrf5340-net.hex").write_text("")
    result = CliRunner().invoke(fw_cmd, ["list"])
    assert result.exit_code == 0, result.output
    assert "swarmit-odd" in result.output
    assert "  netcore-nrf5340-net.hex" in result.output
