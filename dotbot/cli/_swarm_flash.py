# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Name -> firmware resolution for `dotbot swarm flash <name>`.

`dotbot swarm` is a passthrough to swarmit's CLI, whose `flash` takes a
firmware file. This lets an operator flash a bundled example app by a short,
persona-friendly name (`rc-car`, `spin`, `lights`) instead of typing the full
~/.dotbot/artifacts/<source>-<version>/<app>-sandbox-<board>.bin path. A token
that already looks like a path is passed straight through, so the
explicit-path workflow keeps working unchanged.

The catalog is intentionally tiny and curated: these are the demos an operator
reaches for, named for what they DO rather than the firmware filename. Anything
else is still flashable by passing an explicit `.bin`/`.hex` path.
"""

from pathlib import Path

import click

from dotbot.cli._artifacts import _find_in_cache

# Friendly name -> sandbox-app stem. The stem resolves to
# `<stem>-sandbox-<board>.bin` in the fetched dotbot-firmware release.
APP_CATALOG = {
    "rc-car": "dotbot",  # drive the DotBot from the UI / keyboard / joystick
    "spin": "spin",  # the DotBots spin in place
    "lights": "rgbled",  # the on-board RGB LED
}

_DEFAULT_BOARD = "dotbot-v3"
# swarmit's `flash` options that consume the following token as their value;
# everything else starting with "-" is a bare flag. Used to find the firmware
# positional among the flash args.
_VALUE_FLAGS = {"-t", "--ota-timeout", "-r", "--ota-max-retries"}


def _looks_like_path(value: str) -> bool:
    return (
        value.endswith((".hex", ".bin"))
        or "/" in value
        or "\\" in value
        or Path(value).is_file()
    )


def _bin_for(stem: str, board: str = _DEFAULT_BOARD) -> Path | None:
    return _find_in_cache(f"{stem}-sandbox-{board}.bin")


def _first_positional(rest: list[str]) -> int | None:
    """Index of the first non-flag token in `rest` (the firmware argument)."""
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in _VALUE_FLAGS:
            i += 2  # skip the flag and the value it consumes
            continue
        if tok.startswith("-"):
            i += 1  # a bare flag (-y/--yes, ...) or --flag=value
            continue
        return i
    return None


def render_catalog() -> str:
    lines = ["Bundled apps you can flash by name:", ""]
    width = max(len(name) for name in APP_CATALOG)
    for name, stem in APP_CATALOG.items():
        filename = f"{stem}-sandbox-{_DEFAULT_BOARD}.bin"
        fetched = _bin_for(stem) is not None
        suffix = "" if fetched else "  (not fetched - run `dotbot fw fetch`)"
        lines.append(f"  {name:<{width}}  ->  {filename}{suffix}")
    lines += [
        "",
        "Or pass an explicit .hex/.bin path. For a non-v3 board, pass the path.",
    ]
    return "\n".join(lines)


def resolve_flash_args(rest: list[str]) -> tuple[list[str], bool]:
    """Rewrite the tokens after `flash` so a known app name becomes a .bin path.

    Returns `(new_rest, handled)`. `handled=True` means the command was fully
    serviced here (e.g. `--list`) and the caller must NOT forward it to swarmit.
    A token that's already a path, or any flag-only invocation, passes through
    untouched.
    """
    rest = list(rest)
    if "--list" in rest:
        click.echo(render_catalog())
        return rest, True

    idx = _first_positional(rest)
    if idx is None:
        return rest, False  # no firmware token; let swarmit report it

    target = rest[idx]
    if target in APP_CATALOG:
        stem = APP_CATALOG[target]
        path = _bin_for(stem)
        if path is None:
            raise click.ClickException(
                f"'{target}' maps to {stem}-sandbox-{_DEFAULT_BOARD}.bin, which "
                "isn't in the artifacts cache yet. Run `dotbot fw fetch` first."
            )
        rest[idx] = str(path)
        click.echo(f"Flashing '{target}' ({path.name})", err=True)
        return rest, False

    if _looks_like_path(target):
        return rest, False  # explicit path - passthrough

    raise click.ClickException(
        f"Unknown app '{target}'. Pass a .hex/.bin path, or one of: "
        f"{', '.join(APP_CATALOG)} (see `dotbot swarm flash --list`)."
    )
