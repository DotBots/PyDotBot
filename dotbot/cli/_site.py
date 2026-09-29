# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Which site this session works in.

A site names a deployment and its coordinate frame, so it is read across
namespaces - `swarm calibrate-lh2 collect` writes into it, `push` and
`run controller --lh2-calibration` look an id up under it - and resolves as a
top-level config key next to `conn` and `swarm_id`. The package default is
deliberately neutral: a real site is named by the config, never by PyDotBot.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import click

from dotbot.config import ConfigError
from dotbot.site import SITE_DEFAULT, Site
from dotbot.site_packs import resolve_site_entry

SITE_ENV = "DOTBOT_SITE"


def resolve_site_name(
    config: Any = None,
    deployment: Any = None,
    flag: str | None = None,
    environ: Mapping[str, str] = os.environ,
) -> tuple[str, str]:
    """The active site's name and the layer it came from.

    `--site` > `DOTBOT_SITE` > the selected deployment's `site` > the
    top-level `site` > the package default.
    """
    if flag:
        return flag, "the command line"
    raw = environ.get(SITE_ENV)
    if raw:
        return raw, SITE_ENV
    for layer in (deployment, config):
        value = getattr(layer, "site", None)
        if value:
            return value, "the config file"
    return SITE_DEFAULT, "the default"


def site_from_context(ctx: Any, flag: str | None = None) -> tuple[Site, str]:
    """The active site, from the config the root group stashed on `ctx.obj`:
    its inline table, else a site pack of that name."""
    obj = ctx.obj or {}
    config = obj.get("config")
    name, source = resolve_site_name(
        config=config, deployment=obj.get("deployment"), flag=flag
    )
    try:
        entry = resolve_site_entry(config, obj.get("config_path"), name)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    if entry is None:
        return Site(name=name), source
    if entry.shadows is not None:
        click.echo(
            f"note: the inline [sites.{name}] table shadows the site pack at "
            f"{entry.shadows}",
            err=True,
        )
    return entry.site(), source
