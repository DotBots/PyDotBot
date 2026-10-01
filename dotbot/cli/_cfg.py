# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Bridge between a Click command's options and the unified config resolver.

Phase 3 wiring: `fw` / `device` options read their defaults from the loaded
config (stashed on `ctx.obj` by the root group), while an explicit flag on
the command line still wins. The trick is Click's parameter-source check: an
option whose value came from `COMMANDLINE` is a real user choice and beats
the file; an option still sitting at its built-in default yields to the
config/env layers.

Keeping this in one helper means every command resolves identically, and the
no-config common case stays byte-for-byte the same as before (the option's
own default flows straight through `resolve(..., default=value)`).
"""

import click

from dotbot.config import CONNECTION_KEYS, Resolved, resolve_source


def on_commandline(ctx: click.Context, param_name: str) -> bool:
    """True if the user typed `param_name` on the command line."""
    return (
        ctx.get_parameter_source(param_name) is click.core.ParameterSource.COMMANDLINE
    )


def _flag_name(ctx: click.Context, param_name: str) -> str:
    for param in ctx.command.params:
        if param.name == param_name and isinstance(param, click.Option):
            return max(param.opts, key=len)
    return "the command line"


def resolved_from_config(
    ctx: click.Context,
    param_name: str,
    key: str,
    section: str | None,
    default=None,
    site_flag: str | None = None,
) -> Resolved:
    """`from_config`, with the layer the value came from.

    For `conn` and `swarm_id` the active site's `[connection]` is the lowest
    config layer; `site_flag` is the command's `--site`, if it has one.
    """
    value = ctx.params.get(param_name)
    obj = ctx.obj or {}
    flag = value if on_commandline(ctx, param_name) else None
    site = None
    if key in CONNECTION_KEYS:
        from dotbot.cli._site import active_site

        site = active_site(ctx, site_flag).layer
    return resolve_source(
        key,
        section=section,
        flag=flag,
        flag_name=_flag_name(ctx, param_name),
        config=obj.get("config"),
        site=site,
        default=default if value is None else value,
    )


def from_config(
    ctx: click.Context,
    param_name: str,
    key: str,
    section: str | None,
    default=None,
    site_flag: str | None = None,
):
    """CLI flag if given on the command line, else env > config > the option's default.

    `param_name` is the Click parameter name (what `ctx.params` keys on);
    `key` / `section` address the value in the config resolver. An option
    still at its built-in default yields to the env and config layers, with
    that value as the resolver's default; `default` stands in when the value
    is None, so a tri-state flag still resolves (and coerces env strings) to
    its real type.
    """
    return resolved_from_config(ctx, param_name, key, section, default, site_flag).value
