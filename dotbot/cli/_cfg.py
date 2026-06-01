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

from dotbot.config import resolve


def from_config(ctx: click.Context, param_name: str, key: str, section: str):
    """CLI flag if given on the command line, else config > env > the option's default.

    `param_name` is the Click parameter name (what `ctx.params` keys on);
    `key` / `section` address the value in the config resolver. When the
    option was set on the command line we return it verbatim; otherwise we let
    the resolver fall through config (section > deployment > top-level) and env,
    using the option's current value as the built-in default.
    """
    value = ctx.params.get(param_name)
    if ctx.get_parameter_source(param_name) is click.core.ParameterSource.COMMANDLINE:
        return value
    obj = ctx.obj or {}
    return resolve(
        key,
        section=section,
        config=obj.get("config"),
        deployment=obj.get("deployment"),
        default=value,
    )
