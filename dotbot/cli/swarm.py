# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` — provision, OTA-flash, start/stop/monitor.

Mounts the upstream `swarmit` Click group as the `dotbot swarm`
parent (operators get `status|start|stop|flash|monitor|reset|message|
calibrate-lh2` with their existing flags). swarmit stays external for
now — folding it is Track A Phase 6.

The `provision` subcommand is mounted from the in-tree
`dotbot.provision` package (folded in Phase 2). Provision's runtime
dep `intelhex` is gated behind `pip install dotbot[provision]`; if
intelhex is missing, invoking provision-dependent paths raises a
ClickException with a clear message (the package itself imports
cleanly thanks to a try/except around the intelhex import).
"""

from dotbot.cli._lazy import lazy_subcommand


def _load_swarmit_group():
    from swarmit.cli.main import main as swarmit_group

    return swarmit_group


def _load_provision_group():
    from dotbot.provision.cli import cli as provision_group

    return provision_group


def _load_sandbox_fw_group():
    from dotbot.cli._sandbox_fw import cmd as sandbox_fw_group

    return sandbox_fw_group


cmd = lazy_subcommand(
    name="swarm",
    extra="swarm",
    package="swarmit",
    help=(
        "Swarm-orchestration ops: provision, status, start/stop/monitor, "
        "OTA-flash, sandbox firmware build. Wraps swarmit + in-tree "
        "dotbot.provision + dotbot.cli._sandbox_fw."
    ),
    loader=_load_swarmit_group,
)

# Mount in-tree provision + sandbox-fw as subgroups of swarm. The
# imports are unconditional — neither module pulls in optional runtime
# deps at module-import time.
if hasattr(cmd, "commands"):
    try:
        cmd.add_command(_load_provision_group(), name="provision")
    except Exception:  # pylint: disable=broad-except
        # Defensive: if for some reason dotbot.provision fails to import
        # (unlikely — it's now in-tree), the swarm CLI still works
        # without provision.
        pass
    try:
        cmd.add_command(_load_sandbox_fw_group(), name="fw")
    except Exception:  # pylint: disable=broad-except
        pass
