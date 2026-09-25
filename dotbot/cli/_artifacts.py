# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Shared artifact-resolution + friendly-error helpers for `fw` / `device`.

Owns the user-level ``~/.dotbot/artifacts/`` cache convention, the
absolute-path echo on every cache read/write (so you always see where files
landed, regardless of the directory you ran from), the app-image lookup used
by ``dotbot device flash <app>``, and the centralized nrfjprog-missing
message.

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


def resolve_app_artifact(
    app: str,
    *,
    board: str = "dotbot-v3",
    bare: bool = False,
    fw_version: str | None = None,
) -> Path:
    """The cached dotbot-firmware image of `app` for `board`, selected by `-f`.

    Sandboxed (`<app>-sandbox-<board>.bin`) on boards that have a sandbox,
    bare (`<app>-<board>.hex`) with `bare` or elsewhere. `fw_version` follows
    `dotbot.firmware.fetch.resolve_fw_dir`: a release is fetched if missing,
    and nothing is ever built.
    """
    from dotbot.cli._fw_helpers import app_image_name, has_sandbox
    from dotbot.firmware.fetch import resolve_fw_dir

    name = app_image_name(app, board, bare)
    build_args = f"-a {app}"
    if board != "dotbot-v3":
        build_args += f" -t {board}"
    if bare and has_sandbox(board):
        build_args += " --bare"
    root, _ = resolve_fw_dir(
        "dotbot-firmware",
        fw_version,
        artifacts_dir(),
        required=(name,),
        build_args=build_args,
    )
    image = root / name
    echo_artifact_path(image, action="using")
    return image
