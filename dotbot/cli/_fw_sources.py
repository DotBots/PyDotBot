# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Build the firmware images a release ships, from local checkouts.

Three sources:

- `dotbot-firmware`: sandboxed apps (`.bin`) or bare apps (`.hex`), built
  through the DotBot-firmware Makefile.
- `swarmit`: the bootloader for one board and the network core.
- `mari`: the Mari gateway (app + net cores), `mari-gateway`, optionally one
  net-core image per TSCH schedule.

swarmit and mari are built by calling emBuild on each `.emProject` directly
(their Makefiles always pass `-rebuild`). SES names every output
`<project>-<BuildTarget>.<ext>`, which is also the release asset name, so
collecting is a flat copy into the set directory
`<artifacts>/<source>-<name>/`, next to a `manifest.json`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import click

from dotbot.cli import _fw_helpers

SOURCES = ("dotbot-firmware", "swarmit", "mari")

# Apps left out of the default set and of help text; `-a <app>` still builds
# them.
LEGACY_APPS = frozenset({"lh2_calibration"})

# Boards with a `swarmit-bootloader-<board>.emProject` that a release ships.
SWARMIT_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})

# What `-a` selects inside the swarmit and mari sources.
SWARMIT_PARTS = ("bootloader", "netcore")
MARI_PARTS = ("mari-gateway",)
PARTS = {"swarmit": SWARMIT_PARTS, "mari": MARI_PARTS}

# The board the Mari gateway images are built for.
MARI_GATEWAY_BOARD = "nrf5340dk"

# The line of `03app_gateway_net/main.c` that selects the gateway's schedule;
# keep in step with Mari's build-schedules.sh, which edits the same line.
_SCHEDULE_LINE_RE = re.compile(
    r"^(schedule_t\s+\*schedule_app\s*=\s*&)schedule_[a-z]+;", re.MULTILINE
)


@dataclass(frozen=True)
class EmBuildStep:
    """One emBuild invocation and the file it produces, relative to `cwd`.

    `schedule` names the TSCH schedule compiled into a gateway net image;
    the output is then collected as `03app_gateway_net-<schedule>.hex`.
    """

    cwd: Path
    emproject: str
    project: str
    output: Path
    schedule: str | None = None


def set_dir(source: str, name: str, artifacts_root: Path) -> Path:
    """Where a source's locally built set `name` is collected."""
    return artifacts_root / f"{source}-{name}"


def _exe(project_dir: str, build_target: str, name: str, config: str) -> Path:
    return (
        Path(project_dir)
        / "Output"
        / build_target
        / config
        / "Exe"
        / f"{name}-{build_target}.hex"
    )


def _check_parts(source: str, parts: Iterable[str] | None) -> set[str]:
    known = PARTS[source]
    parts = set(parts or known)
    unknown = parts - set(known)
    if unknown:
        raise click.ClickException(
            f"{source} has no part {', '.join(sorted(unknown))}. "
            f"Parts: {', '.join(known)}."
        )
    return parts


# --- swarmit ---------------------------------------------------------------


def swarmit_steps(
    repo: Path, board: str, config: str, parts: Iterable[str] | None = None
) -> list[EmBuildStep]:
    """The emBuild steps for the swarmit images of one board.

    `parts` narrows them to some of `SWARMIT_PARTS`; the board only matters
    for the bootloader.
    """
    parts = _check_parts("swarmit", parts)
    if "bootloader" in parts and board not in SWARMIT_BOARDS:
        raise click.ClickException(
            f"swarmit has no bootloader for board {board!r}. "
            f"Supported: {', '.join(sorted(SWARMIT_BOARDS))}."
        )
    steps = []
    if "bootloader" in parts:
        steps.append(
            EmBuildStep(
                repo,
                f"swarmit-bootloader-{board}.emProject",
                "bootloader",
                _exe("device/bootloader", board, "bootloader", config),
            )
        )
    if "netcore" in parts:
        steps.append(
            EmBuildStep(
                repo,
                "swarmit-netcore.emProject",
                "netcore",
                _exe("device/network_core", "nrf5340-net", "netcore", config),
            )
        )
    return steps


# --- mari --------------------------------------------------------------------


def mari_steps(
    repo: Path,
    config: str,
    parts: Iterable[str] | None = None,
    schedules: Iterable[str] | None = None,
) -> list[EmBuildStep]:
    """The emBuild steps for the Mari gateway images.

    Without `schedules`, the app image and the net image with the schedule
    `main.c` selects. With `schedules`, the app image and one net image per
    schedule instead.
    """
    _check_parts("mari", parts)
    fw = repo / "firmware"
    app = EmBuildStep(
        fw,
        "mari-gateway-app-nrf5340dk.emProject",
        "03app_gateway_app",
        _exe("app/03app_gateway_app", "nrf5340-app", "03app_gateway_app", config),
    )

    def net(schedule: str | None = None) -> EmBuildStep:
        return EmBuildStep(
            fw,
            "mari-gateway-net-nrf5340dk.emProject",
            "03app_gateway_net",
            _exe("app/03app_gateway_net", "nrf5340-net", "03app_gateway_net", config),
            schedule,
        )

    if not schedules:
        return [app, net()]
    return [app] + [net(schedule) for schedule in schedules]


def resolve_schedules(values: Iterable[str]) -> list[str]:
    """Expand `--schedule` values (`all` means every schedule), in ladder order."""
    from dotbot.firmware.schedules import MARI_SCHEDULES

    values = set(values)
    if "all" in values:
        return list(MARI_SCHEDULES)
    return [name for name in MARI_SCHEDULES if name in values]


def collected_name(step: EmBuildStep) -> str:
    """The file name `step`'s output is collected under."""
    from dotbot.firmware.schedules import net_image_name

    return net_image_name(step.schedule) if step.schedule else step.output.name


def select_schedule(main_c: Path, schedule: str) -> None:
    """Point the gateway's `schedule_app` at `schedule_<schedule>` in `main_c`."""
    text = main_c.read_text()
    new, count = _SCHEDULE_LINE_RE.subn(rf"\g<1>schedule_{schedule};", text)
    if count != 1:
        raise click.ClickException(
            f"Could not find the `schedule_t *schedule_app = &schedule_...;` line "
            f"in {main_c}."
        )
    main_c.write_text(new)


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
    label = step.project + (f", schedule {step.schedule}" if step.schedule else "")
    if verbose:
        cmd += ["-verbose", "-echo"]
        click.echo(f"$ (cd {step.cwd} && {' '.join(cmd)})", err=True)
    else:
        click.echo(f"  building {label} ({step.emproject})", err=True)
    t0 = time.perf_counter()
    rc = subprocess.call(
        cmd,
        cwd=step.cwd,
        stdout=None if verbose else subprocess.DEVNULL,
    )
    elapsed = time.perf_counter() - t0
    if rc != 0:
        raise click.ClickException(
            f"emBuild {label} exited {rc} after {elapsed:.1f}s "
            "(rerun with -v for the compiler output)."
        )
    return elapsed


def _check_emprojects(steps: list[EmBuildStep], hint: str = "") -> None:
    for step in steps:
        if not (step.cwd / step.emproject).is_file():
            raise click.ClickException(f"{step.cwd / step.emproject} not found{hint}.")


def run_steps(
    steps: list[EmBuildStep],
    config: str,
    *,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build `steps` in order; return each output under its collected name.

    A step with a schedule edits the gateway's `main.c` to select it, builds,
    and stages the image as `firmware/Output/schedules/<collected name>` (the
    place Mari's build-schedules.sh puts it). `main.c` is restored
    byte-for-byte afterwards, even when a build fails.
    """
    outputs: list[Path] = []
    scheduled = [step for step in steps if step.schedule]
    main_c = original = None
    if scheduled:
        main_c = scheduled[0].cwd / "app" / "03app_gateway_net" / "main.c"
        original = main_c.read_bytes()
    staged: list[Path] = []
    try:
        for step in steps:
            if step.schedule:
                select_schedule(main_c, step.schedule)
            run_embuild(step, config, rebuild=rebuild, verbose=verbose)
            built = step.cwd / step.output
            if step.schedule:
                if not built.is_file():
                    raise click.ClickException(
                        f"Build finished but {built} is missing."
                    )
                dest = step.cwd / "Output" / "schedules" / collected_name(step)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(built, dest)
                staged.append(dest)
                built = dest
            outputs.append(built)
    finally:
        if main_c is not None:
            main_c.write_bytes(original)
            # The restore makes main.c newer than the images built from it;
            # stamp them again so they do not read as stale.
            for path in staged:
                path.touch()
    return outputs


def build_swarmit(
    board: str,
    config: str,
    *,
    parts: Iterable[str] | None = None,
    repo: Path | None = None,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build the swarmit images (or `parts` of them) for `board`."""
    repo = repo or _fw_helpers.resolve_swarmit_repo()
    steps = swarmit_steps(repo, board, config, parts)
    _check_emprojects(steps)
    return run_steps(steps, config, rebuild=rebuild, verbose=verbose)


def build_mari(
    config: str,
    *,
    parts: Iterable[str] | None = None,
    schedules: Iterable[str] | None = None,
    repo: Path | None = None,
    rebuild: bool = False,
    verbose: bool = False,
) -> list[Path]:
    """Build the Mari gateway images, one net image per schedule if given."""
    repo = repo or _fw_helpers.resolve_mari_repo()
    steps = mari_steps(repo, config, parts, schedules)
    _check_emprojects(steps)
    return run_steps(steps, config, rebuild=rebuild, verbose=verbose)


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
    unknown = [app for app in apps if app not in available and app not in LEGACY_APPS]
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


# --- which source builds what ------------------------------------------------


def route_apps(
    apps: Iterable[str],
    sources: Iterable[str],
    dotbot_firmware_names: Callable[[], Iterable[str]],
) -> dict[str, list[str]]:
    """Assign each `-a` name to the one source in `sources` that has it.

    `dotbot_firmware_names()` lists the dotbot-firmware apps; it is only
    called when dotbot-firmware is a candidate among several sources.
    """
    sources = list(sources)
    routed: dict[str, list[str]] = {}
    if len(sources) == 1:
        routed[sources[0]] = list(apps)
        return routed
    df_names: set[str] | None = None
    for app in apps:
        owners = [s for s in sources if s in PARTS and app in PARTS[s]]
        if "dotbot-firmware" in sources:
            if df_names is None:
                df_names = set(dotbot_firmware_names())
            if app in df_names or app in LEGACY_APPS:
                owners.append("dotbot-firmware")
        if len(owners) > 1:
            lines = " or ".join(f"`dotbot fw build {o} -a {app}`" for o in owners)
            raise click.ClickException(
                f"-a {app} names a part of {' and '.join(owners)}; name the "
                f"source: {lines}."
            )
        if not owners:
            listed = "; ".join(
                f"{s} parts: {', '.join(PARTS[s])}" for s in sources if s in PARTS
            )
            if "dotbot-firmware" in sources:
                listed += (
                    f"; dotbot-firmware apps: "
                    f"{', '.join(sorted(df_names or ())) or '(none found)'}"
                )
            raise click.ClickException(f"No source has -a {app!r}. {listed}.")
        routed.setdefault(owners[0], []).append(app)
    return routed


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
