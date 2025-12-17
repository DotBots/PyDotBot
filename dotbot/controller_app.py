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
from pydantic import BaseModel

from dotbot import (
    CONTROLLER_ADAPTER_DEFAULT,
    CONTROLLER_HTTP_PORT_DEFAULT,
    DOTBOT_ADDRESS_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    MQTT_HOST_DEFAULT,
    MQTT_PORT_DEFAULT,
    NETWORK_ID_DEFAULT,
    SERIAL_BAUDRATE_DEFAULT,
    SERIAL_PORT_DEFAULT,
    pydotbot_version,
)
from dotbot.controller import Controller, ControllerSettings
from dotbot.logger import setup_logging


class Config(BaseModel):
    adapter: str = CONTROLLER_ADAPTER_DEFAULT
    serial_port: str = SERIAL_PORT_DEFAULT
    baudrate: int = SERIAL_BAUDRATE_DEFAULT
    mqtt_host: str = MQTT_HOST_DEFAULT
    mqtt_port: int = MQTT_PORT_DEFAULT
    mqtt_use_tls: int = False
    dotbot_address: str = DOTBOT_ADDRESS_DEFAULT
    gateway_address: str = GATEWAY_ADDRESS_DEFAULT
    network_id: str = NETWORK_ID_DEFAULT
    controller_http_port: int = CONTROLLER_HTTP_PORT_DEFAULT
    webbrowser: bool = False
    verbose: bool = False
    log_level: str = "info"
    log_output: str = os.path.join(os.getcwd(), "pydotbot.log")


@click.command()
@click.option(
    "-a",
    "--adapter",
    type=click.Choice(["serial", "edge", "cloud"]),
    help=f"Controller interface adapter. Defaults to {CONTROLLER_ADAPTER_DEFAULT}",
)
@click.option(
    "-p",
    "--port",
    type=str,
    help=f"Serial port used by 'serial' and 'edge' adapters. Defaults to '{SERIAL_PORT_DEFAULT}'",
)
@click.option(
    "-b",
    "--baudrate",
    type=int,
    help=f"Serial baudrate used by 'serial' and 'edge' adapters. Defaults to {SERIAL_BAUDRATE_DEFAULT}",
)
@click.option(
    "-H",
    "--mqtt-host",
    type=str,
    help=f"MQTT host used by cloud adapter. Default: {MQTT_HOST_DEFAULT}.",
)
@click.option(
    "-P",
    "--mqtt-port",
    type=int,
    help=f"MQTT port used by cloud adapter. Default: {MQTT_PORT_DEFAULT}.",
)
@click.option(
    "-T",
    "--mqtt-use_tls",
    is_flag=True,
    help="Use TLS with MQTT (for cloud adapter).",
)
@click.option(
    "-d",
    "--dotbot-address",
    type=str,
    help=f"Address in hex of the DotBot to control. Defaults to {DOTBOT_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "-g",
    "--gw-address",
    type=str,
    help=f"Gateway address in hex. Defaults to {GATEWAY_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "-s",
    "--network-id",
    type=str,
    help=f"Network ID in hex. Defaults to {NETWORK_ID_DEFAULT:>0{4}}",
)
@click.option(
    "-c",
    "--controller-http-port",
    type=int,
    help=f"Controller HTTP port of the REST API. Defaults to '{CONTROLLER_HTTP_PORT_DEFAULT}'",
)
@click.option(
    "-w",
    "--webbrowser",
    is_flag=True,
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
    "-c",
    "--config-path",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a .toml configuration file.",
)
def main(
    adapter,
    port,
    baudrate,
    mqtt_host,
    mqtt_port,
    mqtt_use_tls,
    dotbot_address,
    gw_address,
    network_id,
    controller_http_port,
    webbrowser,
    verbose,
    log_level,
    log_output,
    config_path,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    # The priority order is CLI > ConfigFile (optional) > Defaults
    cli_args = {
        "adapter": adapter,
        "serial_port": port,
        "baudrate": baudrate,
        "mqtt_host": mqtt_host,
        "mqtt_port": mqtt_port,
        "mqtt_use_tls": mqtt_use_tls,
        "dotbot_address": dotbot_address,
        "gateway_address": gw_address,
        "network_id": network_id,
        "controller_http_port": controller_http_port,
        "webbrowser": webbrowser,
        "verbose": verbose,
        "log_level": log_level,
        "log_output": log_output,
    }

    data = {}
    if config_path:
        file_data = toml.load(config_path)
        data.update(file_data)

    data.update({k: v for k, v in cli_args.items() if v not in (None, False)})

    final_config = Config(**data)

    setup_logging(final_config.log_output, final_config.log_level, ["console", "file"])
    try:
        controller = Controller(
            ControllerSettings(
                adapter=final_config.adapter,
                port=final_config.serial_port,
                baudrate=final_config.baudrate,
                mqtt_host=final_config.mqtt_host,
                mqtt_port=final_config.mqtt_port,
                mqtt_use_tls=final_config.mqtt_use_tls,
                dotbot_address=final_config.dotbot_address,
                gw_address=final_config.gateway_address,
                network_id=final_config.network_id,
                controller_http_port=final_config.controller_http_port,
                webbrowser=final_config.webbrowser,
                verbose=final_config.verbose,
            ),
        )
        asyncio.run(controller.run())
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
