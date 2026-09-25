# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Name -> firmware resolution for `dotbot swarm flash <name>`.

`dotbot swarm` is a passthrough to swarmit's CLI, whose `flash` takes a
firmware file. This lets an operator flash a bundled example app by a short,
persona-friendly name (`rc-car`, `spin`, `lights`) instead of typing the full
~/.dotbot/artifacts/dotbot-firmware-<set>/<app>-sandbox-<board>.bin path, with
`-f` picking the set by the rule every flash command shares. A token
that already looks like a path is passed straight through, so the
explicit-path workflow keeps working unchanged.

The catalog is intentionally tiny and curated: these are the demos an operator
reaches for, named for what they DO rather than the firmware filename. Anything
else is still flashable by passing an explicit `.bin`/`.hex` path.
"""

from pathlib import Path

import click

from dotbot.cli._artifacts import artifacts_dir

# Friendly name -> sandbox-app stem. The stem resolves to
# `<stem>-sandbox-<board>.bin` in the dotbot-firmware set `-f` selects.
APP_CATALOG = {
    "rc-car": "dotbot",  # drive the DotBot from the UI / keyboard / joystick
    "spin": "spin",  # the DotBots spin in place
    "lights": "rgbled",  # the on-board RGB LED
    "calibrate": "calibrate",  # LH2 capture on the robot's own button
}

_DEFAULT_BOARD = "dotbot-v3"
# swarmit's `flash` options that consume the following token as their value;
# everything else starting with "-" is a bare flag. Used to find the firmware
# positional among the flash args.
_VALUE_FLAGS = {"-t", "--ota-timeout", "-r", "--ota-max-retries", "--image-version"}
# PyDotBot's own `flash` option, consumed here and never forwarded to swarmit.
_FW_VERSION_FLAGS = ("-f", "--fw-version")


def _looks_like_path(value: str) -> bool:
    return (
        value.endswith((".hex", ".bin"))
        or "/" in value
        or "\\" in value
        or Path(value).is_file()
    )


def _filename(stem: str, board: str = _DEFAULT_BOARD) -> str:
    return f"{stem}-sandbox-{board}.bin"


def _bin_for(stem: str, fw_version: str | None) -> Path:
    from dotbot.firmware.fetch import resolve_fw_dir

    name = _filename(stem)
    root, _ = resolve_fw_dir(
        "dotbot-firmware",
        fw_version,
        artifacts_dir(),
        required=(name,),
        build_args=f"-a {stem}",
    )
    return root / name


def _pop_fw_version(rest: list[str]) -> tuple[list[str], str | None]:
    """Remove `-f/--fw-version VALUE` from `rest`; return (rest, value)."""
    out: list[str] = []
    value = None
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in _VALUE_FLAGS:
            out += rest[i : i + 2]
            i += 2
            continue
        if tok in _FW_VERSION_FLAGS:
            if i + 1 >= len(rest):
                raise click.ClickException(f"{tok} needs a value.")
            value = rest[i + 1]
            i += 2
            continue
        if tok.startswith("--fw-version="):
            value = tok.split("=", 1)[1]
            i += 1
            continue
        out.append(tok)
        i += 1
    return out, value


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


def render_catalog(fw_version: str | None = None) -> str:
    from dotbot.firmware.fetch import pinned_version, resolve_fw_root

    label = fw_version or pinned_version("dotbot-firmware")
    root = None
    if label != "latest" and "/" not in label:
        root = resolve_fw_root(artifacts_dir(), "dotbot-firmware", label)
    elif "/" in label:
        root = Path(label).expanduser()
    lines = [f"Bundled apps you can flash by name (from dotbot-firmware {label}):", ""]
    width = max(len(name) for name in APP_CATALOG)
    for name, stem in APP_CATALOG.items():
        filename = _filename(stem)
        suffix = ""
        if root is not None and not (root / filename).is_file():
            suffix = "  (not in the cache yet)"
        lines.append(f"  {name:<{width}}  ->  {filename}{suffix}")
    lines += [
        "",
        "Or pass an explicit .hex/.bin path. For a non-v3 board, pass the path.",
    ]
    return "\n".join(lines)


def flash_help_epilog() -> str:
    """An epilog appended to swarmit's `flash --help` output.

    swarmit owns the `flash` command, so the bundled-name sugar and `-f`
    aren't in its native help. Attaching this as the command's epilog lets
    Click render them after the Options block (`\\b` keeps the lines
    unwrapped).
    """
    names = ", ".join(APP_CATALOG)
    return (
        "\b\n"
        f"Examples: flash a bundled app by name ({names}), or an explicit "
        ".hex/.bin path.\n"
        "-f, --fw-version picks the dotbot-firmware set a bundled name comes "
        "from:\n"
        "  a release tag, 'latest', a set built by `dotbot fw build` ('local'),\n"
        "  or a directory path; default: the release pydotbot pins, fetched\n"
        "  if missing. Nothing is built.\n"
        "Run `dotbot swarm flash --list` to see what each bundled app flashes."
    )


def resolve_flash_args(rest: list[str]) -> tuple[list[str], bool]:
    """Rewrite the tokens after `flash` so a known app name becomes a .bin path.

    Returns `(new_rest, handled)`. `handled=True` means the command was fully
    serviced here (e.g. `--list`) and the caller must NOT forward it to swarmit.
    `-f/--fw-version` is consumed here. A token that's already a path, or any
    flag-only invocation, passes through untouched.
    """
    rest, fw_version = _pop_fw_version(list(rest))
    if "--list" in rest:
        click.echo(render_catalog(fw_version))
        return rest, True

    idx = _first_positional(rest)
    if idx is None:
        return rest, False  # no firmware token; let swarmit report it

    target = rest[idx]
    if target in APP_CATALOG:
        path = _bin_for(APP_CATALOG[target], fw_version)
        rest[idx] = str(path)
        click.echo(f"Flashing '{target}' -> {path}", err=True)
        return rest, False

    if _looks_like_path(target):
        if fw_version is not None:
            raise click.ClickException(
                "-f selects the set a bundled app name resolves from; an "
                "explicit file path needs no -f."
            )
        return rest, False  # explicit path - passthrough

    raise click.ClickException(
        f"Unknown app '{target}'. Pass a .hex/.bin path, or one of: "
        f"{', '.join(APP_CATALOG)} (see `dotbot swarm flash --list`)."
    )
