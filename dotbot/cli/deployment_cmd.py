# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot deployment` - list / show / switch the configured deployments.

A deployment is one named physical deployment (Inria/100, La Poste/1000, ...)
defined by a `[deployment.<name>]` table in the config file. You *select* one
(`--deployment` / `DOTBOT_DEPLOYMENT` / `default_deployment`) per invocation;
`deployment use` writes the `default_deployment` for you, so switching is one
command rather than a hand edit. `list` / `show` are read-only inspectors.
"""

import re
import tomllib
from pathlib import Path

import click
import httpx
import tomlkit

from dotbot.config import (
    PROJECT_CONFIG_NAME,
    USER_CONFIG_PATH,
    ConfigError,
    discover_config_path,
    load_config_text,
)

# Where `deployment fetch` (no SOURCE) looks for the published registry. The
# `/releases/latest/download/` path 302-redirects to the newest release asset,
# so this URL is stable across republishes. Not published yet - Geovane owns it.
_DEFAULT_REGISTRY_URL = (
    "https://github.com/DotBots/deployments/releases/latest/download/deployments.toml"
)


@click.group(
    name="deployment",
    help="List / show deployments; switch the default with `use`, fetch published ones.",
)
def cmd():
    pass


# The descriptive fields worth showing inline, in display order.
_FIELDS = ("conn", "swarm_id", "serial_port", "location", "bots")


def _deployment_fields(deployment) -> list[tuple[str, object]]:
    """The (name, value) pairs that are actually set on a deployment."""
    return [
        (field, getattr(deployment, field))
        for field in _FIELDS
        if getattr(deployment, field) is not None
    ]


@cmd.command(name="list")
@click.pass_context
def list_deployments(ctx):
    """List configured deployment names, marking the active one (*)."""
    obj = ctx.obj or {}
    config = obj.get("config")
    active = obj.get("deployment_name")

    deployments = config.deployment if config is not None else {}
    if not deployments:
        click.echo("(no deployments configured)")
        return

    for name in sorted(deployments):
        marker = "* " if name == active else "  "
        click.echo(f"{marker}{name}")
        for field, value in _deployment_fields(deployments[name]):
            click.echo(f"      {field}: {value}")


@cmd.command()
@click.argument("name")
@click.pass_context
def show(ctx, name):
    """Print one deployment's fields. Errors if NAME isn't defined."""
    obj = ctx.obj or {}
    config = obj.get("config")

    deployments = config.deployment if config is not None else {}
    if name not in deployments:
        known = ", ".join(sorted(deployments)) or "(none defined)"
        raise click.ClickException(
            f"unknown deployment {name!r}; defined deployments: {known}"
        )

    active = obj.get("deployment_name")
    suffix = " (active)" if name == active else ""
    click.echo(f"{name}{suffix}")
    fields = _deployment_fields(deployments[name])
    if not fields:
        click.echo("  (no fields set)")
        return
    for field, value in fields:
        click.echo(f"  {field}: {value}")


# A `default_deployment = ...` line, active or commented-out, so `use` can
# rewrite it in place and leave everything else (comments included) intact.
_ACTIVE_DEFAULT_RE = re.compile(r"^\s*default_deployment\s*=")
_ANY_DEFAULT_RE = re.compile(r"^\s*#?\s*default_deployment\s*=")


def _set_default_deployment(path: Path, name: str) -> None:
    """Write `default_deployment = "<name>"` into `path`, preserving the rest.

    Replaces the existing `default_deployment` line (an active one first, else
    a commented-out one like the `config init` starter ships); when neither
    exists, inserts the key before the first `[table]` header so it stays a
    valid top-level TOML key.
    """
    new_line = f'default_deployment = "{name}"'
    lines = path.read_text().splitlines()

    active = [i for i, line in enumerate(lines) if _ACTIVE_DEFAULT_RE.match(line)]
    any_match = [i for i, line in enumerate(lines) if _ANY_DEFAULT_RE.match(line)]
    target = active[0] if active else (any_match[0] if any_match else None)

    if target is not None:
        lines[target] = new_line
    else:
        insert_at = next(
            (i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
            len(lines),
        )
        lines.insert(insert_at, new_line)
    path.write_text("\n".join(lines) + "\n")


@cmd.command()
@click.argument("name")
@click.pass_context
def use(ctx, name):
    """Set NAME as the default deployment, writing it to the active config file.

    Updates `default_deployment` in the file `dotbot` is currently using (the
    one `dotbot config path` reports), keeping the rest of the file - comments
    included - intact. NAME must be a defined `[deployment.<name>]`.
    """
    obj = ctx.obj or {}
    config = obj.get("config")
    config_path = obj.get("config_path")

    if config_path is None:
        raise click.ClickException(
            "no config file in use to write to; create one with "
            "`dotbot config init` (or point at one with `dotbot -c PATH`)."
        )
    deployments = config.deployment if config is not None else {}
    if name not in deployments:
        known = ", ".join(sorted(deployments)) or "(none defined)"
        raise click.ClickException(
            f"unknown deployment {name!r}; defined deployments: {known}"
        )

    _set_default_deployment(Path(config_path), name)
    click.echo(f"Set default deployment to {name!r} in {config_path}")


def _read_source(source: str) -> str:
    """Return the text of SOURCE - a local file path, or an http(s) URL."""
    if Path(source).is_file():
        return Path(source).read_text()
    if source.startswith(("http://", "https://")):
        try:
            response = httpx.get(source, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise click.ClickException(f"could not fetch {source}: {exc}") from exc
        return response.text
    raise click.ClickException(f"not a URL or an existing file: {source!r}")


def _merge_target(into: str) -> Path:
    """The file `fetch` writes into: the user config, or the project dotbot.toml."""
    if into == "project":
        found = discover_config_path(include_user_file=False)
        return found if found is not None else Path.cwd() / PROJECT_CONFIG_NAME
    return USER_CONFIG_PATH


def _diff_deployments(target: Path, fetched: dict) -> list[tuple[str, str]]:
    """Per-name status of fetched vs target: 'added' / 'changed' / 'same'."""
    existing = {}
    if target.is_file():
        existing = tomllib.loads(target.read_text()).get("deployment", {})
    changes = []
    for name in sorted(fetched):
        new_fields = fetched[name].model_dump(exclude_none=True)
        old = existing.get(name)
        if old is None:
            changes.append((name, "added"))
        elif old == new_fields:
            changes.append((name, "same"))
        else:
            changes.append((name, "changed"))
    return changes


def _write_deployments(target: Path, fetched: dict, changes: list) -> None:
    """Upsert the added/changed `[deployment.*]` tables, preserving everything else.

    Uses tomlkit so a hand-edited target keeps its comments, other deployments,
    and `[fw]`/`[device]`/`[swarm]`/`[run]` sections; only the named tables that
    actually changed are replaced.
    """
    if target.is_file():
        doc = tomlkit.parse(target.read_text())
    else:
        doc = tomlkit.document()
        doc.add(
            tomlkit.comment(
                " DotBot deployments - managed by `dotbot deployment fetch`."
            )
        )
    deployments = doc.get("deployment")
    if deployments is None:
        deployments = tomlkit.table(is_super_table=True)
        doc["deployment"] = deployments

    status_by_name = dict(changes)
    for name in sorted(fetched):
        if status_by_name.get(name) == "same":
            continue
        table = tomlkit.table()
        for key, value in fetched[name].model_dump(exclude_none=True).items():
            table[key] = value
        deployments[name] = table

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tomlkit.dumps(doc))


@cmd.command()
@click.argument("source", required=False)
@click.option(
    "--into",
    type=click.Choice(["user", "project"]),
    default="user",
    help="Which file to write into (default: your ~/.dotbot/config.toml).",
)
@click.option("--dry-run", is_flag=True, help="Show what would change; write nothing.")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't prompt before replacing an existing deployment.",
)
def fetch(source, into, dry_run, yes):
    """Fetch published deployments and merge them into your config.

    SOURCE is a URL or a local file holding `[deployment.*]` tables; with no
    SOURCE the built-in DotBots registry is used. Existing deployments of the
    same name are replaced (you are asked first); everything else in the file -
    other deployments, sections, comments - is left intact. Like `fw fetch`,
    this only acquires: select one with `dotbot deployment use` / `--deployment`.
    """
    source = source or _DEFAULT_REGISTRY_URL
    text = _read_source(source)
    try:
        config = load_config_text(text, source=source)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    fetched = config.deployment
    if not fetched:
        raise click.ClickException(f"no [deployment.*] tables found in {source}")

    target = _merge_target(into)
    changes = _diff_deployments(target, fetched)

    symbol = {"added": "+", "changed": "~", "same": "="}
    for name, status in changes:
        click.echo(f"  {symbol[status]} {name}")

    if all(status == "same" for _, status in changes):
        click.echo(f"Already up to date; {target} unchanged.")
        return
    if dry_run:
        click.echo(f"(dry run; {target} unchanged)")
        return

    changed = [name for name, status in changes if status == "changed"]
    if changed and not yes:
        click.confirm(
            f"This replaces {len(changed)} existing deployment(s) "
            f"({', '.join(changed)}) in {target}. Continue?",
            abort=True,
        )

    _write_deployments(target, fetched, changes)
    written = sum(1 for _, status in changes if status != "same")
    click.echo(f"Wrote {written} deployment(s) to {target}")
