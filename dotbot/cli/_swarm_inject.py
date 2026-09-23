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

# swarmit's connection flags. Any of these means the user is steering the
# connection explicitly, so we leave their args untouched.
_CONN_FLAGS = ("-n", "--conn", "--connection")
_SWARM_ID_FLAGS = ("-s", "--swarm-id")
_CONFIG_FLAGS = ("-c", "--config-path")
_HELP_FLAGS = ("-h", "--help")


def _has_flag(args: Sequence[str], flags: Sequence[str]) -> bool:
    """True if any of `flags` appears in `args`, including `--flag=value` and
    an attached short value (`-sA001`)."""
    eqs = tuple(f + "=" for f in flags if f.startswith("--"))
    shorts = tuple(f for f in flags if not f.startswith("--"))
    return any(
        arg in flags
        or (eqs and arg.startswith(eqs))
        or (not arg.startswith("--") and arg.startswith(shorts))
        for arg in args
    )


def _takes_value(group: click.Group, name: str) -> bool:
    for param in group.params:
        if (
            isinstance(param, click.Option)
            and name in param.opts + param.secondary_opts
        ):
            return not param.is_flag and not param.count
    return False


def subcommand_index(args: Sequence[str], group: click.Group) -> Optional[int]:
    """Index of the subcommand name in `args`, skipping `group`'s own options.

    Everything before it is a group option (with its value); everything after
    belongs to the subcommand. None when no subcommand is given.
    """
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            return i + 1 if i + 1 < len(args) else None
        if tok.startswith("--"):
            if "=" not in tok and _takes_value(group, tok):
                i += 1
        elif tok.startswith("-") and len(tok) > 1:
            # A short cluster like `-vd ADDR` or `-sA001`: a value-taking
            # letter consumes the rest of the token, or the next token.
            for pos in range(1, len(tok)):
                if _takes_value(group, "-" + tok[pos]):
                    if pos == len(tok) - 1:
                        i += 1
                    break
        else:
            return i
        i += 1
    return None


def inject_config(args: Sequence[str], obj: Optional[dict], group: click.Group) -> list:
    """Prepend `--conn` / `--swarm-id` from the resolved config to `args`.

    No-op when `--help` appears anywhere, when the group options already carry
    `--conn` / `--swarm-id` / `-c` (those win), or when no config supplies the
    value. Only the group options are checked, since a subcommand may reuse the
    same short letters (`flash -s` is `--start`). Injected flags go first so
    swarmit parses them as group options ahead of the subcommand.
    """
    args = list(args)
    end = subcommand_index(args, group)
    group_args = args if end is None else args[:end]
    if any(arg in _HELP_FLAGS for arg in args) or _has_flag(group_args, _CONFIG_FLAGS):
        return args

    from dotbot.config import resolve

    obj = obj or {}
    config = obj.get("config")
    deployment = obj.get("deployment")
    injected: list = []
    conn = resolve("conn", section="swarm", config=config, deployment=deployment)
    swarm_id = resolve(
        "swarm_id", section="swarm", config=config, deployment=deployment
    )
    if conn and not _has_flag(group_args, _CONN_FLAGS):
        injected += ["--conn", str(conn)]
    if swarm_id and not _has_flag(group_args, _SWARM_ID_FLAGS):
        injected += ["--swarm-id", str(swarm_id)]
    return injected + args
