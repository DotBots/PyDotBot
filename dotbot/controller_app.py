# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import asyncio
import os
import sys

import click
import serial
import toml

from dotbot import (
    CONTROLLER_HTTP_PORT_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    MAP_SIZE_DEFAULT,
    SIMULATOR_INIT_STATE_DEFAULT,
    pydotbot_version,
)
from dotbot.cli._conn import ConnError, needs_swarm_id, parse_connection
from dotbot.controller import Controller, ControllerSettings
from dotbot.logger import setup_logging

# Old transport/identity config keys replaced by `conn` / `swarm_id`.
# Present-in-config triggers a warning and is dropped.
_LEGACY_TOML_KEYS = {
    "adapter",
    "mqtt_host",
    "mqtt_port",
    "mqtt_use_tls",
    "network_id",
    "swarmit_network_id",
    "port",
    "baudrate",
}


def _conn_to_settings(conn, swarm_id, sim_is_dotbot):
    """Map `--conn` + `--swarm-id` into internal ControllerSettings fields.

    The internal `adapter` enum (`cloud`/`edge`/`dotbot-simulator`/…) is
    an implementation detail; the CLI only ever sees `--conn`. Broker
    credentials come from the environment (`DOTBOT_MQTT_USER` /
    `DOTBOT_MQTT_PASS`), never the URL or a flag.

    Raises `click.ClickException` for a malformed `--conn` or a missing
    `--swarm-id` on an mqtt connection.
    """
    if conn is None:
        raise click.ClickException(
            "no connection given. Pass --conn (-n) with one of:\n"
            "  mqtts://host:port   (an MQTT broker; also needs --swarm-id)\n"
            "  /dev/ttyACM0        (a serial gateway)\n"
            "  simulator           (no hardware)"
        )
    try:
        parsed = parse_connection(conn)
    except ConnError as exc:
        raise click.ClickException(str(exc)) from exc

    if needs_swarm_id(parsed) and not swarm_id:
        raise click.ClickException(
            f"--conn {conn} needs --swarm-id: the broker carries multiple "
            "swarms; --swarm-id selects yours."
        )

    if parsed.kind == "mqtt":
        settings = {
            "adapter": "cloud",
            "mqtt_host": parsed.host,
            "mqtt_port": parsed.port,
            "mqtt_use_tls": parsed.use_tls,
            "mqtt_username": os.environ.get("DOTBOT_MQTT_USER"),
            "mqtt_password": os.environ.get("DOTBOT_MQTT_PASS"),
        }
        if swarm_id:
            settings["network_id"] = swarm_id
        return settings
    if parsed.kind == "serial":
        settings = {"adapter": "edge", "port": parsed.serial_port}
        if swarm_id:
            settings["network_id"] = swarm_id
        return settings
    # simulator
    return {"adapter": "dotbot-simulator" if sim_is_dotbot else "sailbot-simulator"}


@click.command()
@click.option(
    "-n",
    "--conn",
    "--connection",
    "conn",
    type=str,
    help=(
        "Connection to the swarm — one discriminated string: an MQTT "
        "broker `mqtts://host:port`, a serial device path `/dev/ttyACM0`, "
        "or `simulator`."
    ),
)
@click.option(
    "-s",
    "--swarm-id",
    "swarm_id",
    type=str,
    help=(
        "Swarm id in hex. Required for an mqtt connection (the broker "
        "carries many swarms); ignored for serial/simulator."
    ),
)
@click.option(
    "--dotbot/--sailbot",
    "sim_is_dotbot",
    default=True,
    help="With `--conn simulator`: which robot to simulate. Default: --dotbot.",
)
@click.option(
    "-g",
    "--gw-address",
    type=str,
    help=f"Gateway address in hex. Defaults to {GATEWAY_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "--controller-http-port",
    type=int,
    help=f"Controller HTTP port of the REST API. Defaults to '{CONTROLLER_HTTP_PORT_DEFAULT}'",
)
@click.option(
    "-w",
    "--webbrowser/--no-webbrowser",
    default=None,
    help="Open a web browser automatically",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Run in verbose mode (all payloads received are printed in terminal)",
)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"]),
    help="Logging level. Defaults to info",
)
@click.option(
    "--log-output",
    type=click.Path(),
    help="Filename where logs are redirected",
)
@click.option(
    "--csv-data-output",
    type=click.Path(),
    help="Filename where CSV data logs are stored. If not set, CSV data logging is disabled.",
)
@click.option(
    "--config-path",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a .toml configuration file.",
)
@click.option(
    "-m",
    "--map-size",
    type=str,
    help=f"Map size in mm. Defaults to '{MAP_SIZE_DEFAULT}'",
)
@click.option(
    "-M",
    "--background-map",
    type=click.Path(exists=True, dir_okay=False),
    help=(
        f"Path to a background map image file in png format. The image should"
        "be a top-down view of the environment, with 1024 pixels width and a "
        "height proportional to the real map size. The map size should be set "
        f"with the --map-size option (default: {MAP_SIZE_DEFAULT})."
    ),
)
@click.option(
    "--simulator-init-state",
    type=click.Path(dir_okay=False),
    help=f"Path to the simulator initial state .toml file. Defaults to '{SIMULATOR_INIT_STATE_DEFAULT}'.",
)
def main(
    conn,
    swarm_id,
    sim_is_dotbot,
    gw_address,
    controller_http_port,
    map_size,
    background_map,
    simulator_init_state,
    webbrowser,
    verbose,
    log_level,
    log_output,
    csv_data_output,
    config_path,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    # The priority order is CLI > ConfigFile (optional) > Defaults.
    # The config file may carry `conn` / `swarm_id` too; CLI wins.
    file_data = {}
    if config_path:
        file_data = toml.load(config_path)

    conn = conn if conn is not None else file_data.get("conn")
    swarm_id = swarm_id if swarm_id is not None else file_data.get("swarm_id")

    # Warn (and drop) legacy transport keys in a config file — they're
    # superseded by `conn` / `swarm_id` and silently flowing them through
    # would mask a stale config.
    legacy = sorted(_LEGACY_TOML_KEYS & set(file_data))
    if legacy:
        click.echo(
            f"warning: ignoring legacy config key(s) {legacy}; "
            "use `conn` and `swarm_id` instead.",
            err=True,
        )

    # Translate the single `--conn` connection string into the internal
    # adapter + transport settings. The internal `adapter` enum stays an
    # implementation detail — the CLI never exposes it.
    conn_settings = _conn_to_settings(conn, swarm_id, sim_is_dotbot)

    cli_args = {
        "gw_address": gw_address,
        "controller_http_port": controller_http_port,
        "map_size": map_size,
        "background_map": background_map,
        "simulator_init_state": simulator_init_state,
        "webbrowser": webbrowser,
        "verbose": verbose,
        "log_level": log_level,
        "log_output": log_output,
        "csv_data_output": csv_data_output,
    }

    # Settings precedence: defaults < config-file (non-conn/legacy keys) <
    # conn translation < other CLI flags.
    dropped = _LEGACY_TOML_KEYS | {"conn", "swarm_id"}
    data = {k: v for k, v in file_data.items() if k not in dropped}
    data.update(conn_settings)
    data.update({k: v for k, v in cli_args.items() if v is not None})

    controller_settings = ControllerSettings(**data)

    setup_logging(
        controller_settings.log_output,
        controller_settings.log_level,
        ["console", "file"],
    )
    try:
        controller = Controller(controller_settings)
        asyncio.run(controller.run())
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
