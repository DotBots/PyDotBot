# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot fw` — firmware artifacts: build, fetch, list, make.

`fw` is the *artifacts* namespace — it produces or downloads firmware
files. It never touches hardware: flashing a device lives under `fw`'s
sibling `dotbot device`, and OTA-flashing the fleet under `dotbot swarm`.

The cache (`~/.dotbot/artifacts/`) holds one directory per firmware set,
and two verbs fill it as mirror images, under the same release file names:

- `fetch [SOURCE]...` downloads a release into `<source>-<tag>/`.
- `build [SOURCE]...` builds from local checkouts (DotBot-firmware, swarmit,
  mari) via SES (`emBuild`) and
  copies the result into `<source>-<name>/` (`local` unless `--as NAME`),
  with a `manifest.json` recording the checkout, git sha and file hashes.

`list` shows the sets; `clean`/`targets` act on the DotBot-firmware
checkout; `make` is the low-level escape hatch that forwards arbitrary
arguments to `make` there. Flash commands pick a set with `-f` and never
build (see `dotbot.firmware.fetch.resolve_fw_dir`).
"""

import json
import sys
import time
from pathlib import Path

import click

from dotbot.cli import _fw_helpers
from dotbot.cli._artifacts import (
    DEFAULT_ARTIFACTS_DISPLAY,
    artifacts_dir,
    echo_artifact_path,
)
from dotbot.cli._cfg import from_config
from dotbot.cli._fw_helpers import (
    BARE_TARGETS,
    CONFIGS,
    DEFAULT_BOARD,
    DEFAULT_CONFIGS,
    run_make,
)
from dotbot.cli._fw_sources import SOURCES
from dotbot.firmware.fetch import RELEASE_SOURCES
from dotbot.firmware.schedules import MARI_SCHEDULES

_NOT_READY = (
    "`dotbot fw {sub}` is not implemented yet.\n"
    "For now: use SEGGER Embedded Studio directly, or invoke the "
    "Makefile in your DotBot-firmware checkout (set `DOTBOT_FIRMWARE_REPO`)."
)


@click.group(
    name="fw",
    help=(
        "Firmware artifacts: build (from your checkouts via SEGGER Embedded "
        "Studio) and fetch (a release) into the cache, then list. Sandboxed "
        "apps by default on boards that have a sandbox; --bare for bare-metal "
        "apps. Flashing lives under `dotbot device` (one board) and `dotbot "
        "swarm` (the fleet). Need a Makefile knob? `dotbot fw make` forwards "
        "to `make`."
    ),
)
def cmd():
    pass


def _sources_argument(choices):
    def deco(f):
        return click.argument(
            "sources",
            nargs=-1,
            type=click.Choice(choices),
            metavar="[SOURCE]...",
        )(f)

    return deco


def _target_option(f):
    return click.option(
        "--target",
        "-t",
        default=DEFAULT_BOARD,
        show_default=True,
        help="Board (e.g. dotbot-v3, nrf52840dk). See `dotbot fw targets`.",
    )(f)


def _config_option(help_text):
    def deco(f):
        return click.option(
            "--build-config",
            "config",
            type=click.Choice(CONFIGS),
            default=None,
            help=help_text,
        )(f)

    return deco


def _bare_option(f):
    return click.option(
        "--bare/--sandboxed",
        default=None,
        help=(
            "Bare-metal apps (.hex) or sandboxed apps (.bin). Default: [fw].bare "
            "in config, else sandboxed on boards that have a sandbox "
            "(dotbot-v3, dotbot-v2, nrf5340dk), bare elsewhere."
        ),
    )(f)


def _verbose_option(f):
    return click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help="Show full SEGGER Embedded Studio `-verbose -echo` output.",
    )(f)


_REPO_SPECS = {
    "dotbot-firmware": _fw_helpers.FIRMWARE_REPO,
    "swarmit": _fw_helpers.SWARMIT_REPO,
    "mari": _fw_helpers.MARI_REPO,
}


def _source_repo(source: str, checkout: Path | None, explicit: bool) -> Path:
    """The checkout `source` builds from: `checkout`, checked, or the configured one."""
    spec = _REPO_SPECS[source]
    if checkout is not None:
        if not (checkout / spec.marker).is_file():
            raise click.ClickException(
                f"--checkout {checkout} is not a {spec.dirname} checkout: it has "
                f"no {spec.marker}."
            )
        return checkout
    try:
        return _fw_helpers.resolve_repo(spec)
    except click.ClickException as exc:
        if explicit:
            raise
        raise click.ClickException(
            f"{exc.message}\nOr build only the sources you have checked out, "
            "e.g. `dotbot fw build dotbot-firmware`."
        ) from exc


def _list_dotbot_firmware_apps(target: str) -> list[str]:
    try:
        return _fw_helpers.list_projects(target)
    except click.ClickException:
        return []


@cmd.command()
@_sources_argument(SOURCES)
@_target_option
@click.option(
    "--app",
    "-a",
    "apps",
    multiple=True,
    help=(
        "Build only these parts (repeatable). swarmit: bootloader, netcore; "
        "mari: mari-gateway (its app and net images); dotbot-firmware: an app "
        "project name (see `dotbot fw targets`). Without a SOURCE the source is "
        "inferred from the name. Default: what the source's release ships."
    ),
)
@_config_option(
    "Build configuration. Default: Debug for swarmit and mari (what the "
    "swarmit release ships), Release for dotbot-firmware."
)
@_bare_option
@click.option(
    "--schedule",
    "schedules",
    multiple=True,
    type=click.Choice(tuple(MARI_SCHEDULES) + ("all",)),
    help=(
        "Build the Mari gateway net image for this TSCH schedule, as "
        "03app_gateway_net-<schedule>.hex, the file `dotbot device "
        "flash-mari-gateway --schedule` reads (repeatable; 'all' builds every "
        "schedule). Replaces the default net image in this run."
    ),
)
@click.option(
    "--checkout",
    type=click.Path(file_okay=False, dir_okay=True, exists=True, path_type=Path),
    default=None,
    help=(
        "Build from this checkout instead of the configured one, for this run "
        "(needs exactly one SOURCE). Checkouts otherwise come from "
        "DOTBOT_FIRMWARE_REPO / [fw].firmware_repo, DOTBOT_SWARMIT_REPO / "
        "[fw].swarmit_repo and DOTBOT_MARI_REPO / [fw].mari_repo, defaulting "
        "to repos/<name> next to the config file."
    ),
)
@click.option(
    "--as",
    "set_name",
    default="local",
    show_default=True,
    help=(
        f"Name of the set: files go to {DEFAULT_ARTIFACTS_DISPLAY}/"
        "<source>-<NAME>/, and flash commands take it as -f NAME."
    ),
)
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Force full rebuild (pass `-rebuild` to emBuild). Default: incremental.",
)
@click.option(
    "--print-path",
    is_flag=True,
    default=False,
    help="Print where each artifact would be collected, without building.",
)
@_verbose_option
@click.pass_context
def build(
    ctx,
    sources,
    target,
    apps,
    config,
    bare,
    schedules,
    checkout,
    set_name,
    rebuild,
    print_path,
    verbose,
):
    """Build firmware from your checkouts into the cache.

    SOURCE is dotbot-firmware, swarmit or mari; default: all three.
    dotbot-firmware builds the apps its release ships for the board; swarmit
    the bootloader for the board and the network core; mari the gateway
    (mari-gateway). The images are copied into
    ~/.dotbot/artifacts/<source>-<name>/ under their release file names,
    next to a manifest.json (checkout, git sha, dirty flag, build config,
    per-file sha256).
    """
    from dotbot.cli import _fw_sources as fs
    from dotbot.firmware.fetch import validate_set_name

    target = from_config(ctx, "target", "board", "fw")
    config = from_config(ctx, "config", "build_config", "fw")
    bare = from_config(ctx, "bare", "bare", "fw", default=False)
    validate_set_name(set_name)
    explicit = bool(sources)
    sources = list(dict.fromkeys(sources)) or list(SOURCES)
    if checkout is not None and (not explicit or len(sources) != 1):
        raise click.ClickException(
            "--checkout overrides one checkout: name exactly one SOURCE, e.g. "
            "`dotbot fw build swarmit --checkout PATH`."
        )
    df_target = _fw_helpers.build_target(target, bare)

    routed: dict[str, list[str]] = {}
    if apps:
        routed = fs.route_apps(
            apps, sources, lambda: _list_dotbot_firmware_apps(df_target)
        )
        idle = [s for s in sources if s not in routed]
        if explicit and idle:
            raise click.ClickException(
                f"No -a names a part of {', '.join(idle)}; drop it from the "
                "sources or add its -a."
            )
        sources = [s for s in sources if s in routed]
    schedule_names = fs.resolve_schedules(schedules)
    if schedule_names and "mari" not in sources:
        raise click.ClickException(
            "--schedule selects Mari gateway net images, and this run does not "
            "build mari: `dotbot fw build mari --schedule "
            f"{' --schedule '.join(schedules)}`."
        )

    planned = []
    for source in sources:
        cfg = config or DEFAULT_CONFIGS[source]
        if source == "swarmit":
            parts = routed.get("swarmit")
            if (parts is None or "bootloader" in parts) and (
                target not in fs.SWARMIT_BOARDS
            ):
                msg = f"swarmit has no bootloader for board {target!r}"
                if explicit or parts:
                    raise click.ClickException(msg + ".")
                click.echo(f"[skip] {msg}", err=True)
                continue
            src_repo = _source_repo(source, checkout, explicit)
            steps = fs.swarmit_steps(src_repo, target, cfg, parts)
            names = [fs.collected_name(step) for step in steps]
            planned.append((source, src_repo, cfg, target, names, parts))
        elif source == "mari":
            parts = routed.get("mari")
            src_repo = _source_repo(source, checkout, explicit)
            steps = fs.mari_steps(src_repo, cfg, parts, schedule_names)
            names = [fs.collected_name(step) for step in steps]
            planned.append((source, src_repo, cfg, fs.MARI_GATEWAY_BOARD, names, parts))
        else:
            src_repo = _source_repo(source, checkout, explicit)
            df_apps = fs.dotbot_firmware_apps(
                df_target, routed.get("dotbot-firmware"), src_repo
            )
            files = fs.dotbot_firmware_outputs(df_target, df_apps, cfg, src_repo)
            names = [f.name for f in files]
            planned.append((source, src_repo, cfg, target, names, df_apps))

    root = artifacts_dir()
    if print_path:
        for source, _, _, _, names, _ in planned:
            out = fs.set_dir(source, set_name, root)
            for name in names:
                click.echo(str(out / name))
        return

    mode = "rebuild" if rebuild else "incremental"
    copied: list[Path] = []
    t0 = time.perf_counter()
    for source, src_repo, cfg, board, _, selection in planned:
        click.echo(f"Building {source} for {board} ({cfg}, {mode})...", err=True)
        if source == "swarmit":
            files = fs.build_swarmit(
                target,
                cfg,
                parts=selection,
                repo=src_repo,
                rebuild=rebuild,
                verbose=verbose,
            )
        elif source == "mari":
            files = fs.build_mari(
                cfg,
                parts=selection,
                schedules=schedule_names,
                repo=src_repo,
                rebuild=rebuild,
                verbose=verbose,
            )
        else:
            files = fs.build_dotbot_firmware(
                df_target,
                selection,
                cfg,
                repo=src_repo,
                rebuild=rebuild,
                verbose=verbose,
            )
        out = fs.set_dir(source, set_name, root)
        before = {
            f.name: fs.sha256(out / f.name) for f in files if (out / f.name).is_file()
        }
        collected = fs.collect(files, out)
        manifest = fs.write_build_manifest(
            out,
            source=source,
            name=set_name,
            repo=src_repo,
            config=cfg,
            board=board,
            files=collected,
        )
        for p in collected:
            new_sha = manifest["files"][p.name]["sha256"]
            state = (
                "new"
                if p.name not in before
                else "unchanged" if before[p.name] == new_sha else "changed"
            )
            click.echo(f"  {state:<9} {p.name}", err=True)
        echo_artifact_path(out, action="collected into")
        copied += collected
    elapsed = time.perf_counter() - t0
    click.echo(f"✓ Collected {len(copied)} artifact(s) in {elapsed:.1f}s", err=True)
    for p in copied:
        click.echo(str(p))


@cmd.command()
@_target_option
@_config_option("Build configuration. Default: Release.")
@_bare_option
@_verbose_option
@click.pass_context
def clean(ctx, target, config, bare, verbose):
    """Clean the DotBot-firmware SES build outputs for a board."""
    target = from_config(ctx, "target", "board", "fw")
    config = (
        from_config(ctx, "config", "build_config", "fw")
        or DEFAULT_CONFIGS["dotbot-firmware"]
    )
    bare = from_config(ctx, "bare", "bare", "fw", default=False)
    build_target = _fw_helpers.build_target(target, bare)
    click.echo(f"Cleaning {build_target} ({config})...", err=True)
    elapsed = run_make(build_target, config, make_targets=["clean"], quiet=not verbose)
    click.echo(f"✓ Cleaned in {elapsed:.1f}s", err=True)


@cmd.command(name="targets")
def list_targets():
    """List the boards `dotbot fw build -t` takes, and the apps each builds."""
    from dotbot.cli._fw_sources import MARI_GATEWAY_BOARD, SWARMIT_BOARDS

    boards = _fw_helpers.BOARD_NAMES
    width = max(len(t) for t in boards)
    for board in sorted(boards):
        if _fw_helpers.has_sandbox(board) and board in BARE_TARGETS:
            what = "sandboxed apps (bare with --bare)"
        elif _fw_helpers.has_sandbox(board):
            what = "sandboxed apps"
        else:
            what = "bare apps"
        if board in SWARMIT_BOARDS:
            what += ", swarmit bootloader"
        if board == MARI_GATEWAY_BOARD:
            what += ", Mari gateway"
        click.echo(f"{board:<{width}}  {what}")


@cmd.command()
@_sources_argument(tuple(RELEASE_SOURCES))
@click.option(
    "--fw-version",
    "-f",
    default=None,
    help=(
        "A release tag (needs exactly one SOURCE: the two version "
        "independently) or 'latest'. Default: the release pydotbot pins."
    ),
)
def fetch(sources, fw_version):
    """Download releases into ~/.dotbot/artifacts/<source>-<tag>/.

    SOURCE is swarmit (the bootloaders, the network core and the Mari
    gateway; its pin is the installed swarmit package's version) or
    dotbot-firmware (the apps; its pin is the version pydotbot is tested
    against). Default: both. Mari's own releases publish no firmware, and no
    release carries the per-schedule gateway images: build those with
    `dotbot fw build mari --schedule`.
    """
    from dotbot import pydotbot_version
    from dotbot.firmware.fetch import (
        DEFAULT_FETCH_SOURCES,
        _short_path,
        fetch_assets,
        pinned_version,
    )

    sources = list(dict.fromkeys(sources)) or list(DEFAULT_FETCH_SOURCES)
    if fw_version not in (None, "latest") and len(sources) != 1:
        raise click.ClickException(
            f"-f {fw_version} names one release, and swarmit and dotbot-firmware "
            "version independently: name its SOURCE, e.g. "
            f"`dotbot fw fetch swarmit -f {fw_version}`."
        )
    fetched: list[Path] = []
    for src in sources:
        if fw_version is None:
            version = pinned_version(src)
            click.echo(
                f"Fetching {src} {version} (pinned by pydotbot {pydotbot_version()})..."
            )
        else:
            version = fw_version
            if version == "latest":
                click.echo(f"Fetching the latest {src} release...")
        fetched.append(fetch_assets(src, version, artifacts_dir()))
    click.echo("\nDone. Firmware fetched into:")
    for path in fetched:
        click.echo(f"  {_short_path(path)}")


def _describe_set(directory: Path) -> str:
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
    except (OSError, ValueError):
        return ""
    if manifest.get("kind") == "build":
        sha = (manifest.get("git_sha") or "no git")[:10]
        dirty = " dirty" if manifest.get("dirty") else ""
        shas = {
            e.get("git_sha")
            for e in manifest.get("files", {}).values()
            if isinstance(e, dict)
        }
        mixed = ", mixed builds" if len(shas) > 1 else ""
        return (
            f"built {sha}{dirty} ({manifest.get('build_config')}, "
            f"{manifest.get('board')}{mixed}) at {manifest.get('built_at')}, "
            f"from {manifest.get('repo')}"
        )
    if "version" in manifest:
        return f"release {manifest['version']}, fetched {manifest.get('fetched_at')}"
    return ""


@cmd.command(name="list")
def list_artifacts():
    """List the firmware sets cached in ~/.dotbot/artifacts/."""
    root = artifacts_dir()
    echo_artifact_path(root, action="listing")
    sets = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not sets:
        click.echo("(nothing cached yet — run `dotbot fw fetch` or `dotbot fw build`)")
        return
    for directory in sets:
        images = sorted(
            p.name
            for p in directory.iterdir()
            if p.is_file()
            and p.suffix in (".hex", ".bin")
            and not p.name.startswith("config-")
        )
        description = _describe_set(directory)
        click.echo(f"{directory.name}" + (f"  {description}" if description else ""))
        for name in images:
            click.echo(f"  {name}")


@cmd.command()
@click.argument("name")
@click.option(
    "--template",
    type=click.Choice(["swarmit-app", "bare"]),
    default="swarmit-app",
    show_default=True,
)
def new(name, template):  # pylint: disable=unused-argument
    """Scaffold a new firmware project (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="new"), err=True)
    sys.exit(2)


# The low-level Makefile escape hatch, mounted next to its high layer
# `fw build`. Importing `make` here is cheap (no SES/firmware import at
# module load), so it doesn't compromise the dispatcher's lazy loading.
from dotbot.cli.make import cmd as _make_cmd  # noqa: E402

cmd.add_command(_make_cmd)
