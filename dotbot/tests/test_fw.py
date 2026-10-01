# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot fw` (clean/targets/make, board flavours, SES and repo lookup).

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
from dotbot.config import DotbotConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Pretend repos/DotBot-firmware exists at a tmp path with a Makefile."""
    repo = tmp_path / "fake-dotbot-firmware"
    repo.mkdir()
    (repo / "Makefile").write_text("# fake\n")
    monkeypatch.setenv("DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE", str(repo))
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
    for sub in ("build", "clean", "targets", "fetch", "list"):
        assert sub in result.output
    assert "artifacts " not in result.output
    assert "--bare" in result.output
    assert "--sandbox" not in result.output


def test_fw_artifacts_is_gone(runner):
    result = runner.invoke(fw_cmd, ["artifacts"])
    assert result.exit_code != 0


def test_fw_targets_lists_every_board_with_its_apps(runner):
    result = runner.invoke(fw_cmd, ["targets"])
    assert result.exit_code == 0
    rows = {
        ln.split()[0]: ln.split(None, 1)[1]
        for ln in result.output.splitlines()
        if ln.strip()
    }
    assert rows["dotbot-v3"].startswith("sandboxed apps (bare with --bare)")
    assert rows["nrf5340dk"].startswith("sandboxed apps")
    assert rows["sailbot-v1"] == "bare apps"
    assert not any(board.startswith("sandbox-") for board in rows)


def test_fw_targets_has_no_sandbox_flag(runner):
    assert runner.invoke(fw_cmd, ["targets", "--sandbox"]).exit_code != 0


@pytest.mark.parametrize("sub", ["build", "clean"])
def test_sandbox_flag_is_gone(runner, sub):
    result = runner.invoke(fw_cmd, [sub, "--sandbox"])
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_sandbox_prefixed_board_points_at_the_default(runner):
    result = runner.invoke(fw_cmd, ["build", "--target", "sandbox-dotbot-v3"])
    assert result.exit_code != 0
    assert "-t dotbot-v3" in result.output
    assert "sandboxed apps are the default" in result.output


def test_fw_build_rejects_unknown_target_with_suggestion(runner):
    result = runner.invoke(fw_cmd, ["build", "--target", "dotbotv3"])  # missing dash
    assert result.exit_code != 0
    assert "dotbot-v3" in result.output  # didyoumean suggestion


def test_bare_on_a_sandbox_only_board_names_its_bare_targets(runner):
    result = runner.invoke(fw_cmd, ["build", "-t", "nrf5340dk", "--bare"])
    assert result.exit_code != 0
    assert "nrf5340dk-app" in result.output


@pytest.mark.parametrize(
    "board, bare, target",
    [
        ("dotbot-v3", False, "sandbox-dotbot-v3"),
        ("dotbot-v3", True, "dotbot-v3"),
        ("nrf5340dk", False, "sandbox-nrf5340dk"),
        ("nrf52840dk", False, "nrf52840dk"),
    ],
)
def test_sandboxed_apps_are_the_default_where_a_board_has_a_sandbox(
    board, bare, target
):
    assert _fw_helpers.build_target(board, bare) == target


def test_app_image_name_follows_the_flavour():
    assert _fw_helpers.app_image_name("dotbot", "dotbot-v3", False) == (
        "dotbot-sandbox-dotbot-v3.bin"
    )
    assert _fw_helpers.app_image_name("dotbot", "dotbot-v3", True) == (
        "dotbot-dotbot-v3.hex"
    )


def test_fw_clean_cleans_the_sandboxed_target_by_default(
    runner, fake_repo, fake_segger, capture_make
):
    result = runner.invoke(fw_cmd, ["clean"])
    assert result.exit_code == 0, result.output
    cmd = capture_make[0]["cmd"]
    assert "BUILD_TARGET=sandbox-dotbot-v3" in cmd
    assert "BUILD_CONFIG=Release" in cmd
    assert "clean" in cmd
    assert "Cleaning sandbox-dotbot-v3" in result.output
    assert "✓ Cleaned" in result.output


def test_fw_clean_bare(runner, fake_repo, fake_segger, capture_make):
    result = runner.invoke(fw_cmd, ["clean", "--bare"])
    assert result.exit_code == 0, result.output
    assert "BUILD_TARGET=dotbot-v3" in capture_make[0]["cmd"]


def test_fw_clean_bare_from_config(runner, fake_repo, fake_segger, capture_make):
    cfg = DotbotConfig.model_validate({"fw": {"bare": True}})
    result = runner.invoke(
        fw_cmd,
        ["clean"],
        obj={"config": cfg},
    )
    assert result.exit_code == 0, result.output
    assert "BUILD_TARGET=dotbot-v3" in capture_make[0]["cmd"]


_BARE_CFG = {"config": DotbotConfig.model_validate({"fw": {"bare": True}})}


@pytest.mark.parametrize(
    "args, obj, env, bare",
    [
        ([], None, None, False),
        (["--bare"], None, None, True),
        (["--sandboxed"], _BARE_CFG, None, False),
        ([], _BARE_CFG, None, True),
        ([], _BARE_CFG, "0", False),
        ([], None, "1", True),
        (["--sandboxed"], None, "1", False),
    ],
)
@pytest.mark.parametrize("sub", ["build", "clean"])
def test_fw_bare_precedence(runner, monkeypatch, sub, args, obj, env, bare):
    monkeypatch.delenv("DOTBOT_BARE", raising=False)
    if env is None:
        monkeypatch.delenv("DOTBOT_FW_BARE", raising=False)
    else:
        monkeypatch.setenv("DOTBOT_FW_BARE", env)
    seen = []

    def spy(board, bare):
        seen.append(bare)
        raise click.ClickException("stop")

    monkeypatch.setattr(_fw_helpers, "build_target", spy)
    runner.invoke(fw_cmd, [sub, *args], obj=obj)
    assert seen == [bare]


def test_fw_new_still_not_implemented(runner):
    """`new` is deferred to a separate templates plan."""
    result = runner.invoke(fw_cmd, ["new", "my-experiment"])
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()


def test_run_make_returns_elapsed_seconds(fake_repo, fake_segger, monkeypatch):
    """`run_make` must return a float so subcommands can format the timing."""
    monkeypatch.setattr("dotbot.cli._fw_helpers.subprocess.call", lambda *a, **kw: 0)
    elapsed = _fw_helpers.run_make("dotbot-v3", "Release", "dotbot")
    assert isinstance(elapsed, float)
    assert elapsed >= 0


# ── `dotbot fw make` escape hatch ───────────────────────────────────────


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
    """`dotbot fw make foo bar BAZ=qux` invokes `make foo bar BAZ=qux`."""
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
    assert "dotbot fw make" in result.output


# ── Helper-level tests ──────────────────────────────────────────────────


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point the unified config's user file at a tmp dir and run in a clean
    cwd, so fw config tests don't see the real `~/.dotbot/dotbot.toml` or a
    stray `dotbot.toml`."""
    home = tmp_path / "home"
    (home / ".dotbot").mkdir(parents=True)
    monkeypatch.setattr(
        "dotbot.config.USER_CONFIG_PATH",
        home / ".dotbot" / "dotbot.toml",
    )
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


def _write_config(home, toml_body):
    (home / ".dotbot" / "dotbot.toml").write_text(toml_body)


def test_resolve_segger_dir_uses_env_first(tmp_path, monkeypatch, isolated_home):
    """Env var beats config file beats glob."""
    _write_config(isolated_home, '[fw]\nsegger_dir = "/from/config"\n')
    monkeypatch.setenv("SEGGER_DIR", str(tmp_path))
    assert _fw_helpers.resolve_segger_dir() == tmp_path


def test_resolve_segger_dir_falls_back_to_config(monkeypatch, isolated_home):
    """When SEGGER_DIR is unset, `[fw].segger_dir` from the config wins."""
    _write_config(isolated_home, '[fw]\nsegger_dir = "/from/config"\n')
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    assert _fw_helpers.resolve_segger_dir() == Path("/from/config").absolute()


def test_resolve_segger_dir_reads_the_user_file_past_a_project_file(
    monkeypatch, isolated_home
):
    _write_config(isolated_home, '[fw]\nsegger_dir = "/from/user"\n')
    Path("dotbot.toml").write_text('swarm_id = "0001"\n')
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    assert _fw_helpers.resolve_segger_dir() == Path("/from/user").absolute()


def test_resolve_segger_dir_reads_a_relative_value_from_the_file_that_sets_it(
    monkeypatch, isolated_home
):
    _write_config(isolated_home, '[fw]\nsegger_dir = "ses"\n')
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    expected = (isolated_home / ".dotbot" / "ses").resolve()
    assert _fw_helpers.resolve_segger_dir().resolve() == expected


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
    monkeypatch.delenv("DOTBOT_FW_SEGGER_DIR", raising=False)
    monkeypatch.setattr("dotbot.cli._fw_helpers.sys.platform", "linux")
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_segger_dir()
    # Error message must surface BOTH escape hatches so the user can fix
    # whichever they prefer.
    msg = str(excinfo.value)
    assert "DOTBOT_FW_SEGGER_DIR" in msg
    assert "dotbot config set fw.segger_dir" in msg


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """No source-folder env vars, no user config file, a clean cwd."""
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
    return tmp_path


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "Makefile").write_text("# fake\n")
    return path


def _config_file(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_relative_config_path_resolves_against_the_config_file(repo_env, monkeypatch):
    ws = repo_env / "workspace"
    repo = _repo(ws / "checkouts" / "fw")
    cfg = _config_file(
        ws / "dotbot.toml", '[fw.sources]\ndotbot-firmware = "checkouts/fw"\n'
    )
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    assert _fw_helpers.resolve_firmware_repo() == repo


def test_relative_config_path_ignores_the_cwd(repo_env, monkeypatch):
    ws = repo_env / "workspace"
    cfg = _config_file(ws / "dotbot.toml", '[fw.sources]\nswarmit = "sw"\n')
    _repo(Path.cwd() / "sw")  # a decoy next to the cwd, not the config
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_swarmit_repo()
    msg = str(excinfo.value)
    assert str(ws / "sw") in msg
    assert str(cfg) in msg


def test_default_is_repos_next_to_the_config_file(repo_env, monkeypatch):
    ws = repo_env / "workspace"
    fw = _repo(ws / "repos" / "DotBot-firmware")
    sw = _repo(ws / "repos" / "swarmit")
    cfg = _config_file(ws / "dotbot.toml", "")
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    assert _fw_helpers.resolve_firmware_repo() == fw
    assert _fw_helpers.resolve_swarmit_repo() == sw


def test_mari_source_is_found_by_its_firmware_makefile(repo_env, monkeypatch):
    ws = repo_env / "workspace"
    mari = ws / "repos" / "mari"
    _repo(mari / "firmware")
    cfg = _config_file(ws / "dotbot.toml", "")
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    assert _fw_helpers.resolve_mari_repo() == mari
    monkeypatch.setenv("DOTBOT_FW_SOURCES_MARI", str(mari / "firmware"))
    with pytest.raises(click.ClickException, match="firmware/Makefile"):
        _fw_helpers.resolve_mari_repo()


def test_default_uses_the_project_of_the_config_on_the_click_context(repo_env):
    from dotbot.config import load_files

    ws = repo_env / "workspace"
    sw = _repo(ws / "repos" / "swarmit")
    cfg = _config_file(ws / "dotbot.toml", "")

    @click.command()
    def probe():
        click.echo(_fw_helpers.resolve_swarmit_repo())

    result = CliRunner().invoke(
        probe, [], obj={"config": load_files([("project", cfg)])}
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == str(sw)


def test_env_var_beats_config_and_default(repo_env, monkeypatch):
    ws = repo_env / "workspace"
    _repo(ws / "repos" / "swarmit")
    elsewhere = _repo(repo_env / "elsewhere")
    cfg = _config_file(ws / "dotbot.toml", '[fw.sources]\nswarmit = "repos/swarmit"\n')
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    monkeypatch.setenv("DOTBOT_FW_SOURCES_SWARMIT", str(elsewhere))
    assert _fw_helpers.resolve_swarmit_repo() == elsewhere


def test_absolute_config_path_is_used_as_is(repo_env, monkeypatch):
    repo = _repo(repo_env / "abs" / "DotBot-firmware")
    cfg = _config_file(
        repo_env / "ws" / "dotbot.toml",
        f'[fw.sources]\ndotbot-firmware = "{repo.as_posix()}"\n',
    )
    monkeypatch.setenv("DOTBOT_CONFIG", str(cfg))
    assert _fw_helpers.resolve_firmware_repo() == repo


def test_nothing_found_names_the_key_and_env_var(repo_env):
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_swarmit_repo()
    msg = str(excinfo.value)
    assert "DOTBOT_FW_SOURCES_SWARMIT" in msg
    assert "[fw.sources]" in msg


def test_resolve_firmware_repo_env_var_pointing_at_no_makefile_errors(
    tmp_path, monkeypatch
):
    """Bad env-var path fails loudly rather than silently falling back."""
    bad = tmp_path / "no-makefile-here"
    bad.mkdir()
    monkeypatch.setenv("DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE", str(bad))
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_firmware_repo()
    assert "DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE" in str(excinfo.value)
    assert "Makefile" in str(excinfo.value)


def test_malformed_config_raises_with_path(monkeypatch, isolated_home):
    """A malformed config surfaces a clean error naming the file, not a traceback."""
    _write_config(isolated_home, "this is not [valid toml\n")
    monkeypatch.delenv("SEGGER_DIR", raising=False)
    with pytest.raises(click.ClickException) as excinfo:
        _fw_helpers.resolve_segger_dir()
    assert "dotbot.toml" in str(excinfo.value)


# ── Parity guard against silent drift ───────────────────────────────────


def _real_firmware_repo_or_skip():
    """Find the real DotBot-firmware repo for the parity test, or skip."""
    import os
    from pathlib import Path

    env = os.environ.get("DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE")
    if env and (Path(env) / "Makefile").is_file():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "repos" / "DotBot-firmware"
        if (candidate / "Makefile").is_file():
            return candidate
    pytest.skip(
        "Could not locate the real DotBot-firmware repo; set "
        "DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE or run from inside the workspace."
    )


def test_no_dotbot_firmware_app_is_named_like_a_role():
    """`fw build`, `fw fetch` and `device flash` read a role name (and
    `device flash` `programmer`) as that target, so an app with that name
    could never be built or flashed by name."""
    from dotbot.cli._fw_sources import ROLES
    from dotbot.cli.device import FLASH_TARGETS

    repo = _real_firmware_repo_or_skip()
    apps = {p.name for d in ("apps", "apps-sandbox") for p in (repo / d).iterdir()}
    assert not apps & (set(ROLES) | set(FLASH_TARGETS))


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
    makefile_targets = {
        line.strip() for line in result.stdout.splitlines() if line.strip()
    }
    cli_targets = set(_fw_helpers.BARE_TARGETS) | {
        f"sandbox-{b}" for b in _fw_helpers.SANDBOX_BOARDS
    }
    assert makefile_targets == cli_targets, (
        f"CLI hardcoded targets drifted from Makefile.\n"
        f"In CLI but not Makefile: {cli_targets - makefile_targets}\n"
        f"In Makefile but not CLI: {makefile_targets - cli_targets}"
    )


def test_segger_dir_reads_the_mechanical_env_name_first(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_FW_SEGGER_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("SEGGER_DIR", str(tmp_path / "b"))
    assert _fw_helpers.resolve_segger_dir() == tmp_path / "a"
    monkeypatch.delenv("DOTBOT_FW_SEGGER_DIR")
    assert _fw_helpers.resolve_segger_dir() == tmp_path / "b"


def test_the_artifacts_dir_comes_from_the_config_relative_to_its_file(
    tmp_path, monkeypatch
):
    from dotbot.cli._artifacts import artifacts_dir

    for name in ("DOTBOT_FW_ARTIFACTS_DIR", "DOTBOT_ARTIFACTS_DIR"):
        monkeypatch.delenv(name, raising=False)
    project = tmp_path / "lab"
    project.mkdir()
    (project / "dotbot.toml").write_text('[fw]\nartifacts_dir = "cache"\n')
    monkeypatch.chdir(project)
    assert artifacts_dir() == (project / "cache").resolve()
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path / "env"))
    assert artifacts_dir() == (tmp_path / "env").resolve()
