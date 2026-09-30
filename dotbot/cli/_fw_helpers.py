# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for the `dotbot fw` build commands.

`dotbot fw build/clean/targets` shell out to the `DotBot-firmware` Makefile,
which discriminates bare vs sandboxed apps by `BUILD_TARGET` prefix
(`sandbox-*` routes to `apps-sandbox/`, everything else to `apps/`). A board
that has a sandbox builds sandboxed apps unless `--bare` is given. The helpers
here keep target validation, SEGGER_DIR resolution, and the make invocation
contract in one place.

## Configuration

`SEGGER_DIR` can be persisted in `~/.dotbot/config.toml` so it doesn't
have to ride in every shell:

```toml
[fw]
segger_dir = "/Applications/SEGGER/SEGGER Embedded Studio 8.30"
```

Resolution order (first match wins):
- SEGGER: `SEGGER_DIR` env var → `[fw].segger_dir` in config → glob
  `/Applications/SEGGER/SEGGER Embedded Studio*` on macOS.
- source folders (`resolve_repo`): `DOTBOT_FW_SOURCES_<SOURCE>` (e.g.
  `DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE`) → the `[fw.sources]` table, keyed
  `dotbot-firmware` / `swarmit` / `mari`, a relative value resolving against
  the directory of the config file that set it → `repos/<name>` next to the
  config file in use → error.
"""

import difflib
import glob
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import click

from dotbot.firmware.boards import BOARDS

# Glob used to discover SES installs on macOS. Picks the lexicographically
# largest match (e.g. "Studio 8.30" beats "Studio 8.22a"), which is good
# enough as a fallback when the user hasn't set SEGGER_DIR or written
# `[fw].segger_dir` in their dotbot config.
_SEGGER_MACOS_GLOB = "/Applications/SEGGER/SEGGER Embedded Studio*"

# BUILD_TARGET / flashable board names. Single source of truth is the board
# table in `dotbot.firmware.boards` (which also carries each board's nrfjprog
# family + core) — so a valid build target and a flashable board can't drift
# apart. An unrecognized target falls through to the Makefile's catch-all
# `find apps/` rule (opaque SES errors), so we validate up-front.
BARE_TARGETS = frozenset(BOARDS)

# BUILD_TARGET = "sandbox-" + BOARD for the sandbox path. Boards
# supported by the SES `.emProject` files at the DotBot-firmware root.
SANDBOX_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})
# Every name `-t` takes: `nrf5340dk` has only a sandbox target (its bare
# targets are per core).
BOARD_NAMES = BARE_TARGETS | SANDBOX_BOARDS

# Valid `BUILD_CONFIG` values.
CONFIGS = ("Debug", "Release")
# The swarmit release ships Debug images, the Mari gateway included;
# DotBot-firmware releases ship Release.
DEFAULT_CONFIGS = {"swarmit": "Debug", "mari": "Debug", "dotbot-firmware": "Release"}
DEFAULT_BOARD = "dotbot-v3"


def _loaded_config():
    """The resolved unified config and the file it came from.

    Uses the config the root `dotbot` group already resolved onto the Click
    context when one is active (so `-c`, the cwd `dotbot.toml`, the
    `~/.dotbot/config.toml` fallback, and flag precedence all apply); for
    direct (non-CLI) calls it discovers and loads the config fresh.
    """
    ctx = click.get_current_context(silent=True)
    obj = ctx.obj if (ctx is not None and isinstance(ctx.obj, dict)) else None
    if obj is not None and obj.get("config") is not None:
        return obj["config"], obj.get("config_path")
    from dotbot import config as _config

    try:
        return _config.load_discovered()
    except _config.ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _config_fw_value(key: str) -> Optional[str]:
    """Read `[fw].<key>` from the resolved unified config, or None."""
    cfg, _ = _loaded_config()
    val = getattr(cfg.fw, key, None)
    return str(val) if val else None


def _glob_macos_segger() -> Optional[Path]:
    """Pick the lexicographically-latest SES install matching the glob.

    Returns None if no match has a usable `bin/emBuild`. The sort order
    favours newer versions (e.g. `8.30` > `8.22a`) for typical SES
    version strings.
    """
    if sys.platform != "darwin":
        return None
    matches = sorted(glob.glob(_SEGGER_MACOS_GLOB))
    for match in reversed(matches):
        candidate = Path(match)
        if (candidate / "bin" / "emBuild").is_file():
            return candidate
    return None


def resolve_segger_dir() -> Path:
    """SEGGER_DIR env → config → macOS glob → error."""
    env = os.environ.get("SEGGER_DIR")
    if env:
        return Path(env)
    cfg = _config_fw_value("segger_dir")
    if cfg:
        return Path(cfg)
    macos = _glob_macos_segger()
    if macos:
        return macos
    raise click.ClickException(
        "Building firmware from source needs SEGGER Embedded Studio (SES), "
        "which wasn't found.\n"
        "  • Export SEGGER_DIR, or add to ~/.dotbot/config.toml:\n"
        "      [fw]\n"
        '      segger_dir = "/path/to/SEGGER Embedded Studio X.YY"\n'
        "  • You do NOT need SES to run firmware: `dotbot fw fetch -f <version>` "
        "downloads pre-built release binaries and `dotbot device flash` flashes "
        "them.\n"
        "(A license-free CMake/GCC build path is planned; until then, building "
        "from source needs SES.)"
    )


def require_embuild() -> Path:
    """The SES install to build with; raise unless it has `bin/emBuild`."""
    segger = resolve_segger_dir()
    embuild = segger / "bin" / "emBuild"
    if not embuild.is_file():
        raise click.ClickException(
            f"emBuild not found at {embuild}. Check that SEGGER_DIR points "
            f"at a real SEGGER Embedded Studio install."
        )
    return segger


@dataclass(frozen=True)
class RepoSpec:
    """How one source folder is located: its `[fw.sources]` key, default dir.

    `marker` is the file, relative to the folder, that identifies it.
    """

    key: str
    dirname: str
    marker: str = "Makefile"

    @property
    def env_var(self) -> str:
        return "DOTBOT_FW_SOURCES_" + self.key.upper().replace("-", "_")

    @property
    def setting(self) -> str:
        return f"[fw.sources] {self.key}"


FIRMWARE_REPO = RepoSpec("dotbot-firmware", "DotBot-firmware")
SWARMIT_REPO = RepoSpec("swarmit", "swarmit")
MARI_REPO = RepoSpec("mari", "mari", "firmware/Makefile")
REPO_SPECS = {spec.key: spec for spec in (FIRMWARE_REPO, SWARMIT_REPO, MARI_REPO)}


def resolve_repo(spec: RepoSpec) -> Path:
    """Locate a source folder (a directory holding `spec.marker`).

    env var → `[fw.sources]` (relative to the config file's directory) →
    `repos/<dirname>` next to the config file in use → error. The folder
    returned is absolute.
    """
    env = os.environ.get(spec.env_var)
    if env:
        candidate = Path(env).expanduser().absolute()
        if (candidate / spec.marker).is_file():
            return candidate
        raise click.ClickException(
            f"{spec.env_var}={env!r} does not contain {spec.marker}."
        )
    cfg, cfg_path = _loaded_config()
    base = Path(cfg_path).resolve().parent if cfg_path is not None else None
    value = getattr(cfg.fw.sources, spec.key.replace("-", "_"), None)
    if value:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() and base is not None:
            candidate = base / candidate
        candidate = candidate.absolute()
        if (candidate / spec.marker).is_file():
            return candidate
        where = f" (set in {cfg_path})" if cfg_path is not None else ""
        raise click.ClickException(
            f"{spec.setting} = {value!r}{where} resolves to {candidate}, "
            f"which does not contain {spec.marker}."
        )
    if base is not None:
        candidate = base / "repos" / spec.dirname
        if (candidate / spec.marker).is_file():
            return candidate
        looked = f"{candidate} (next to {cfg_path}) has no {spec.marker}"
    else:
        looked = "no dotbot.toml is in use, so there is no repos/ to look in"
    raise click.ClickException(
        f"Could not find your {spec.dirname} source folder: {looked}. Either:\n"
        f"  - set {spec.key} under [fw.sources] in your config (a relative "
        "path resolves against the config file's directory), or\n"
        f"  - export {spec.env_var}=/path/to/{spec.dirname}, or\n"
        f"  - keep the clone at repos/{spec.dirname} next to your dotbot.toml."
    )


def resolve_firmware_repo() -> Path:
    """The DotBot-firmware source folder (see `resolve_repo`)."""
    return resolve_repo(FIRMWARE_REPO)


def resolve_swarmit_repo() -> Path:
    """The swarmit source folder (see `resolve_repo`)."""
    return resolve_repo(SWARMIT_REPO)


def resolve_mari_repo() -> Path:
    """The mari source folder (see `resolve_repo`)."""
    return resolve_repo(MARI_REPO)


def suggest_close_match(name: str, candidates: Iterable[str]) -> str:
    """One-shot 'did you mean X?' suggestion, or empty string if none close."""
    close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.6)
    return f" Did you mean {close[0]!r}?" if close else ""


def has_sandbox(board: str) -> bool:
    return board in SANDBOX_BOARDS


def build_target(board: str, bare: bool) -> str:
    """The make BUILD_TARGET for `board`: sandboxed apps where it has a sandbox."""
    if board.startswith("sandbox-"):
        raise click.ClickException(
            f"Pass the board name alone, -t {board[len('sandbox-'):]}: sandboxed "
            "apps are the default on boards that have a sandbox (--bare for "
            "bare-metal apps)."
        )
    if board not in BOARD_NAMES:
        hint = suggest_close_match(board, BOARD_NAMES)
        raise click.ClickException(
            f"Unknown board {board!r}.{hint}\n"
            "Run `dotbot fw targets` to list the boards."
        )
    if bare and board not in BARE_TARGETS:
        raise click.ClickException(
            f"{board!r} has sandboxed apps only; its bare-metal targets are "
            f"{', '.join(sorted(t for t in BARE_TARGETS if t.startswith(board)))}."
        )
    return board if bare or not has_sandbox(board) else f"sandbox-{board}"


def app_image_name(app: str, board: str, bare: bool) -> str:
    """The release file name of `app` for `board` (a sandboxed `.bin` or a `.hex`)."""
    target = build_target(board, bare)
    ext = "bin" if target.startswith("sandbox-") else "hex"
    return f"{app}-{target}.{ext}"


def _make_env(segger_dir: Path) -> dict:
    env = dict(os.environ)
    env["SEGGER_DIR"] = str(segger_dir)
    return env


def list_projects(target: str, repo: Optional[Path] = None) -> list[str]:
    """Return the post-filter project list for `target` via `make list-projects`."""
    repo = repo or resolve_firmware_repo()
    segger = resolve_segger_dir()
    result = subprocess.run(
        ["make", "-s", "list-projects", f"BUILD_TARGET={target}"],
        cwd=repo,
        env=_make_env(segger),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise click.ClickException(
            f"`make list-projects BUILD_TARGET={target}` failed:\n{result.stderr}"
        )
    # The Makefile recipe prints an ANSI-styled header line we want to skip;
    # take only lines that look like bare project identifiers.
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
        and not line.strip().startswith(("\x1b", "\\e["))
        and "Available projects" not in line
    ]


def list_release_projects(target: str, repo: Optional[Path] = None) -> list[str]:
    """The apps a DotBot-firmware release ships for `target`.

    Read from the Makefile's `ARTIFACT_PROJECTS`, the list its own
    `artifacts` target (and so the release workflow) builds. The rule that
    prints it comes in on stdin (`-f -`), which make 3.81 (macOS) accepts,
    unlike `--eval`.
    """
    repo = repo or resolve_firmware_repo()
    result = subprocess.run(
        [
            "make",
            "-s",
            "-f",
            "Makefile",
            "-f",
            "-",
            f"BUILD_TARGET={target}",
            "print-release-projects",
        ],
        input="print-release-projects: ; @echo $(ARTIFACT_PROJECTS)\n",
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise click.ClickException(
            f"Reading ARTIFACT_PROJECTS for BUILD_TARGET={target} failed:\n"
            f"{result.stderr}"
        )
    return result.stdout.split()


def run_make(
    target: str,
    config: str,
    project: Optional[str] = None,
    *,
    rebuild: bool = False,
    quiet: bool = True,
    make_targets: Optional[list[str]] = None,
    variables: Optional[dict[str, str]] = None,
    repo: Optional[Path] = None,
) -> float:
    """Invoke `make BUILD_TARGET=... BUILD_CONFIG=... [project|make_target]`.

    rebuild=False passes an empty `BUILD_MODE=` to make so the
    `emBuild` recipe runs with no action flag — emBuild defaults to
    incremental builds in that case. rebuild=True passes
    `BUILD_MODE=-rebuild` to force full rebuilds. Requires the
    `BUILD_MODE` knob added in DotBot-firmware Makefile (commit
    "makefile: parameterize emBuild -rebuild via BUILD_MODE knob").

    quiet=True passes `QUIET=1` so the Makefile suppresses SES's
    `-verbose -echo` flood; the per-project "Building project X" /
    "Done" banners still come through. quiet=False also echoes the full
    make command line to stderr so the user has a copy-pasteable line
    to reproduce outside the CLI.

    If `make_targets` is given, those are the make-level targets passed
    on the command line (e.g. `["clean"]`, `["artifacts"]`). Otherwise
    `project` is appended (or nothing, which means default `all` →
    every project for the BUILD_TARGET). `variables` are passed as
    `NAME=value` and override the Makefile's own assignments.

    Returns elapsed wall-clock seconds. Raises `ClickException` on
    non-zero exit so callers can short-circuit.
    """
    repo = repo or resolve_firmware_repo()
    segger = require_embuild()
    cmd = ["make", f"BUILD_TARGET={target}", f"BUILD_CONFIG={config}"]
    if quiet:
        cmd.append("QUIET=1")
    cmd.append(f"BUILD_MODE={'-rebuild' if rebuild else ''}")
    cmd.extend(f"{name}={value}" for name, value in (variables or {}).items())
    if make_targets:
        cmd.extend(make_targets)
    elif project:
        cmd.append(project)
    if not quiet:
        # Verbose mode: print the make command so the user can copy/paste
        # it to reproduce outside the CLI.
        click.echo(f"$ {shlex.join(cmd)}", err=True)
    t0 = time.perf_counter()
    rc = subprocess.call(cmd, cwd=repo, env=_make_env(segger))
    elapsed = time.perf_counter() - t0
    if rc != 0:
        raise click.ClickException(f"`make` exited {rc} after {elapsed:.1f}s.")
    return elapsed


def artifact_path(
    target: str, project: str, config: str, repo: Optional[Path] = None
) -> Path:
    """Return where SES writes the artifact for (target, project, config).

    SES uses its internal `$(BuildTarget)` macro for the Output directory
    and the suffix on the file name. The `.emProject` solution files set
    that macro to match the make-level `BUILD_TARGET` exactly (bare
    `dotbot-v3` → `BuildTarget=dotbot-v3`, sandbox `sandbox-dotbot-v3` →
    `BuildTarget=sandbox-dotbot-v3`), so the on-disk path mirrors what
    the Makefile's `ARTIFACT_BASE` formula expects.
    """
    is_sandbox = target.startswith("sandbox-")
    apps_dir = "apps-sandbox" if is_sandbox else "apps"
    ext = "bin" if is_sandbox else "hex"
    repo = repo or resolve_firmware_repo()
    return (
        repo
        / apps_dir
        / project
        / "Output"
        / target
        / config
        / "Exe"
        / f"{project}-{target}.{ext}"
    )
