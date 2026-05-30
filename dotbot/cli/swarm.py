# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` — fleet operations over the air (status/start/stop/flash/...).

Mounts the upstream `swarmit` Click group as the `dotbot swarm` parent:
operators get `status|start|stop|flash|monitor|reset|message|calibrate-lh2|
serve` with their existing flags. `swarm` is strictly the *many-devices,
over-the-radio* namespace.

Single-device, cabled operations moved out: firmware-artifact build/fetch/
list live under `dotbot fw`, and per-device flashing/inspection (including
what used to be `swarm provision …`) lives under `dotbot device`.
"""

from dotbot.cli._lazy import lazy_subcommand


def _load_swarmit_group():
    from swarmit.cli.main import main as swarmit_group

    return swarmit_group


cmd = lazy_subcommand(
    name="swarm",
    extra="swarm",
    package="swarmit",
    help=(
        "Fleet ops over the air: status, start/stop, OTA-flash, monitor, "
        "reset, calibrate-lh2. Wraps swarmit."
    ),
    loader=_load_swarmit_group,
)
