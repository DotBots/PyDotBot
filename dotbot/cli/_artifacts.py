# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared artifact-resolution + friendly-error helpers for `fw` / `device`.

Owns the CWD-local ``./artifacts/`` convention, the absolute-path echo on
every cache read/write (so running from a random directory never silently
touches a relative path the user didn't name), the auto-resolve decision
tree used by ``dotbot device flash <app>`` (present → build → error), and
the two centralized tool-missing messages (SES for builds, nrfjprog for
device ops).

Leaf module: it imports `_fw_helpers` / `dotbot.firmware` lazily *inside*
functions, so importing it (e.g. for `device info`, which needs neither
SES nor a firmware repo) stays cheap and side-effect-free.
"""

from pathlib import Path

import click


def artifacts_dir() -> Path:
    """The CWD-local ``./artifacts/`` directory, resolved absolute.

    The single source of truth for where build outputs land and fetched
    releases are cached. Per-workspace (no global ``~/.dotbot/fw``), so
    two checkouts never collide.
    """
    return (Path.cwd() / "artifacts").resolve()


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


def resolve_app_artifact(
    app: str,
    *,
    board: str = "dotbot-v3",
    config: str = "Release",
    sandbox: bool = False,
) -> Path:
    """Auto-resolve a single app's firmware artifact for cable-flashing.

    Decision tree (npm-style): present in ``./artifacts/`` → build from
    source → clear error pointing at build/fetch. An *explicit file path*
    is handled by the caller before this is reached.

    - Flat ``./artifacts/<app>-<board>.hex`` (bare) or
      ``./artifacts/<app>-sandbox-<board>.bin`` (sandbox), as produced by
      `dotbot fw build` / `dotbot fw artifacts`.
    - Else, if a DotBot-firmware repo is locatable, build it (needs SES)
      and use the SES output path.
    - Else, a friendly error telling the user to build or fetch first.
    """
    name = (
        f"{app}-sandbox-{board}.bin" if sandbox else f"{app}-{board}.hex"
    )
    cached = artifacts_dir() / name
    if cached.is_file():
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
        "  • `dotbot fw fetch -f <version>` to download a release, then retry, or\n"
        "  • pass an explicit path: `dotbot device flash ./artifacts/<file>`."
    )
