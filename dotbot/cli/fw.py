# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot fw` — firmware artifacts: build, fetch, list, make.

`fw` is the *artifacts* namespace — it produces or downloads firmware
files. It never touches hardware: flashing a device lives under `fw`'s
sibling `dotbot device`, and OTA-flashing the fleet under `dotbot swarm`.

- `build` compiles from source via SES (`emBuild`) in `DotBot-firmware`,
  leaving the result in the SES `Output/.../Exe/` tree and echoing that
  path — it does *not* copy into `./artifacts/`. Bare apps by default;
  `--sandbox` builds the TrustZone NS flavor (`sandbox-<board>`, `.bin`).
- `artifacts` builds *and* collects the result into `./artifacts/`, with
  the flat `<app>-<board>.hex` / `<app>-sandbox-<board>.bin` names.
- `fetch` downloads a published release into `./artifacts/<version>/`.
- `list` shows what's cached in `./artifacts/`.
- `make` is the low-level escape hatch: it forwards arbitrary arguments
  to `make` in the firmware repo (workspace-resolved SEGGER_DIR) for the
  Makefile knobs `build` deliberately doesn't model.

Only `artifacts` and `fetch` populate `./artifacts/`. The device-flash
commands then auto-resolve their input, by *different* rules: `dotbot
device flash <app>` resolves an app image present-in-`./artifacts/` →
build-from-source → error (it never fetches); `device flash-swarmit-sandbox`
/ `flash-mari-gateway` resolve a release's system firmware
present-in-`./artifacts/` → fetch (they never build).
"""

import sys
from pathlib import Path

import click

from dotbot.cli._artifacts import artifacts_dir, echo_artifact_path
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
        "Firmware artifacts: build (from source via SES), fetch (a release), "
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
    help="Show full SES `-verbose -echo` output.",
)
def build(target, project, config, sandbox, rebuild, verbose):
    """Build firmware from source (default target: dotbot-v3)."""
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
def clean(target, config, sandbox, verbose):
    """Clean SES build outputs (default target: dotbot-v3)."""
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
@_sandbox_option
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Where to collect artifacts. Default: ./artifacts/ (your CWD).",
)
@click.option(
    "--print-path",
    is_flag=True,
    default=False,
    help="Print where the artifact lives without building.",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def artifacts(target, project, config, sandbox, out_dir, print_path, verbose):
    """Build + collect artifacts into ./artifacts/ (default)."""
    import shutil

    build_target = _resolve_build_target(target, sandbox)
    if print_path:
        if not project:
            raise click.ClickException(
                "`--print-path` requires `--app NAME` — there is no canonical "
                "artifact path without a specific project."
            )
        click.echo(str(artifact_path(build_target, project, config)))
        return
    out = Path(out_dir).resolve() if out_dir else artifacts_dir()
    click.echo(
        f"Building + collecting artifacts for {target} ({config}) → {out}/...",
        err=True,
    )
    # Force a full rebuild: bare and sandbox share the SES Output dir per
    # board (`$(BuildTarget)`), so incremental can pick up stale objects
    # from the other flavor and link-error.
    elapsed = run_make(build_target, config, project, rebuild=True, quiet=not verbose)
    out.mkdir(parents=True, exist_ok=True)
    apps_to_collect = [project] if project else list_projects(build_target)
    copied = []
    for app in apps_to_collect:
        src = artifact_path(build_target, app, config)
        if src.is_file():
            dst = out / src.name
            shutil.copy2(src, dst)
            copied.append(dst)
    echo_artifact_path(out, action="collected into")
    click.echo(f"✓ Collected {len(copied)} artifact(s) in {elapsed:.1f}s", err=True)
    for p in copied:
        click.echo(str(p))


@cmd.command()
@click.option(
    "--fw-version", "-f", required=True, help="Release version tag, or 'local'."
)
@click.option(
    "--local-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    help="Root of a local DotBot-firmware/swarmit build (with --fw-version local).",
)
def fetch(fw_version, local_root):
    """Download a released firmware set into ./artifacts/<version>/."""
    from dotbot.firmware.flash import fetch_assets

    out = fetch_assets(fw_version, artifacts_dir(), local_root)
    echo_artifact_path(out, action="fetched into")


@cmd.command(name="list")
def list_artifacts():
    """List firmware artifacts cached in ./artifacts/."""
    root = artifacts_dir()
    echo_artifact_path(root, action="listing")
    if not root.is_dir():
        click.echo("(no ./artifacts/ yet — run `dotbot fw build` or `dotbot fw fetch`)")
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
