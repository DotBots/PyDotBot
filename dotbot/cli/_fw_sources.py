# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Build the firmware images a release ships, from local source folders.

What `dotbot fw build` takes, and the source folder each builds from:

- an app name: a sandboxed app (`.bin`) or a bare app (`.hex`), built
  through the DotBot-firmware Makefile;
- `swarmit-sandbox`: the swarmit bootloader for one board and the network
  core;
- `mari-gateway`: the Mari gateway (app + net cores) from mari, optionally
  one net-core image per TSCH schedule.

Each source is built through its own entry point: the swarmit and mari
Makefiles (which always rebuild in full), and Mari's `build-schedules.sh`
for the per-schedule gateway images. SES names every output
`<project>-<BuildTarget>.<ext>`, which is also the release asset name, so
collecting is a flat copy into the set directory
`<artifacts>/<source>-<name>/`, next to a `manifest.json`.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import click

from dotbot.cli import _fw_helpers

SOURCES = ("dotbot-firmware", "swarmit", "mari")

# The roles `fw build`, `fw fetch` and `device flash` take by name, and the
# source each builds from. Any other name is a DotBot-firmware app, so no app
# may be called one of these.
ROLES = {"swarmit-sandbox": "swarmit", "mari-gateway": "mari"}
APP_SOURCE = "dotbot-firmware"
# The release a target's images are fetched from. Mari's releases publish no
# firmware; the swarmit release carries the Mari gateway.
ROLE_RELEASES = {"swarmit-sandbox": "swarmit", "mari-gateway": "swarmit"}
APP_RELEASE = "dotbot-firmware"

# Apps left out of the default set and of help text; naming one still builds
# it.
LEGACY_APPS = frozenset({"lh2_calibration"})

# Boards with a `swarmit-bootloader-<board>.emProject` that a release ships.
SWARMIT_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})

# What `--part` selects inside swarmit-sandbox: swarmit make targets.
SWARMIT_PARTS = ("bootloader", "netcore")

# The board the Mari gateway images are built for.
MARI_GATEWAY_BOARD = "nrf5340dk"


@dataclass(frozen=True)
class BuildCommand:
    """One run of a source folder's own build entry point.

    `env` is added to the environment, next to SEGGER_DIR.
    """

    argv: tuple[str, ...]
    cwd: Path
    label: str
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildPlan:
    """The commands that build a role, and the files they leave.

    Each output is already named as its release asset.
    """

    commands: list[BuildCommand]
    outputs: list[Path]


def set_dir(source: str, name: str, artifacts_root: Path) -> Path:
    """Where a source's locally built set `name` is collected."""
    return artifacts_root / f"{source}-{name}"


def _exe(project_dir: Path, build_target: str, name: str, config: str) -> Path:
    return (
        project_dir
        / "Output"
        / build_target
        / config
        / "Exe"
        / f"{name}-{build_target}.hex"
    )


def _check_parts(parts: Iterable[str] | None) -> list[str]:
    parts = set(parts or SWARMIT_PARTS)
    unknown = parts - set(SWARMIT_PARTS)
    if unknown:
        raise click.ClickException(
            f"swarmit-sandbox has no part {', '.join(sorted(unknown))}. "
            f"Parts: {', '.join(SWARMIT_PARTS)}."
        )
    return [part for part in SWARMIT_PARTS if part in parts]


# --- swarmit ---------------------------------------------------------------


def swarmit_plan(
    repo: Path, board: str, config: str, parts: Iterable[str] | None = None
) -> BuildPlan:
    """`make bootloader netcore` in swarmit, or the make targets `parts` names.

    The board only matters for the bootloader.
    """
    parts = _check_parts(parts)
    if "bootloader" in parts and board not in SWARMIT_BOARDS:
        raise click.ClickException(
            f"swarmit has no bootloader for board {board!r}. "
            f"Supported: {', '.join(sorted(SWARMIT_BOARDS))}."
        )
    outputs = {
        "bootloader": _exe(repo / "device/bootloader", board, "bootloader", config),
        "netcore": _exe(repo / "device/network_core", "nrf5340-net", "netcore", config),
    }
    command = BuildCommand(
        (
            "make",
            "-C",
            str(repo),
            *parts,
            f"BUILD_TARGET={board}",
            f"BUILD_CONFIG={config}",
        ),
        repo,
        " ".join(parts),
    )
    return BuildPlan([command], [outputs[part] for part in parts])


# --- mari --------------------------------------------------------------------


def mari_plan(
    repo: Path, config: str, schedules: Iterable[str] | None = None
) -> BuildPlan:
    """`make gateway` in mari's firmware folder.

    With `schedules`, `make gateway-app` and then Mari's `build-schedules.sh`
    for those schedules instead, which stages one net image per schedule in
    `firmware/Output/schedules/` under its release name.
    """
    from dotbot.firmware.schedules import net_image_name

    fw = repo / "firmware"
    app = _exe(fw / "app/03app_gateway_app", "nrf5340-app", "03app_gateway_app", config)

    def make(target: str) -> BuildCommand:
        return BuildCommand(
            ("make", "-C", str(fw), target, f"BUILD_CONFIG={config}"), fw, target
        )

    schedules = list(schedules or ())
    if not schedules:
        net = _exe(
            fw / "app/03app_gateway_net", "nrf5340-net", "03app_gateway_net", config
        )
        return BuildPlan([make("gateway")], [app, net])
    script = BuildCommand(
        ("bash", str(fw / "build-schedules.sh"), *schedules),
        fw,
        f"gateway-net, schedule {' '.join(schedules)}",
        {"BUILD_CONFIG": config},
    )
    staged = fw / "Output" / "schedules"
    return BuildPlan(
        [make("gateway-app"), script],
        [app] + [staged / net_image_name(schedule) for schedule in schedules],
    )


def resolve_schedules(values: Iterable[str]) -> list[str]:
    """Expand `--schedule` values (`all` means every schedule), in ladder order."""
    from dotbot.firmware.schedules import MARI_SCHEDULES

    values = set(values)
    if "all" in values:
        return list(MARI_SCHEDULES)
    return [name for name in MARI_SCHEDULES if name in values]


# Lines of captured build output shown when a quiet build fails.
_FAILURE_TAIL = 60

_TOOL_HINTS = {
    "make": "swarmit and mari are built through their Makefiles, which need "
    "GNU make.",
    "bash": "Mari's build-schedules.sh, which builds the per-schedule gateway "
    "images, needs bash; on Windows, run from Git Bash or WSL.",
}


def _execute(
    argv: tuple[str, ...], cwd: Path, env: dict[str, str], capture: bool
) -> tuple[int, str]:
    """Run `argv`; return its exit code and, if `capture`, its combined output."""
    try:
        if not capture:
            return subprocess.call(argv, cwd=cwd, env=env), ""
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"`{argv[0]}` was not found on PATH. {_TOOL_HINTS.get(argv[0], '')}"
        ) from exc
    return result.returncode, result.stdout


def run_plan(plan: BuildPlan, *, verbose: bool = False) -> list[Path]:
    """Run `plan`'s commands in order; return its outputs.

    With `verbose` the output streams through; otherwise only the tail of a
    failing command's output is shown.
    """
    segger = _fw_helpers.require_embuild()
    for command in plan.commands:
        extra = {"SEGGER_DIR": str(segger), **command.env}
        env = {**_fw_helpers._make_env(segger), **command.env}
        if verbose:
            shown = " ".join(f"{k}={shlex.quote(v)}" for k, v in extra.items())
            click.echo(f"$ {shown} {shlex.join(command.argv)}", err=True)
        else:
            click.echo(f"  building {command.label}", err=True)
        t0 = time.perf_counter()
        rc, output = _execute(command.argv, command.cwd, env, capture=not verbose)
        elapsed = time.perf_counter() - t0
        if rc != 0:
            if output:
                tail = output.rstrip().splitlines()[-_FAILURE_TAIL:]
                click.echo("\n".join(tail), err=True)
            raise click.ClickException(
                f"Building {command.label} exited {rc} after {elapsed:.1f}s"
                + ("." if verbose else " (rerun with -v for the full output).")
            )
    return plan.outputs


def build_swarmit(
    board: str,
    config: str,
    *,
    parts: Iterable[str] | None = None,
    repo: Path | None = None,
    verbose: bool = False,
) -> list[Path]:
    """Build the swarmit images (or `parts` of them) for `board`."""
    repo = repo or _fw_helpers.resolve_swarmit_repo()
    return run_plan(swarmit_plan(repo, board, config, parts), verbose=verbose)


def build_mari(
    config: str,
    *,
    schedules: Iterable[str] | None = None,
    repo: Path | None = None,
    verbose: bool = False,
) -> list[Path]:
    """Build the Mari gateway images, one net image per schedule if given."""
    repo = repo or _fw_helpers.resolve_mari_repo()
    if schedules and not (repo / "firmware" / "build-schedules.sh").is_file():
        raise click.ClickException(
            f"{repo} has no firmware/build-schedules.sh, which builds the "
            "per-schedule gateway images; update that mari checkout."
        )
    return run_plan(mari_plan(repo, config, schedules), verbose=verbose)


# --- dotbot-firmware -------------------------------------------------------


def default_apps(build_target: str, repo: Path | None = None) -> list[str]:
    """The release set for `build_target`, without `LEGACY_APPS`.

    Falls back to every buildable app when the Makefile names no release
    set for the target.
    """
    apps = _fw_helpers.list_release_projects(build_target, repo)
    if not apps:
        apps = _fw_helpers.list_projects(build_target, repo)
    return [app for app in apps if app not in LEGACY_APPS]


def dotbot_firmware_apps(
    target: str, apps: list[str] | None = None, repo: Path | None = None
) -> list[str]:
    """The apps to build for `target`: `apps`, checked, or the release set.

    A name in `LEGACY_APPS` is accepted without being listed: the Makefile
    leaves those apps out of its default project list.
    """
    if not apps:
        return default_apps(target, repo)
    available = _fw_helpers.list_projects(target, repo)
    shadowed = sorted(set(available) & set(ROLES))
    if shadowed:
        raise click.ClickException(
            f"DotBot-firmware has an app named {', '.join(shadowed)}, which is "
            "also a role name; rename the app."
        )
    unknown = [app for app in apps if app not in available and app not in LEGACY_APPS]
    if unknown:
        raise click.ClickException(
            f"No {', '.join(repr(a) for a in unknown)} app for {target}.\n"
            f"Roles: {', '.join(ROLES)}.\n"
            f"Apps for {target}: {', '.join(available)}."
        )
    return list(apps)


def build_dotbot_firmware(
    target: str,
    apps: list[str],
    config: str,
    *,
    repo: Path | None = None,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build `apps` for `target`; return the produced files."""
    click.echo(f"  building {target}: {' '.join(apps)}", err=True)
    _fw_helpers.run_make(
        target,
        config,
        rebuild=rebuild,
        quiet=not verbose,
        make_targets=apps,
        variables={"PROJECTS": " ".join(apps)},
        repo=repo,
    )
    return dotbot_firmware_outputs(target, apps, config, repo)


def dotbot_firmware_outputs(
    target: str, apps: list[str], config: str, repo: Path | None = None
) -> list[Path]:
    """The files `build_dotbot_firmware(target, apps, config)` produces."""
    return [_fw_helpers.artifact_path(target, app, config, repo) for app in apps]


# --- collection --------------------------------------------------------------


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def git_state(repo: Path) -> tuple[str | None, bool | None]:
    """(HEAD sha, dirty) of `repo`, or (None, None) outside a git checkout."""
    sha = _git(repo, "rev-parse", "HEAD")
    if sha is None:
        return None, None
    status = _git(repo, "status", "--porcelain")
    return sha.strip(), (bool(status.strip()) if status is not None else None)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


MANIFEST_NAME = "manifest.json"


def write_build_manifest(
    out_dir: Path,
    *,
    source: str,
    name: str,
    repo: Path,
    config: str,
    board: str,
    files: Iterable[Path],
) -> dict:
    """Record this build in `out_dir/manifest.json`; return the manifest.

    The top level describes the latest build. `files` covers every image in
    the set, so one rebuilt with `--part` sits next to older ones, each carrying
    the build it came from.
    """
    from dotbot import pydotbot_version

    sha, dirty = git_state(repo)
    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = out_dir / MANIFEST_NAME
    try:
        previous = json.loads(path.read_text()).get("files", {})
    except (OSError, ValueError, AttributeError):
        previous = {}
    entries = {
        fname: entry
        for fname, entry in previous.items()
        if isinstance(entry, dict) and (out_dir / fname).is_file()
    }
    for f in files:
        entries[f.name] = {
            "sha256": sha256(f),
            "git_sha": sha,
            "dirty": dirty,
            "build_config": config,
            "built_at": built_at,
        }
    manifest = {
        "kind": "build",
        "source": source,
        "name": name,
        "repo": str(Path(repo).resolve()),
        "git_sha": sha,
        "dirty": dirty,
        "build_config": config,
        "board": board,
        "built_at": built_at,
        "pydotbot": pydotbot_version(),
        "files": dict(sorted(entries.items())),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def collect(files: Iterable[Path], out_dir: Path) -> list[Path]:
    """Copy `files` flat into `out_dir` under their own names.

    An existing entry is replaced, and a symlink is removed rather than
    written through, so a copy never lands inside a build tree.
    """
    files = list(files)
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        raise click.ClickException(
            "Build finished but these outputs are missing:\n  " + "\n  ".join(missing)
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in files:
        dst = out_dir / src.name
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied
