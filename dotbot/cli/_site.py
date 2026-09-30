# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Which site this session works in, and what it brings along.

A site names a place and its coordinate frame, so it is read across
namespaces - `swarm calibrate-lh2 collect` writes into it, `push` and
`run controller --lh2-calibration` look an id up under it - and resolves as a
top-level config key. Its `[connection]` table is the lowest config layer for
`conn` and `swarm_id`. The package default is deliberately neutral: a real
site is named by the config, never by PyDotBot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import click

from dotbot.config import ConfigError, Resolved, SiteLayer
from dotbot.site import SITE_DEFAULT, Site
from dotbot.site_packs import SiteEntry, broker_trust, resolve_site_entry

SITE_ENV = "DOTBOT_SITE"
# Where the root group caches the active site, when no --site names another
_ACTIVE = "active_site"


def config_label(config_path: Path | None) -> str:
    """How a source line names the config file: its file name."""
    return config_path.name if config_path is not None else "the config file"


def resolve_site_name(
    config: Any = None,
    flag: str | None = None,
    environ: Mapping[str, str] = os.environ,
    config_path: Path | None = None,
) -> tuple[str, str]:
    """The active site's name and the layer it came from.

    `--site` > `DOTBOT_SITE` > the config's `site` > the package default.
    """
    if flag:
        return flag, "--site"
    raw = environ.get(SITE_ENV)
    if raw:
        return raw, SITE_ENV
    value = getattr(config, "site", None)
    if value:
        return value, config_label(config_path)
    return SITE_DEFAULT, "the default"


@dataclass(frozen=True)
class ActiveSite:
    """The site a command works in: its name, where the name came from, and
    its table or pack (None when nothing defines it)."""

    name: str
    source: str
    entry: SiteEntry | None

    @property
    def layer(self) -> SiteLayer:
        if self.entry is None:
            return SiteLayer(self.name)
        trust, distrust = broker_trust(self.entry)
        return SiteLayer(self.name, self.entry.table.connection, trust, distrust)

    def site(self) -> Site:
        return self.entry.site() if self.entry is not None else Site(name=self.name)


def active_site(ctx: Any, flag: str | None = None) -> ActiveSite:
    """The active site, from the config the root group stashed on `ctx.obj`:
    its inline table, else a site pack of that name."""
    obj = ctx.obj if isinstance(getattr(ctx, "obj", None), dict) else {}
    if flag is None and _ACTIVE in obj:
        return obj[_ACTIVE]
    config = obj.get("config")
    config_path = obj.get("config_path")
    name, source = resolve_site_name(config, flag=flag, config_path=config_path)
    try:
        entry = resolve_site_entry(config, config_path, name)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    active = ActiveSite(name, source, entry)
    if flag is None and isinstance(getattr(ctx, "obj", None), dict):
        obj[_ACTIVE] = active
    return active


def site_from_context(ctx: Any, flag: str | None = None) -> tuple[Site, str]:
    """The active site and where its name came from."""
    active = active_site(ctx, flag)
    entry = active.entry
    if entry is not None and entry.shadows is not None:
        click.echo(
            f"note: the inline [sites.{active.name}] table shadows the site "
            f"pack at {entry.shadows}",
            err=True,
        )
    return active.site(), active.source


def connection_banner(
    site: ActiveSite, conn: Resolved, swarm_id: Resolved | None = None
) -> str:
    """One line naming the site, conn and swarm id a command acts on, and
    where each came from."""
    parts = [f"site {site.name} ({site.source})"]
    if conn.value is not None:
        parts.append(f"conn {conn.value} ({conn.source})")
    if swarm_id is not None and swarm_id.value is not None:
        parts.append(f"swarm {swarm_id.value} ({swarm_id.source})")
    return ", ".join(parts)


def missing_swarm_message(conn: Resolved, site: ActiveSite) -> str:
    """The error for an MQTT conn with no swarm id."""
    if conn.kind == "site":
        return f"site {site.name} names no swarm; set --swarm-id or DOTBOT_SWARM_ID"
    return (
        f"--conn {conn.value} needs --swarm-id: the broker carries multiple "
        "swarms; --swarm-id selects yours."
    )
