# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Build the firmware set a release ships, from local checkouts.

Two sources, matching the two GitHub release sources `dotbot fw fetch`
downloads from:

- `dotbot-firmware`: bare apps (`.hex`) and sandbox apps (`.bin`), built
  through the DotBot-firmware Makefile.
- `swarmit`: the bootloader for one board, the network core, and the Mari
  gateway (app + net cores) from swarmit's pinned `mari` submodule, built by
  calling emBuild on each `.emProject` directly (the swarmit Makefiles always
  pass `-rebuild`).

SES names every output `<project>-<BuildTarget>.<ext>`, which is also the
release asset name, so collecting is a flat copy into
`<artifacts>/<source>-local/`.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import click

from dotbot.cli import _fw_helpers

SOURCES = ("dotbot-firmware", "swarmit")
FLAVORS = ("bare", "sandbox")

# Apps left out of the default set even when a release still ships them.
# `-a <app>` builds them explicitly.
LEGACY_APPS = frozenset({"lh2_calibration"})

# Boards with a `swarmit-bootloader-<board>.emProject` that a release ships.
SWARMIT_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})


@dataclass(frozen=True)
class EmBuildStep:
    """One emBuild invocation and the file it produces, relative to `cwd`."""

    cwd: Path
    emproject: str
    project: str
    output: Path


def local_dir(source: str, artifacts_root: Path) -> Path:
    """Where a source's locally built set is collected."""
    return artifacts_root / f"{source}-local"


# --- swarmit ---------------------------------------------------------------


def swarmit_steps(repo: Path, board: str, config: str) -> list[EmBuildStep]:
    """The emBuild steps for the swarmit release set of one board."""
    if board not in SWARMIT_BOARDS:
        raise click.ClickException(
            f"swarmit has no bootloader for board {board!r}. "
            f"Supported: {', '.join(sorted(SWARMIT_BOARDS))}."
        )
    mari = repo / "mari" / "firmware"

    def exe(project_dir: str, build_target: str, name: str) -> Path:
        return (
            Path(project_dir)
            / "Output"
            / build_target
            / config
            / "Exe"
            / f"{name}-{build_target}.hex"
        )

    return [
        EmBuildStep(
            repo,
            f"swarmit-bootloader-{board}.emProject",
            "bootloader",
            exe("device/bootloader", board, "bootloader"),
        ),
        EmBuildStep(
            repo,
            "swarmit-netcore.emProject",
            "netcore",
            exe("device/network_core", "nrf5340-net", "netcore"),
        ),
        EmBuildStep(
            mari,
            "mari-gateway-app-nrf5340dk.emProject",
            "03app_gateway_app",
            exe("app/03app_gateway_app", "nrf5340-app", "03app_gateway_app"),
        ),
        EmBuildStep(
            mari,
            "mari-gateway-net-nrf5340dk.emProject",
            "03app_gateway_net",
            exe("app/03app_gateway_net", "nrf5340-net", "03app_gateway_net"),
        ),
    ]


def run_embuild(
    step: EmBuildStep, config: str, *, rebuild: bool = False, verbose: bool = False
) -> float:
    """Run emBuild for one step; return elapsed seconds."""
    segger = _fw_helpers.resolve_segger_dir()
    embuild = segger / "bin" / "emBuild"
    if not embuild.is_file():
        raise click.ClickException(
            f"emBuild not found at {embuild}. Check that SEGGER_DIR points "
            f"at a real SEGGER Embedded Studio install."
        )
    cmd = [str(embuild), step.emproject, "-project", step.project, "-config", config]
    if rebuild:
        cmd.append("-rebuild")
    if verbose:
        cmd += ["-verbose", "-echo"]
        click.echo(f"$ (cd {step.cwd} && {' '.join(cmd)})", err=True)
    else:
        click.echo(f"  building {step.project} ({step.emproject})", err=True)
    t0 = time.perf_counter()
    rc = subprocess.call(
        cmd,
        cwd=step.cwd,
        stdout=None if verbose else subprocess.DEVNULL,
    )
    elapsed = time.perf_counter() - t0
    if rc != 0:
        raise click.ClickException(
            f"emBuild {step.project} exited {rc} after {elapsed:.1f}s "
            "(rerun with -v for the compiler output)."
        )
    return elapsed


def build_swarmit(
    board: str, config: str, *, rebuild: bool = False, verbose: bool = False
) -> list[Path]:
    """Build the swarmit set for `board`; return the produced files."""
    repo = _fw_helpers.resolve_swarmit_repo()
    steps = swarmit_steps(repo, board, config)
    for step in steps:
        if not (step.cwd / step.emproject).is_file():
            hint = ""
            if step.cwd != repo:
                hint = " (is the mari submodule checked out? `git submodule update --init`)"
            raise click.ClickException(f"{step.cwd / step.emproject} not found{hint}.")
    for step in steps:
        run_embuild(step, config, rebuild=rebuild, verbose=verbose)
    return [step.cwd / step.output for step in steps]


# --- dotbot-firmware -------------------------------------------------------


def build_target_for(board: str, flavor: str) -> str:
    return f"sandbox-{board}" if flavor == "sandbox" else board


def flavor_supports(board: str, flavor: str) -> bool:
    boards = (
        _fw_helpers.SANDBOX_BOARDS if flavor == "sandbox" else _fw_helpers.BARE_TARGETS
    )
    return board in boards


def default_apps(build_target: str) -> list[str]:
    """The release set for `build_target`, without `LEGACY_APPS`.

    Falls back to every buildable app when the Makefile names no release
    set for the target.
    """
    apps = _fw_helpers.list_release_projects(build_target)
    if not apps:
        apps = _fw_helpers.list_projects(build_target)
    return [app for app in apps if app not in LEGACY_APPS]


def dotbot_firmware_plan(
    board: str, flavors: Iterable[str], app: Optional[str] = None
) -> list[tuple[str, list[str]]]:
    """(BUILD_TARGET, apps) pairs to build for `board` across `flavors`.

    With `app`, each flavor that has the app builds just it; it is an error
    when no requested flavor has it.
    """
    plan: list[tuple[str, list[str]]] = []
    for flavor in flavors:
        target = build_target_for(board, flavor)
        if app is None:
            apps = default_apps(target)
        else:
            apps = [app] if app in _fw_helpers.list_projects(target) else []
        if apps:
            plan.append((target, apps))
    if app is not None and not plan:
        raise click.ClickException(
            f"App {app!r} is not available for {board!r} "
            f"({' or '.join(flavors)})."
        )
    return plan


def build_dotbot_firmware(
    plan: list[tuple[str, list[str]]],
    config: str,
    *,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build every (target, apps) pair; return the produced files."""
    produced: list[Path] = []
    for target, apps in plan:
        click.echo(f"  building {target}: {' '.join(apps)}", err=True)
        _fw_helpers.run_make(
            target, config, rebuild=rebuild, quiet=not verbose, make_targets=apps
        )
        produced += [_fw_helpers.artifact_path(target, app, config) for app in apps]
    return produced


def dotbot_firmware_outputs(
    plan: list[tuple[str, list[str]]], config: str
) -> list[Path]:
    """The files `build_dotbot_firmware(plan, config)` produces."""
    return [
        _fw_helpers.artifact_path(target, app, config)
        for target, apps in plan
        for app in apps
    ]


# --- collection --------------------------------------------------------------


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
