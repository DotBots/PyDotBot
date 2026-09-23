# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Build a swarmit client from a dotbot connection string.

The CLI and the controller both reach the fleet over the air through
swarmit, from the same `conn` / `swarm_id` pair. Reusing swarmit's own
conn-string translation keeps the two tools from drifting apart on what a
connection string means.

Imported lazily inside the builder: the swarmit protocol registry must not
load during PyDotBot test collection.
"""

from __future__ import annotations

from typing import Any

from dotbot.mqtt_tls import allow_unverified_broker


def build_swarmit_client(conn: str, swarm_id: str) -> Any:
    """A swarmit client over the whole swarm.

    Transport selection is swarmit's call: `build_client` probes for a
    running swarmit server and falls back to an in-process controller on its
    own, so there is nothing to choose here.

    swarmit connects while its controller is constructed, so certificate
    checking is settled before `build_client` is reached.
    """
    allow_unverified_broker()

    from swarmit.cli.main import DEFAULTS, _conn_to_config
    from swarmit.client import build_client
    from swarmit.testbed.controller import ControllerSettings

    final = {**DEFAULTS, **_conn_to_config(conn, swarm_id)}
    settings = ControllerSettings(
        serial_port=final["serial_port"],
        serial_baudrate=final["baudrate"],
        mqtt_host=final["mqtt_host"],
        mqtt_port=final["mqtt_port"],
        mqtt_use_tls=final["mqtt_use_tls"],
        mqtt_username=final.get("mqtt_username"),
        mqtt_password=final.get("mqtt_password"),
        network_id=int(final["swarmit_network_id"], 16),
        adapter=final["adapter"],
        devices=[],
        verbose=False,
    )
    return build_client(settings)


def conn_string(settings: Any) -> str:
    """The connection string that reproduces how a controller reached the swarm.

    Duck-typed on `ControllerSettings` so the server's display route and the
    calibration session derive it once, from the same fields.
    """
    if settings.adapter == "cloud":
        scheme = "mqtts" if settings.mqtt_use_tls else "mqtt"
        return f"{scheme}://{settings.mqtt_host}:{settings.mqtt_port}"
    if settings.adapter in ("dotbot-simulator", "sailbot-simulator"):
        return "simulator"
    return settings.port
