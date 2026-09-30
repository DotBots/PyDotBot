"""`dotbot fw` - firmware artifacts: build, fetch, list, make.

`fw` is the *artifacts* namespace - it produces or downloads firmware
files. It never touches hardware: flashing a device lives under `fw`'s
sibling `dotbot device`, and OTA-flashing the fleet under `dotbot swarm`.

`build` and `fetch` take the same names `dotbot device flash` does: a role
(`swarmit-sandbox`, `mari-gateway`) or a DotBot-firmware app. They fill the
cache (`~/.dotbot/artifacts/`) as mirror images, one directory per firmware
set, under the same release file names:

- `fetch [ROLE|APP]...` downloads a release into `<release>-<tag>/`.
- `build [ROLE|APP]...` builds from local source folders (DotBot-firmware,
  swarmit, mari) via SES (`emBuild`) and copies the result into
  `<source>-<name>/` (`local` unless `--as NAME`), with a `manifest.json`
  recording the source folder, git sha and file hashes.

`list` shows the sets; `clean`/`targets` act on the DotBot-firmware
source folder; `make` is the low-level escape hatch that forwards arbitrary
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
from dotbot.cli._cfg import from_config, on_commandline
from dotbot.cli._fw_helpers import (
    BARE_TARGETS,
    CONFIGS,
    DEFAULT_BOARD,
    DEFAULT_CONFIGS,
    run_make,
)
from dotbot.cli._fw_sources import APP_SOURCE, ROLES, SOURCES
from dotbot.firmware.schedules import MARI_SCHEDULES

_NOT_READY = (
    "`dotbot fw {sub}` is not implemented yet.\n"
    "For now: use SEGGER Embedded Studio directly, or invoke the "
    "Makefile in your DotBot-firmware source folder."
)

# How build output names what it is building, per source.
_LABELS = {APP_SOURCE: "apps", **{source: role for role, source in ROLES.items()}}


@click.group(
    name="fw",
    help=(
        "Firmware artifacts: build (from your source folders via SEGGER "
        "Embedded Studio) and fetch (a release) into the cache, then list. "
        "Both take a role (swarmit-sandbox, mari-gateway) or an app name, "
        "the names `dotbot device flash` takes. Sandboxed apps by default on "
        "boards that have a sandbox; --bare for bare-metal apps. Flashing "
        "lives under `dotbot device` (one board) and `dotbot swarm` (the "
        "fleet). Need a Makefile knob? `dotbot fw make` forwards to `make`."
    ),
)
def cmd():
    pass


def _names_argument(f):
    return click.argument("names", nargs=-1, metavar="[ROLE|APP]...")(f)


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


def _source_repo(source: str, path: Path | None, explicit: bool) -> Path:
    """The source folder `source` builds from: `path`, checked, or the configured one."""
    spec = _fw_helpers.REPO_SPECS[source]
    if path is not None:
        if not (path / spec.marker).is_file():
            raise click.ClickException(
                f"--path {path} is not a {spec.dirname} source folder: it has "
                f"no {spec.marker}."
            )
        return path
    try:
        return _fw_helpers.resolve_repo(spec)
    except click.ClickException as exc:
        if explicit:
            raise
        raise click.ClickException(
            f"{exc.message}\nOr name only what your source folders build, "
            "e.g. `dotbot fw build dotbot` (an app) or `dotbot fw build "
            "swarmit-sandbox`."
        ) from exc


@cmd.command()
@_names_argument
@_target_option
@click.option(
    "--part",
    "-a",
    "parts",
    multiple=True,
    help=(
        "Build only these parts of swarmit-sandbox (repeatable): bootloader, "
        "netcore. Default: both."
    ),
)
@_config_option(
    "Build configuration. Default: Debug for swarmit-sandbox and mari-gateway "
    "(what the swarmit release ships), Release for apps."
)
@_bare_option
@click.option(
    "--schedule",
    "schedules",
    multiple=True,
    type=click.Choice(tuple(MARI_SCHEDULES) + ("all",)),
    help=(
        "Build the mari-gateway net image for this TSCH schedule, as "
        "03app_gateway_net-<schedule>.hex, the file `dotbot device flash "
        "mari-gateway --schedule` reads (repeatable; 'all' builds every "
        "schedule). Replaces the default net image in this run. No release "
        "carries these images."
    ),
)
@click.option(
    "--path",
    type=click.Path(file_okay=False, dir_okay=True, exists=True, path_type=Path),
    default=None,
    help=(
        "Build from this source folder instead of the configured one, for "
        "this run (every name must build from the same source). Source "
        "folders otherwise come from [fw.sources] (dotbot-firmware, swarmit, "
        "mari) or DOTBOT_FW_SOURCES_<SOURCE>, defaulting to repos/<name> next "
        "to the config file."
    ),
)
@click.option(
    "--as",
    "set_name",
    default="local",
    show_default=True,
    help=(
        f"Name of the set: files go to {DEFAULT_ARTIFACTS_DISPLAY}/"
        "<source>-<NAME>/ (dotbot-firmware-, swarmit- or mari-), and flash "
        "commands take it as -f NAME."
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
    names,
    target,
    parts,
    config,
    bare,
    schedules,
    path,
    set_name,
    rebuild,
    print_path,
    verbose,
):
    """Build firmware from your source folders into the cache.

    ROLE is swarmit-sandbox (the swarmit bootloader for the board and the
    network core, from swarmit) or mari-gateway (the Mari gateway, both
    cores, from mari). APP is a DotBot-firmware app, e.g. spin or dotbot
    (see `dotbot fw targets`). Default: both roles and the apps a
    DotBot-firmware release ships for the board. The images are copied into
    ~/.dotbot/artifacts/<source>-<name>/ under their release file names,
    next to a manifest.json (source folder, git sha, dirty flag, build
    config, per-file sha256).
    """
    from dotbot.cli import _fw_sources as fs
    from dotbot.firmware.fetch import validate_set_name

    bare_given = on_commandline(ctx, "bare")
    target = from_config(ctx, "target", "board", "fw")
    config = from_config(ctx, "config", "build_config", "fw")
    bare = from_config(ctx, "bare", "bare", "fw", default=False)
    validate_set_name(set_name)
    names = list(dict.fromkeys(names))
    explicit = bool(names)
    roles = [name for name in names if name in ROLES]
    apps = [name for name in names if name not in ROLES]
    if explicit:
        sources = ([APP_SOURCE] if apps else []) + [
            source for role, source in ROLES.items() if role in roles
        ]
    else:
        sources = list(SOURCES)

    not_parts = [part for part in parts if part not in fs.SWARMIT_PARTS]
    if not_parts:
        raise click.ClickException(
            f"--part takes {' or '.join(fs.SWARMIT_PARTS)}, parts of "
            "swarmit-sandbox. Name a role or an app as an argument: "
            f"`dotbot fw build {' '.join(not_parts)}`."
        )
    if parts and "swarmit-sandbox" not in roles:
        raise click.ClickException(
            "--part picks parts of swarmit-sandbox: `dotbot fw build "
            f"swarmit-sandbox -a {' -a '.join(parts)}`."
        )
    schedule_names = fs.resolve_schedules(schedules)
    if schedule_names and "mari" not in sources:
        raise click.ClickException(
            "--schedule only applies to mari-gateway: `dotbot fw build "
            f"mari-gateway --schedule {' --schedule '.join(schedules)}`."
        )
    if bare_given and APP_SOURCE not in sources:
        raise click.ClickException(
            "--bare/--sandboxed only apply to apps; swarmit-sandbox and "
            "mari-gateway have one build each."
        )
    if path is not None and (not explicit or len(sources) != 1):
        raise click.ClickException(
            "--path overrides one source folder: name what to build from it, "
            "all from the same source, e.g. `dotbot fw build swarmit-sandbox "
            "--path PATH` or `dotbot fw build spin --path PATH`."
        )
    df_target = _fw_helpers.build_target(target, bare)

    planned = []
    for source in sources:
        cfg = config or DEFAULT_CONFIGS[source]
        if source == "swarmit":
            if (not parts or "bootloader" in parts) and (
                target not in fs.SWARMIT_BOARDS
            ):
                msg = f"swarmit-sandbox has no bootloader for board {target!r}"
                if explicit or parts:
                    raise click.ClickException(msg + ".")
                click.echo(f"[skip] {msg}", err=True)
                continue
            src_repo = _source_repo(source, path, explicit)
            selection = list(parts) or None
            steps = fs.swarmit_steps(src_repo, target, cfg, selection)
            files = [fs.collected_name(step) for step in steps]
            planned.append((source, src_repo, cfg, target, files, selection))
        elif source == "mari":
            src_repo = _source_repo(source, path, explicit)
            steps = fs.mari_steps(src_repo, cfg, schedule_names)
            files = [fs.collected_name(step) for step in steps]
            planned.append((source, src_repo, cfg, fs.MARI_GATEWAY_BOARD, files, None))
        else:
            src_repo = _source_repo(source, path, explicit)
            df_apps = fs.dotbot_firmware_apps(df_target, apps or None, src_repo)
            outputs = fs.dotbot_firmware_outputs(df_target, df_apps, cfg, src_repo)
            files = [f.name for f in outputs]
            planned.append((source, src_repo, cfg, target, files, df_apps))

    root = artifacts_dir()
    if print_path:
        for source, _, _, _, files, _ in planned:
            out = fs.set_dir(source, set_name, root)
            for name in files:
                click.echo(str(out / name))
        return

    mode = "rebuild" if rebuild else "incremental"
    copied: list[Path] = []
    t0 = time.perf_counter()
    for source, src_repo, cfg, board, _, selection in planned:
        click.echo(
            f"Building {_LABELS[source]} for {board} ({cfg}, {mode})...", err=True
        )
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
    """(May be removed.) Clean the DotBot-firmware build outputs for a board."""
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
    """(May be removed.) List the boards `dotbot fw build -t` takes.

    Also shows what each board builds. `dotbot fw make list-targets` prints
    the same board list from the Makefile.
    """
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
            what += ", swarmit-sandbox"
        if board == MARI_GATEWAY_BOARD:
            what += ", mari-gateway"
        click.echo(f"{board:<{width}}  {what}")


def _shipped_apps(directory: Path) -> set[str]:
    """The app names in a DotBot-firmware release directory."""
    boards = _fw_helpers.BOARD_NAMES
    suffixes = sorted(
        {f"-{t}" for board in boards for t in (board, f"sandbox-{board}")},
        key=len,
        reverse=True,
    )
    apps = set()
    for path in directory.iterdir():
        if path.suffix not in (".hex", ".bin"):
            continue
        for suffix in suffixes:
            if path.stem.endswith(suffix) and len(path.stem) > len(suffix):
                apps.add(path.stem[: -len(suffix)])
                break
    return apps


@cmd.command()
@_names_argument
@click.option(
    "--fw-version",
    "-f",
    default=None,
    help=(
        "A release tag or 'latest' (the swarmit and DotBot-firmware releases "
        "version independently, so a tag takes names from one of them). "
        "Default: the releases pydotbot pins."
    ),
)
def fetch(names, fw_version):
    """Download releases into ~/.dotbot/artifacts/<release>-<tag>/.

    ROLE is swarmit-sandbox or mari-gateway: both come from the swarmit
    release (the bootloaders, the network core and the Mari gateway; its pin
    is the installed swarmit package's version). Mari's own releases publish
    no firmware. APP is an app name: apps come from the DotBot-firmware
    release (every app it ships; its pin is the version pydotbot is tested
    against). Default: both releases. No release carries the per-schedule
    gateway images: build those with `dotbot fw build mari-gateway
    --schedule`.
    """
    from dotbot import pydotbot_version
    from dotbot.cli._fw_sources import APP_RELEASE, ROLE_RELEASES
    from dotbot.firmware.fetch import (
        DEFAULT_FETCH_SOURCES,
        _short_path,
        fetch_assets,
        pinned_version,
    )

    names = list(dict.fromkeys(names))
    sources = [name for name in names if name in SOURCES]
    if sources:
        raise click.ClickException(
            f"{', '.join(sources)}: `dotbot fw fetch` takes a role "
            f"({', '.join(ROLES)}) or an app name, not a source."
        )
    apps = [name for name in names if name not in ROLES]
    releases = list(
        dict.fromkeys(
            [ROLE_RELEASES[name] for name in names if name in ROLES]
            + ([APP_RELEASE] if apps else [])
        )
    ) or list(DEFAULT_FETCH_SOURCES)
    if fw_version not in (None, "latest") and len(releases) != 1:
        raise click.ClickException(
            f"-f {fw_version} names one release, and the swarmit release "
            "(swarmit-sandbox, mari-gateway) and the DotBot-firmware release "
            "(apps) version independently: fetch one at a time, e.g. "
            f"`dotbot fw fetch swarmit-sandbox -f {fw_version}`."
        )
    fetched: list[Path] = []
    for release in releases:
        if fw_version is None:
            version = pinned_version(release)
            click.echo(
                f"Fetching {release} {version} (pinned by pydotbot "
                f"{pydotbot_version()})..."
            )
        else:
            version = fw_version
            if version == "latest":
                click.echo(f"Fetching the latest {release} release...")
        out = fetch_assets(release, version, artifacts_dir())
        fetched.append(out)
        if release == APP_RELEASE and apps:
            shipped = _shipped_apps(out)
            missing = [app for app in apps if app not in shipped]
            if missing:
                raise click.ClickException(
                    f"The DotBot-firmware release in {_short_path(out)} ships no "
                    f"{', '.join(missing)}. It ships: "
                    f"{', '.join(sorted(shipped)) or '(no apps)'}. Roles: "
                    f"{', '.join(ROLES)}. Build an app it lacks with "
                    "`dotbot fw build <app>`."
                )
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
        click.echo("(nothing cached yet: run `dotbot fw fetch` or `dotbot fw build`)")
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
