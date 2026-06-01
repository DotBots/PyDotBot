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

# swarmit's connection flags. Any of these means the user is steering the
# connection explicitly, so we leave their args untouched.
_CONN_FLAGS = ("-n", "--conn", "--connection")
_SWARM_ID_FLAGS = ("-s", "--swarm-id")
_CONFIG_FLAGS = ("-c", "--config-path")
_HELP_FLAGS = ("-h", "--help")


def _has_flag(args: Sequence[str], flags: Sequence[str]) -> bool:
    """True if any of `flags` (or its `--flag=value` form) appears in `args`."""
    eqs = tuple(f + "=" for f in flags if f.startswith("--"))
    return any(arg in flags or (eqs and arg.startswith(eqs)) for arg in args)


def inject_config(args: Sequence[str], obj: Optional[dict]) -> list:
    """Prepend `--conn` / `--swarm-id` from the resolved config to `args`.

    No-op when the user already passes a `--conn` / `--swarm-id` / `-c` flag or
    `--help` (those win), or when no config supplies the value. Injected flags
    go first so swarmit parses them as group options ahead of the subcommand.
    """
    args = list(args)
    if _has_flag(args, _HELP_FLAGS) or _has_flag(args, _CONFIG_FLAGS):
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
    if conn and not _has_flag(args, _CONN_FLAGS):
        injected += ["--conn", str(conn)]
    if swarm_id and not _has_flag(args, _SWARM_ID_FLAGS):
        injected += ["--swarm-id", str(swarm_id)]
    return injected + args
