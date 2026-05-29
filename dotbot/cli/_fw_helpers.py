# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for `dotbot fw` (bare) and `dotbot swarm fw` (sandbox).

Both subcommands shell out to the same `DotBot-firmware` Makefile,
which discriminates bare vs sandbox by `BUILD_TARGET` prefix
(`sandbox-*` routes to `apps-sandbox/`, everything else to `apps/`).
The wrappers in `dotbot/cli/fw.py` (bare) and `dotbot/cli/_sandbox_fw.py`
(sandbox) reuse the helpers here so target validation, SEGGER_DIR
resolution, and the make invocation contract stay in one place.

## Configuration

`SEGGER_DIR` and the path to the DotBot-firmware checkout can be set
in `~/.dotbot/config.toml` so they don't need to be passed via env
on every shell:

```toml
[fw]
segger_dir = "/Applications/SEGGER/SEGGER Embedded Studio 8.30"
firmware_repo = "/Users/me/Developer/dotbot-testbed/repos/DotBot-firmware"
```

Resolution order (first match wins):
- `SEGGER_DIR` env var ↦ `[fw].segger_dir` in config ↦ glob
  `/Applications/SEGGER/SEGGER Embedded Studio*` on macOS (latest
  sort-order pick).
- `DOTBOT_FIRMWARE_REPO` env var ↦ `[fw].firmware_repo` in config ↦
  walk up from CWD looking for `repos/DotBot-firmware/Makefile`.
"""

import difflib
import glob
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import click
import toml

# Glob used to discover SES installs on macOS. Picks the lexicographically
# largest match (e.g. "Studio 8.30" beats "Studio 8.22a"), which is good
# enough as a fallback when the user hasn't set SEGGER_DIR or written
# `[fw].segger_dir` in `~/.dotbot/config.toml`.
_SEGGER_MACOS_GLOB = "/Applications/SEGGER/SEGGER Embedded Studio*"

# Per-user persistent config — shares the `~/.dotbot/` directory the
# controller / calibration already use (see dotbot/controller.py's
# CALIBRATION_PATH).
_CONFIG_PATH = Path.home() / ".dotbot" / "config.toml"

# BUILD_TARGET values handled by DotBot-firmware's Makefile (bare path).
# Mirrors the explicit branches in the Makefile; an unrecognized target
# falls through to the catch-all `find apps/` rule which produces opaque
# SES errors, so we validate up-front.
BARE_TARGETS = frozenset(
    {
        "dotbot-v1",
        "dotbot-v2",
        "dotbot-v3",
        "nrf52833dk",
        "nrf52840dk",
        "nrf5340dk-app",
        "nrf5340dk-net",
        "sailbot-v1",
        "freebot-v1.0",
        "lh2-mini-mote",
        "xgo-v1",
        "xgo-v2",
    }
)

# BUILD_TARGET = "sandbox-" + BOARD for the sandbox path. Boards
# supported by the SES `.emProject` files at the DotBot-firmware root.
SANDBOX_BOARDS = frozenset({"dotbot-v2", "dotbot-v3", "nrf5340dk"})

# Valid `BUILD_CONFIG` values.
CONFIGS = ("Debug", "Release")
DEFAULT_CONFIG = "Release"
DEFAULT_BARE_TARGET = "dotbot-v3"
DEFAULT_SANDBOX_BOARD = "dotbot-v3"


def load_config() -> dict:
    """Read `~/.dotbot/config.toml`. Empty dict if missing.

    Raises ClickException with the file path if the TOML is malformed,
    so the user knows where to fix.
    """
    if not _CONFIG_PATH.is_file():
        return {}
    try:
        return toml.load(_CONFIG_PATH)
    except toml.TomlDecodeError as exc:
        raise click.ClickException(
            f"Failed to parse {_CONFIG_PATH}: {exc}"
        ) from exc


def _config_fw_value(key: str) -> Optional[str]:
    """Read `[fw].<key>` from `~/.dotbot/config.toml`, or None."""
    fw_section = load_config().get("fw") or {}
    val = fw_section.get(key)
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
        "SEGGER_DIR is not set and no SEGGER install was found.\n"
        "Either export SEGGER_DIR, or add to ~/.dotbot/config.toml:\n"
        "  [fw]\n"
        '  segger_dir = "/path/to/SEGGER Embedded Studio X.YY"'
    )


def resolve_firmware_repo() -> Path:
    """DOTBOT_FIRMWARE_REPO env → config → workspace walk-up → error."""
    env = os.environ.get("DOTBOT_FIRMWARE_REPO")
    if env:
        candidate = Path(env)
        if (candidate / "Makefile").is_file():
            return candidate
        raise click.ClickException(
            f"DOTBOT_FIRMWARE_REPO={env!r} does not contain a Makefile."
        )
    cfg = _config_fw_value("firmware_repo")
    if cfg:
        candidate = Path(cfg)
        if (candidate / "Makefile").is_file():
            return candidate
        raise click.ClickException(
            f"[fw].firmware_repo={cfg!r} in {_CONFIG_PATH} does not contain "
            f"a Makefile."
        )
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "repos" / "DotBot-firmware"
        if (candidate / "Makefile").is_file():
            return candidate
    raise click.ClickException(
        "Could not locate DotBot-firmware.\n"
        "Either run from inside a workspace that has "
        "`repos/DotBot-firmware`, export DOTBOT_FIRMWARE_REPO, or add to "
        "~/.dotbot/config.toml:\n"
        "  [fw]\n"
        '  firmware_repo = "/path/to/DotBot-firmware"'
    )


def suggest_close_match(name: str, candidates: Iterable[str]) -> str:
    """One-shot 'did you mean X?' suggestion, or empty string if none close."""
    close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.6)
    return f" Did you mean {close[0]!r}?" if close else ""


def validate_bare_target(target: str) -> None:
    if target.startswith("sandbox-"):
        raise click.ClickException(
            f"{target!r} is a sandbox target. Use "
            f"`dotbot swarm fw build {target[len('sandbox-'):]}` instead."
        )
    if target not in BARE_TARGETS:
        hint = suggest_close_match(target, BARE_TARGETS)
        raise click.ClickException(
            f"Unknown bare target {target!r}.{hint}\n"
            f"Run `dotbot fw targets` to list valid bare targets."
        )


def validate_sandbox_board(board: str) -> None:
    if board.startswith("sandbox-"):
        raise click.ClickException(
            f"Drop the `sandbox-` prefix — pass just the board name: "
            f"{board[len('sandbox-'):]!r}."
        )
    if board not in SANDBOX_BOARDS:
        hint = suggest_close_match(board, SANDBOX_BOARDS)
        raise click.ClickException(
            f"Unknown sandbox board {board!r}.{hint}\n"
            f"Run `dotbot swarm fw targets` to list valid sandbox boards."
        )


def _make_env(segger_dir: Path) -> dict:
    env = dict(os.environ)
    env["SEGGER_DIR"] = str(segger_dir)
    return env


def list_projects(target: str) -> list[str]:
    """Return the post-filter project list for `target` via `make list-projects`."""
    repo = resolve_firmware_repo()
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


def run_make(
    target: str,
    config: str,
    project: Optional[str] = None,
    *,
    rebuild: bool = False,
    quiet: bool = True,
    make_targets: Optional[list[str]] = None,
) -> float:
    """Invoke `make BUILD_TARGET=... BUILD_CONFIG=... [project|make_target]`.

    rebuild=False asks the Makefile to use `-build` (incremental, fast);
    rebuild=True restores the prior `-rebuild` behavior. Requires the
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
    every project for the BUILD_TARGET).

    Returns elapsed wall-clock seconds. Raises `ClickException` on
    non-zero exit so callers can short-circuit.
    """
    repo = resolve_firmware_repo()
    segger = resolve_segger_dir()
    embuild = segger / "bin" / "emBuild"
    if not embuild.is_file():
        raise click.ClickException(
            f"emBuild not found at {embuild}. Check that SEGGER_DIR points "
            f"at a real SES install."
        )
    cmd = ["make", f"BUILD_TARGET={target}", f"BUILD_CONFIG={config}"]
    if quiet:
        cmd.append("QUIET=1")
    cmd.append(f"BUILD_MODE={'-rebuild' if rebuild else '-build'}")
    if make_targets:
        cmd.extend(make_targets)
    elif project:
        cmd.append(project)
    if not quiet:
        # Verbose mode: print the make command so the user can copy/paste
        # it to reproduce outside the CLI.
        click.echo(f"$ {' '.join(cmd)}", err=True)
    t0 = time.perf_counter()
    rc = subprocess.call(cmd, cwd=repo, env=_make_env(segger))
    elapsed = time.perf_counter() - t0
    if rc != 0:
        raise click.ClickException(f"`make` exited {rc} after {elapsed:.1f}s.")
    return elapsed


def artifact_path(target: str, project: str, config: str) -> Path:
    """Return where SES writes the artifact for (target, project, config).

    SES uses its internal `$(BuildTarget)` macro for the Output directory
    and the suffix on the file name. In both `dotbot-v3.emProject` and
    `sandbox-dotbot-v3.emProject` that macro is hardcoded to the board
    name (e.g. `dotbot-v3`) — the `sandbox-` prefix only affects which
    apps/ directory SES uses, not the Output path. So the on-disk path
    is `apps[-sandbox]/<app>/Output/<board>/<config>/Exe/<app>-<board>.<ext>`.

    Note: DotBot-firmware's Makefile `ARTIFACT_BASE` formula uses the
    Make-level `BUILD_TARGET` (which DOES include the `sandbox-` prefix)
    and so disagrees with SES's actual output path for sandbox targets.
    The CLI tracks the real on-disk location, not the (buggy) Makefile
    expectation.
    """
    is_sandbox = target.startswith("sandbox-")
    apps_dir = "apps-sandbox" if is_sandbox else "apps"
    ext = "bin" if is_sandbox else "hex"
    board = target[len("sandbox-") :] if is_sandbox else target
    repo = resolve_firmware_repo()
    return (
        repo
        / apps_dir
        / project
        / "Output"
        / board
        / config
        / "Exe"
        / f"{project}-{board}.{ext}"
    )
