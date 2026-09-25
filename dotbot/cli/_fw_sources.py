# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Build the firmware set a release ships, from local checkouts.

Two sources, matching the two GitHub release sources `dotbot fw fetch`
downloads from:

- `dotbot-firmware`: sandboxed apps (`.bin`) or bare apps (`.hex`), built
  through the DotBot-firmware Makefile.
- `swarmit`: the bootloader for one board, the network core, and the Mari
  gateway (app + net cores) from swarmit's pinned `mari` submodule, built by
  calling emBuild on each `.emProject` directly (the swarmit Makefiles always
  pass `-rebuild`).

SES names every output `<project>-<BuildTarget>.<ext>`, which is also the
release asset name, so collecting is a flat copy into the set directory
`<artifacts>/<source>-<name>/`, next to a `manifest.json`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import click

from dotbot.cli import _fw_helpers

SOURCES = ("dotbot-firmware", "swarmit")

# Apps left out of the default set even when a release still ships them.
# `-a <app>` builds them explicitly.
LEGACY_APPS = frozenset({"lh2_calibration"})

# Boards with a `swarmit-bootloader-<board>.emProject` that a release ships.
SWARMIT_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})

# What `-a` selects inside the swarmit set; `gateway` is both gateway images.
SWARMIT_PARTS = ("bootloader", "netcore", "gateway")


@dataclass(frozen=True)
class EmBuildStep:
    """One emBuild invocation and the file it produces, relative to `cwd`."""

    cwd: Path
    emproject: str
    project: str
    output: Path


def set_dir(source: str, name: str, artifacts_root: Path) -> Path:
    """Where a source's locally built set `name` is collected."""
    return artifacts_root / f"{source}-{name}"


# --- swarmit ---------------------------------------------------------------


def swarmit_steps(
    repo: Path, board: str, config: str, parts: Optional[Iterable[str]] = None
) -> list[EmBuildStep]:
    """The emBuild steps for the swarmit release set of one board.

    `parts` narrows the set to some of `SWARMIT_PARTS`; the board only
    matters for the bootloader.
    """
    parts = set(parts or SWARMIT_PARTS)
    unknown = parts - set(SWARMIT_PARTS)
    if unknown:
        raise click.ClickException(
            f"swarmit has no part {', '.join(sorted(unknown))}. "
            f"Parts: {', '.join(SWARMIT_PARTS)}."
        )
    if "bootloader" in parts and board not in SWARMIT_BOARDS:
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

    steps = []
    if "bootloader" in parts:
        steps.append(
            EmBuildStep(
                repo,
                f"swarmit-bootloader-{board}.emProject",
                "bootloader",
                exe("device/bootloader", board, "bootloader"),
            )
        )
    if "netcore" in parts:
        steps.append(
            EmBuildStep(
                repo,
                "swarmit-netcore.emProject",
                "netcore",
                exe("device/network_core", "nrf5340-net", "netcore"),
            )
        )
    if "gateway" in parts:
        steps += [
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
    return steps


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
    board: str,
    config: str,
    *,
    parts: Optional[Iterable[str]] = None,
    repo: Optional[Path] = None,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build the swarmit set (or `parts` of it) for `board`; return the files."""
    repo = repo or _fw_helpers.resolve_swarmit_repo()
    steps = swarmit_steps(repo, board, config, parts)
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


def default_apps(build_target: str, repo: Optional[Path] = None) -> list[str]:
    """The release set for `build_target`, without `LEGACY_APPS`.

    Falls back to every buildable app when the Makefile names no release
    set for the target.
    """
    apps = _fw_helpers.list_release_projects(build_target, repo)
    if not apps:
        apps = _fw_helpers.list_projects(build_target, repo)
    return [app for app in apps if app not in LEGACY_APPS]


def dotbot_firmware_apps(
    target: str, apps: Optional[list[str]] = None, repo: Optional[Path] = None
) -> list[str]:
    """The apps to build for `target`: `apps`, checked, or the release set."""
    if not apps:
        return default_apps(target, repo)
    available = _fw_helpers.list_projects(target, repo)
    unknown = [app for app in apps if app not in available]
    if unknown:
        raise click.ClickException(
            f"No {', '.join(repr(a) for a in unknown)} app for {target}.\n"
            f"Available: {', '.join(available)}"
        )
    return list(apps)


def build_dotbot_firmware(
    target: str,
    apps: list[str],
    config: str,
    *,
    repo: Optional[Path] = None,
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
        repo=repo,
    )
    return dotbot_firmware_outputs(target, apps, config, repo)


def dotbot_firmware_outputs(
    target: str, apps: list[str], config: str, repo: Optional[Path] = None
) -> list[Path]:
    """The files `build_dotbot_firmware(target, apps, config)` produces."""
    return [_fw_helpers.artifact_path(target, app, config, repo) for app in apps]


# --- which source builds what ------------------------------------------------


def route_apps(
    apps: Iterable[str],
    sources: Iterable[str],
    dotbot_firmware_names: Callable[[], Iterable[str]],
) -> dict[str, list[str]]:
    """Assign each `-a` name to the one source in `sources` that has it.

    `dotbot_firmware_names()` lists the dotbot-firmware apps; it is only
    called when dotbot-firmware is a candidate for more than a single source.
    """
    sources = list(sources)
    routed: dict[str, list[str]] = {}
    if len(sources) == 1:
        routed[sources[0]] = list(apps)
        return routed
    df_names: Optional[set[str]] = None
    for app in apps:
        owners = []
        if "swarmit" in sources and app in SWARMIT_PARTS:
            owners.append("swarmit")
        if "dotbot-firmware" in sources:
            if df_names is None:
                df_names = set(dotbot_firmware_names())
            if app in df_names:
                owners.append("dotbot-firmware")
        if len(owners) > 1:
            raise click.ClickException(
                f"-a {app} is both a swarmit part and a dotbot-firmware app; "
                f"name the source: `dotbot fw build swarmit -a {app}` or "
                f"`dotbot fw build dotbot-firmware -a {app}`."
            )
        if not owners:
            raise click.ClickException(
                f"No source has -a {app!r}. swarmit parts: "
                f"{', '.join(SWARMIT_PARTS)}; dotbot-firmware apps: "
                f"{', '.join(sorted(df_names or ())) or '(none found)'}."
            )
        routed.setdefault(owners[0], []).append(app)
    return routed


# --- collection --------------------------------------------------------------


def _git(repo: Path, *args: str) -> Optional[str]:
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


def git_state(repo: Path) -> tuple[Optional[str], Optional[bool]]:
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
    the set, so one rebuilt with `-a` sits next to older ones, each carrying
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
