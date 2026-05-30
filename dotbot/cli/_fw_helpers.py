# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for the `dotbot fw` build commands (bare + --sandbox).

`dotbot fw build/clean/targets/artifacts` shell out to the same
`DotBot-firmware` Makefile, which discriminates bare vs sandbox by
`BUILD_TARGET` prefix (`sandbox-*` routes to `apps-sandbox/`, everything
else to `apps/`). Sandbox is the `--sandbox` flavor flag on those
commands (not a separate namespace). The helpers here keep target
validation, SEGGER_DIR resolution, and the make invocation contract in
one place.

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
- firmware repo: `DOTBOT_FIRMWARE_REPO` env var → `<cwd>/DotBot-firmware/`.
  Deliberately minimal — no parent walk-up, no `repos/` heuristics, no
  config-file precedence. Either you `cd` to where your clone is, or
  you point at it explicitly.
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
        raise click.ClickException(f"Failed to parse {_CONFIG_PATH}: {exc}") from exc


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


def resolve_firmware_repo() -> Path:
    """DOTBOT_FIRMWARE_REPO env → ./DotBot-firmware/ → error.

    Deliberately minimal — no parent walk-up, no `repos/` heuristics,
    no config-file precedence. Either the env var points somewhere
    valid, or the user `cd`'d to the directory that contains a
    sibling `DotBot-firmware/` clone.
    """
    env = os.environ.get("DOTBOT_FIRMWARE_REPO")
    if env:
        candidate = Path(env)
        if (candidate / "Makefile").is_file():
            return candidate
        raise click.ClickException(
            f"DOTBOT_FIRMWARE_REPO={env!r} does not contain a Makefile."
        )
    candidate = Path.cwd() / "DotBot-firmware"
    if (candidate / "Makefile").is_file():
        return candidate
    raise click.ClickException(
        "Could not locate DotBot-firmware. Either:\n"
        "  - `cd` to the directory containing your DotBot-firmware clone, or\n"
        "  - export DOTBOT_FIRMWARE_REPO=/path/to/DotBot-firmware"
    )


def suggest_close_match(name: str, candidates: Iterable[str]) -> str:
    """One-shot 'did you mean X?' suggestion, or empty string if none close."""
    close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.6)
    return f" Did you mean {close[0]!r}?" if close else ""


def validate_bare_target(target: str) -> None:
    if target.startswith("sandbox-"):
        raise click.ClickException(
            f"{target!r} is a sandbox target. Use "
            f"`dotbot fw build -t {target[len('sandbox-'):]} --sandbox` instead."
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
            f"Run `dotbot fw targets --sandbox` to list valid sandbox boards."
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
    cmd.append(f"BUILD_MODE={'-rebuild' if rebuild else ''}")
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
    and the suffix on the file name. The `.emProject` solution files set
    that macro to match the make-level `BUILD_TARGET` exactly (bare
    `dotbot-v3` → `BuildTarget=dotbot-v3`, sandbox `sandbox-dotbot-v3` →
    `BuildTarget=sandbox-dotbot-v3`), so the on-disk path mirrors what
    the Makefile's `ARTIFACT_BASE` formula expects.
    """
    is_sandbox = target.startswith("sandbox-")
    apps_dir = "apps-sandbox" if is_sandbox else "apps"
    ext = "bin" if is_sandbox else "hex"
    repo = resolve_firmware_repo()
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
