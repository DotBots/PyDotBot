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


@click.command()
@click.option(
    "-a",
    "--adapter",
    type=click.Choice(["serial", "edge", "cloud"]),
    default=CONTROLLER_ADAPTER_DEFAULT,
    help=f"Controller interface adapter. Defaults to {CONTROLLER_ADAPTER_DEFAULT}",
)
@click.option(
    "-p",
    "--port",
    type=str,
    default=SERIAL_PORT_DEFAULT,
    help=f"Serial port used by 'serial' and 'edge' adapters. Defaults to '{SERIAL_PORT_DEFAULT}'",
)
@click.option(
    "-b",
    "--baudrate",
    type=int,
    default=SERIAL_BAUDRATE_DEFAULT,
    help=f"Serial baudrate used by 'serial' and 'edge' adapters. Defaults to {SERIAL_BAUDRATE_DEFAULT}",
)
@click.option(
    "-H",
    "--mqtt-host",
    type=str,
    default=MQTT_HOST_DEFAULT,
    help=f"MQTT host used by cloud adapter. Default: {MQTT_HOST_DEFAULT}.",
)
@click.option(
    "-P",
    "--mqtt-port",
    type=int,
    default=MQTT_PORT_DEFAULT,
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
    default=DOTBOT_ADDRESS_DEFAULT,
    help=f"Address in hex of the DotBot to control. Defaults to {DOTBOT_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "-g",
    "--gw-address",
    type=str,
    default=GATEWAY_ADDRESS_DEFAULT,
    help=f"Gateway address in hex. Defaults to {GATEWAY_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "-s",
    "--network-id",
    type=str,
    default=NETWORK_ID_DEFAULT,
    help=f"Network ID in hex. Defaults to {NETWORK_ID_DEFAULT:>0{4}}",
)
@click.option(
    "-c",
    "--controller-http-port",
    type=int,
    default=CONTROLLER_HTTP_PORT_DEFAULT,
    help=f"Controller HTTP port of the REST API. Defaults to '{CONTROLLER_HTTP_PORT_DEFAULT}'",
)
@click.option(
    "-w",
    "--webbrowser",
    is_flag=True,
    default=False,
    help="Open a web browser automatically",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Run in verbose mode (all payloads received are printed in terminal)",
)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"]),
    default="info",
    help="Logging level. Defaults to info",
)
@click.option(
    "--log-output",
    type=click.Path(),
    default=os.path.join(os.getcwd(), "pydotbot.log"),
    help="Filename where logs are redirected",
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
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    setup_logging(log_output, log_level, ["console", "file"])
    try:
        controller = Controller(
            ControllerSettings(
                adapter=adapter,
                port=port,
                baudrate=baudrate,
                mqtt_host=mqtt_host,
                mqtt_port=mqtt_port,
                mqtt_use_tls=mqtt_use_tls,
                dotbot_address=dotbot_address,
                gw_address=gw_address,
                network_id=network_id,
                controller_http_port=controller_http_port,
                webbrowser=webbrowser,
                verbose=verbose,
            ),
        )
        asyncio.run(controller.run())
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
