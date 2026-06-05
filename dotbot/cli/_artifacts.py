# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared artifact-resolution + friendly-error helpers for `fw` / `device`.

Owns the user-level ``~/.dotbot/artifacts/`` cache convention, the
absolute-path echo on every cache read/write (so you always see where files
landed, regardless of the directory you ran from), the auto-resolve decision
tree used by ``dotbot device flash <app>`` (present → build → error), and
the two centralized tool-missing messages (SES for builds, nrfjprog for
device ops).

Leaf module: it imports `_fw_helpers` / `dotbot.firmware` lazily *inside*
functions, so importing it (e.g. for `device info`, which needs neither
SES nor a firmware repo) stays cheap and side-effect-free.
"""

import os
from pathlib import Path

import click

# Single source of truth for the default cache location, so changing it is a
# one-line edit. `artifacts_dir()` is the behavioral path (env-overridable, ~
# expanded, resolved); `DEFAULT_ARTIFACTS_DISPLAY` is the human-readable form
# for help text. (Docstrings and the Markdown docs can't interpolate a
# variable, so they spell the path out literally - keep them in sync by hand.)
_DEFAULT_ARTIFACTS_PARTS = (".dotbot", "artifacts")
DEFAULT_ARTIFACTS_DISPLAY = "~/" + "/".join(_DEFAULT_ARTIFACTS_PARTS)


def artifacts_dir() -> Path:
    """The firmware cache: ``~/.dotbot/artifacts/`` by default.

    User-level and shared across working directories (like other tools cache
    downloaded firmware), so you don't re-download a release per directory and
    the launch dir stays clean. Override with ``$DOTBOT_ARTIFACTS_DIR``.
    """
    override = os.environ.get("DOTBOT_ARTIFACTS_DIR")
    base = (
        Path(override) if override else Path.home().joinpath(*_DEFAULT_ARTIFACTS_PARTS)
    )
    return base.expanduser().resolve()


def echo_artifact_path(path: Path, *, action: str = "using") -> None:
    """Announce the resolved absolute artifact path on a cache read/write.

    ``action`` is a short verb ("writing", "reading", "using", ...). The
    point is that a user who ran the command from an unexpected directory
    immediately sees where files actually landed.
    """
    click.echo(f"[artifacts] {action}: {Path(path).resolve()}", err=True)


def friendly_nrfjprog_error() -> click.ClickException:
    """Message for a missing `nrfjprog`. It's an external binary (no pip)."""
    return click.ClickException(
        "`nrfjprog` (Nordic command-line tools) was not found on PATH.\n"
        "Device commands flash over the J-Link cable via nrfjprog.\n"
        "  • Install nRF Command Line Tools from "
        "https://www.nordicsemi.com/Products/Development-tools/nRF-Command-Line-Tools\n"
        "  • Or, on a fresh shell, make sure its `bin/` is on PATH."
    )


def ensure_nrfjprog() -> None:
    """Raise the friendly nrfjprog message if the tool isn't installed."""
    from dotbot.firmware.nrf import nrfjprog_available

    if not nrfjprog_available():
        raise friendly_nrfjprog_error()


def _find_in_cache(name: str) -> Path | None:
    """Find a firmware file across the source-qualified cache dirs.

    The cache holds ``<source>-<version>/`` (fetched releases) and
    ``<source>-local[-link]/`` (built/linked) subdirs. Prefer a local build
    (you're iterating on it), else the newest-versioned release dir.
    """
    root = artifacts_dir()
    if not root.is_dir():
        return None
    local_hits: list[Path] = []
    released_hits: list[Path] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        candidate = sub / name
        if candidate.is_file():
            if sub.name.endswith(("-local", "-local-link")):
                local_hits.append(candidate)
            else:
                released_hits.append(candidate)
    if local_hits:
        return local_hits[0]
    if released_hits:
        # newest by dir name (a coarse version sort; good enough for picking
        # the latest release of a given app)
        return sorted(released_hits, key=lambda p: p.parent.name, reverse=True)[0]
    return None


def resolve_app_artifact(
    app: str,
    *,
    board: str = "dotbot-v3",
    config: str = "Release",
    sandbox: bool = False,
) -> Path:
    """Auto-resolve a single app's firmware artifact for cable-flashing.

    Decision tree (npm-style): present in ``~/.dotbot/artifacts/`` → build
    from source → clear error pointing at build/fetch. An *explicit file path*
    is handled by the caller before this is reached.

    - Flat ``<app>-<board>.hex`` (bare) or ``<app>-sandbox-<board>.bin``
      (sandbox), as produced by `dotbot fw artifacts`, found across the
      cache's ``<source>-<version>/`` and ``<source>-local/`` dirs.
    - Else, if a DotBot-firmware repo is locatable, build it (needs SES)
      and use the SES output path.
    - Else, a friendly error telling the user to build or fetch first.
    """
    name = f"{app}-sandbox-{board}.bin" if sandbox else f"{app}-{board}.hex"
    cached = _find_in_cache(name)
    if cached is not None:
        echo_artifact_path(cached, action="using")
        return cached

    # Not cached → try to build from source.
    from dotbot.cli import _fw_helpers

    try:
        repo = _fw_helpers.resolve_firmware_repo()
    except click.ClickException:
        repo = None
    if repo is not None:
        target = f"sandbox-{board}" if sandbox else board
        click.echo(
            f"[artifacts] {name} not cached; building {app} for {target}...",
            err=True,
        )
        # run_make → resolve_segger_dir already raises the friendly
        # "no SES, use fetch + device flash" message when SES is absent.
        _fw_helpers.run_make(target, config, app, rebuild=False, quiet=True)
        built = _fw_helpers.artifact_path(target, app, config)
        if built.is_file():
            echo_artifact_path(built, action="built")
            return built
        raise click.ClickException(
            f"Build finished but {built} was not produced; check the app name."
        )

    raise click.ClickException(
        f"No artifact for {app!r} ({board}) in {artifacts_dir()} and no "
        "DotBot-firmware source to build from.\n"
        "  • `dotbot fw build "
        f"-a {app} -t {board}{' --sandbox' if sandbox else ''}` to build, or\n"
        "  • `dotbot fw fetch` to download the latest releases, then retry, or\n"
        "  • pass an explicit path: `dotbot device flash <path-to-.hex>`."
    )
