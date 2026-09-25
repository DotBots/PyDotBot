# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot fw` — firmware artifacts: build, fetch, list, make.

`fw` is the *artifacts* namespace — it produces or downloads firmware
files. It never touches hardware: flashing a device lives under `fw`'s
sibling `dotbot device`, and OTA-flashing the fleet under `dotbot swarm`.

- `build` compiles from source via SES (`emBuild`) in `DotBot-firmware`,
  leaving the result in the SES `Output/.../Exe/` tree and echoing that
  path — it does *not* copy into the cache. Bare apps by default;
  `--sandbox` builds the TrustZone NS flavor (`sandbox-<board>`, `.bin`).
- `artifacts` builds *and* collects the result into the cache
  (`~/.dotbot/artifacts/dotbot-firmware-local/`), with the flat
  `<app>-<board>.hex` / `<app>-sandbox-<board>.bin` names.
- `fetch` downloads the pinned release (or a `-f <tag>`/`latest`
  override) into `~/.dotbot/artifacts/<source>-<version>/`.
- `list` shows what's cached in `~/.dotbot/artifacts/`.
- `make` is the low-level escape hatch: it forwards arbitrary arguments
  to `make` in the firmware repo (workspace-resolved SEGGER_DIR) for the
  Makefile knobs `build` deliberately doesn't model.

Only `artifacts` and `fetch` populate the cache. The device-flash
commands then auto-resolve their input, by *different* rules: `dotbot
device flash <app>` resolves an app image present in `~/.dotbot/artifacts/` →
build-from-source → error (it never fetches); `device flash-swarmit-sandbox`
/ `flash-mari-gateway` resolve a release's system firmware present in
`~/.dotbot/artifacts/` → fetch (they never build).
"""

import sys
import time
from pathlib import Path

import click

from dotbot.cli._artifacts import (
    DEFAULT_ARTIFACTS_DISPLAY,
    artifacts_dir,
    echo_artifact_path,
)
from dotbot.cli import _fw_helpers
from dotbot.cli._cfg import from_config
from dotbot.cli._fw_sources import SOURCES
from dotbot.cli._fw_helpers import (
    BARE_TARGETS,
    CONFIGS,
    DEFAULT_BARE_TARGET,
    DEFAULT_CONFIG,
    SANDBOX_BOARDS,
    artifact_path,
    list_projects,
    run_make,
    validate_bare_target,
    validate_sandbox_board,
)

_NOT_READY = (
    "`dotbot fw {sub}` is not implemented yet.\n"
    "For now: use SEGGER Embedded Studio directly, or invoke the "
    "Makefile in your DotBot-firmware checkout (set `DOTBOT_FIRMWARE_REPO`)."
)


@click.group(
    name="fw",
    help=(
        "Firmware artifacts: build (from source via SEGGER Embedded Studio), "
        "fetch (a release), "
        "list. Bare apps by default; `--sandbox` for TrustZone NS apps. "
        "Flashing lives under `dotbot device` (one board) and `dotbot swarm` "
        "(the fleet). Need a Makefile knob? `dotbot fw make` forwards to `make`."
    ),
)
def cmd():
    pass


def _target_option(f):
    """Reusable `--target/-t` option for build/clean/artifacts."""
    return click.option(
        "--target",
        "-t",
        default=DEFAULT_BARE_TARGET,
        show_default=True,
        help=(
            "Board/target (e.g. dotbot-v3, nrf5340dk-app). With --sandbox, "
            "pass the board name without the `sandbox-` prefix. See "
            "`dotbot fw targets [--sandbox]`."
        ),
    )(f)


def _project_option(f):
    """Reusable `--app/-a NAME` option for build/clean/artifacts."""
    return click.option(
        "--app",
        "-a",
        "project",
        type=str,
        default=None,
        help=(
            "Build a single app (e.g. `dotbot`, `spin`). "
            "Default: build every app available for the target."
        ),
    )(f)


def _config_option(f):
    """Reusable `--build-config` option for build/clean/artifacts."""
    return click.option(
        "--build-config",
        "config",
        type=click.Choice(CONFIGS),
        default=DEFAULT_CONFIG,
        show_default=True,
        help="Build configuration (Debug or Release).",
    )(f)


def _sandbox_option(f):
    """Reusable `--sandbox` flavor flag (TrustZone NS apps)."""
    return click.option(
        "--sandbox",
        is_flag=True,
        default=False,
        help="Build/list the TrustZone sandbox (NS) flavor — `sandbox-<board>`, emits .bin.",
    )(f)


def _resolve_build_target(target: str, sandbox: bool) -> str:
    """Validate and return the make BUILD_TARGET for (board, flavor)."""
    if sandbox:
        validate_sandbox_board(target)
        return f"sandbox-{target}"
    validate_bare_target(target)
    return target


@cmd.command()
@_target_option
@_project_option
@_config_option
@_sandbox_option
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Force full rebuild (pass `-rebuild` to emBuild). Default: incremental.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show full SEGGER Embedded Studio `-verbose -echo` output.",
)
@click.pass_context
def build(ctx, target, project, config, sandbox, rebuild, verbose):
    """Build firmware from source (default target: dotbot-v3)."""
    target = from_config(ctx, "target", "board", "fw")
    config = from_config(ctx, "config", "build_config", "fw")
    sandbox = from_config(ctx, "sandbox", "sandbox", "fw")
    build_target = _resolve_build_target(target, sandbox)
    flavor = "sandbox " if sandbox else ""
    apps_to_build = [project] if project else list_projects(build_target)
    if project and project not in list_projects(build_target):
        raise click.ClickException(
            f"App {project!r} is not available for target {target!r}.\n"
            f"Available: {', '.join(list_projects(build_target))}"
        )
    mode = "rebuild" if rebuild else "incremental"
    what = project or f"all {flavor}apps"
    click.echo(f"Building {what} for {target} ({config}, {mode})...", err=True)
    elapsed = run_make(
        build_target, config, project, rebuild=rebuild, quiet=not verbose
    )
    click.echo(f"✓ Built {target} in {elapsed:.1f}s", err=True)
    # Echo each produced artifact path on its own stdout line so pipelines
    # like `dotbot fw build | xargs -n1 ...` work.
    for app in apps_to_build:
        out = artifact_path(build_target, app, config)
        if out.is_file():
            click.echo(str(out))


@cmd.command()
@_target_option
@_config_option
@_sandbox_option
@click.option("-v", "--verbose", is_flag=True, default=False)
@click.pass_context
def clean(ctx, target, config, sandbox, verbose):
    """Clean SEGGER Embedded Studio build outputs (default target: dotbot-v3)."""
    target = from_config(ctx, "target", "board", "fw")
    config = from_config(ctx, "config", "build_config", "fw")
    sandbox = from_config(ctx, "sandbox", "sandbox", "fw")
    build_target = _resolve_build_target(target, sandbox)
    click.echo(f"Cleaning {target} ({config})...", err=True)
    elapsed = run_make(build_target, config, make_targets=["clean"], quiet=not verbose)
    click.echo(f"✓ Cleaned in {elapsed:.1f}s", err=True)


@cmd.command(name="targets")
@_sandbox_option
def list_targets(sandbox):
    """List valid targets for `dotbot fw build` (one per line)."""
    boards = SANDBOX_BOARDS if sandbox else BARE_TARGETS
    for t in sorted(boards):
        click.echo(t)


@cmd.command()
@_target_option
@_project_option
@_config_option
@click.option(
    "--source",
    "-S",
    "sources",
    type=click.Choice(SOURCES),
    multiple=True,
    help=(
        "Source to build (repeatable). Default: every source, or just "
        "dotbot-firmware with --app. Checkouts: DOTBOT_FIRMWARE_REPO / "
        "[fw].firmware_repo and DOTBOT_SWARMIT_REPO / [fw].swarmit_repo, "
        "a relative config path resolving against the config file, "
        "defaulting to repos/<name> next to the config file."
    ),
)
@_sandbox_option
@click.option(
    "--bare",
    is_flag=True,
    default=False,
    help="dotbot-firmware: bare apps only. Default: bare and sandbox apps.",
)
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Force full rebuild (pass `-rebuild` to emBuild). Default: incremental.",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help=(
        "Collect everything into this directory. Default: "
        f"{DEFAULT_ARTIFACTS_DISPLAY}/<source>-local/."
    ),
)
@click.option(
    "--print-path",
    is_flag=True,
    default=False,
    help="Print where each artifact would be collected, without building.",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
@click.pass_context
def artifacts(
    ctx,
    target,
    project,
    config,
    sources,
    sandbox,
    bare,
    rebuild,
    out_dir,
    print_path,
    verbose,
):
    """Build a release's firmware set from local checkouts into the cache.

    Collects into ``<cache>/<source>-local/`` under the release file names,
    so `device flash`, `swarm flash` and `-f local` find them alongside
    fetched releases. dotbot-firmware builds the apps its release ships for
    the board (bare and sandbox); swarmit builds the bootloader for the
    board, the network core and the Mari gateway from its mari submodule.
    """
    from dotbot.cli import _fw_sources as fs

    target = from_config(ctx, "target", "board", "fw")
    config = from_config(ctx, "config", "build_config", "fw")
    sandbox = from_config(ctx, "sandbox", "sandbox", "fw")
    if sandbox and bare:
        raise click.ClickException("--sandbox and --bare are mutually exclusive.")
    explicit = bool(sources)
    if not sources:
        sources = ("dotbot-firmware",) if project else SOURCES
    if project and "dotbot-firmware" not in sources:
        raise click.ClickException("--app names a dotbot-firmware app.")

    planned: list[tuple[str, list[Path], object]] = []
    for source in sources:
        if source == "swarmit":
            if target not in fs.SWARMIT_BOARDS:
                msg = f"swarmit has no bootloader for board {target!r}"
                if explicit:
                    raise click.ClickException(msg + ".")
                click.echo(f"[skip] {msg}", err=True)
                continue
            repo = _fw_helpers.resolve_swarmit_repo()
            files = [s.cwd / s.output for s in fs.swarmit_steps(repo, target, config)]
            planned.append((source, files, None))
            continue
        if sandbox:
            flavors = ["sandbox"]
        elif bare:
            flavors = ["bare"]
        else:
            flavors = [f for f in fs.FLAVORS if fs.flavor_supports(target, f)]
        for flavor in flavors:
            _resolve_build_target(target, flavor == "sandbox")
        plan = fs.dotbot_firmware_plan(target, flavors, project)
        planned.append((source, fs.dotbot_firmware_outputs(plan, config), plan))

    root = artifacts_dir()

    def dest(source):
        return Path(out_dir).resolve() if out_dir else fs.local_dir(source, root)

    if print_path:
        for source, files, _ in planned:
            for f in files:
                click.echo(str(dest(source) / f.name))
        return

    mode = "rebuild" if rebuild else "incremental"
    copied: list[Path] = []
    t0 = time.perf_counter()
    for source, files, plan in planned:
        click.echo(f"Building {source} for {target} ({config}, {mode})...", err=True)
        if source == "swarmit":
            files = fs.build_swarmit(target, config, rebuild=rebuild, verbose=verbose)
        else:
            files = fs.build_dotbot_firmware(
                plan, config, rebuild=rebuild, verbose=verbose
            )
        out = dest(source)
        copied += fs.collect(files, out)
        echo_artifact_path(out, action="collected into")
    elapsed = time.perf_counter() - t0
    click.echo(f"✓ Collected {len(copied)} artifact(s) in {elapsed:.1f}s", err=True)
    for p in copied:
        click.echo(str(p))


@cmd.command()
@click.option(
    "--source",
    "-S",
    type=click.Choice(list(("swarmit", "dotbot-firmware"))),
    default=None,
    help="Limit to one source (default: fetch the pinned version from all sources).",
)
@click.option(
    "--fw-version",
    "-f",
    default=None,
    help="Override the pinned version for --source: a release tag, 'latest', or 'local'.",
)
@click.option(
    "--local-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    help="Root of a local build tree (with --source <src> --fw-version local).",
)
def fetch(source, fw_version, local_root):
    """Download firmware into ~/.dotbot/artifacts/<source>-<version>/.

    With no flags, fetches the exact release this pydotbot is pinned to, from
    every source: swarmit (swarm system images, version inferred from the
    installed swarmit package) and DotBot-firmware (bare + sandbox apps, the
    version pydotbot is tested against). The two version independently, so
    overriding with -f requires a --source - pass `-f latest` for the newest
    release or `-f <tag>` for a specific one.
    """
    from dotbot import pydotbot_version
    from dotbot.firmware.fetch import (
        DEFAULT_FETCH_SOURCES,
        _short_path,
        fetch_assets,
        pinned_version,
    )

    if fw_version is not None and source is None:
        raise click.ClickException(
            "Pass --source with -f/--fw-version: swarmit and dotbot-firmware "
            "version independently."
        )
    sources = [source] if source else list(DEFAULT_FETCH_SOURCES)
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
        fetched.append(fetch_assets(src, version, artifacts_dir(), local_root))
    click.echo("\nDone. Firmware fetched into:")
    for path in fetched:
        click.echo(f"  {_short_path(path)}")


@cmd.command(name="list")
def list_artifacts():
    """List firmware artifacts cached in ~/.dotbot/artifacts/."""
    root = artifacts_dir()
    echo_artifact_path(root, action="listing")
    if not root.is_dir():
        click.echo(
            "(nothing cached yet — run `dotbot fw fetch` or `dotbot fw artifacts`)"
        )
        return
    found = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix in (".hex", ".bin")
    )
    if not found:
        click.echo("(empty)")
        return
    for p in found:
        click.echo(str(p.relative_to(root)))


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
