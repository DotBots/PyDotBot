# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Config -> swarmit argument injection for `dotbot swarm`.

`dotbot swarm` wraps swarmit's own CLI, which does not read the unified dotbot
config. This translates the resolved `conn` / `swarm_id` into swarmit's flags at
the mount boundary, so a saved `dotbot.toml` drives the fleet like every other
command - while an explicit swarmit flag still wins (swarmit's own precedence is
CLI flag > config file).

Kept separate from `swarm.py` so it imports without pulling in swarmit, whose
protocol registry collides with PyDotBot's inside a shared test process.
"""

from typing import Optional, Sequence

import click

_HELP_FLAGS = ("-h", "--help")


def _option(group: click.Group, name: str) -> Optional[click.Option]:
    for param in group.params:
        if (
            isinstance(param, click.Option)
            and name in param.opts + param.secondary_opts
        ):
            return param
    return None


def _takes_value(option: Optional[click.Option]) -> bool:
    return option is not None and not option.is_flag and not option.count


def _scan(args: Sequence[str], group: click.Group) -> tuple[Optional[int], dict]:
    """Where the subcommand name sits in `args`, and the values `group`'s own
    options were given before it, keyed by parameter name (last one wins, as
    in Click). Short clusters (`-vn URL`, `-sA001`) are read the way Click
    reads them.
    """
    values: dict = {}
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            return (i + 1 if i + 1 < len(args) else None), values
        if tok.startswith("--"):
            name, eq, attached = tok.partition("=")
            option = _option(group, name)
            if _takes_value(option):
                if eq:
                    values[option.name] = attached
                elif i + 1 < len(args):
                    i += 1
                    values[option.name] = args[i]
        elif tok.startswith("-") and len(tok) > 1:
            # A value-taking letter consumes the rest of the token, or the
            # next token.
            for pos in range(1, len(tok)):
                option = _option(group, "-" + tok[pos])
                if _takes_value(option):
                    if pos < len(tok) - 1:
                        values[option.name] = tok[pos + 1 :]
                    elif i + 1 < len(args):
                        i += 1
                        values[option.name] = args[i]
                    break
        else:
            return i, values
        i += 1
    return None, values


def subcommand_index(args: Sequence[str], group: click.Group) -> Optional[int]:
    """Index of the subcommand name in `args`, skipping `group`'s own options.

    Everything before it is a group option (with its value); everything after
    belongs to the subcommand. None when no subcommand is given.
    """
    return _scan(args, group)[0]


def group_options(args: Sequence[str], group: click.Group) -> dict:
    """The values given to `group`'s own options, by parameter name."""
    return _scan(args, group)[1]


def swarm_connection(obj: Optional[dict]) -> tuple:
    """The `[swarm]` conn and swarm id, each a `Resolved`, the active site's
    `[connection]` included."""
    from types import SimpleNamespace

    from dotbot.cli._site import active_site, config_label
    from dotbot.config import resolve_source

    obj = obj if obj is not None else {}
    site = active_site(SimpleNamespace(obj=obj)).layer
    return tuple(
        resolve_source(
            key,
            section="swarm",
            config=obj.get("config"),
            config_label=config_label(obj.get("config_path")),
            site=site,
        )
        for key in ("conn", "swarm_id")
    )


def inject_config(args: Sequence[str], obj: Optional[dict], group: click.Group) -> list:
    """Prepend `--conn` / `--swarm-id` from the resolved config to `args`.

    No-op when `--help` appears anywhere, when the group options already carry
    `--conn` / `--swarm-id` / `-c` (those win), or when no config supplies the
    value. Only the group options are checked, since a subcommand may reuse the
    same short letters (`flash -s` is `--start`). Injected flags go first so
    swarmit parses them as group options ahead of the subcommand.
    """
    args = list(args)
    given = group_options(args, group)
    if any(arg in _HELP_FLAGS for arg in args) or "config_path" in given:
        return args

    conn, swarm_id = (item.value for item in swarm_connection(obj))
    injected: list = []
    if conn and "conn" not in given:
        injected += ["--conn", str(conn)]
    if swarm_id and "swarm_id" not in given:
        injected += ["--swarm-id", str(swarm_id)]
    return injected + args
