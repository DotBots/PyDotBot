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
    CONTROLLER_PORT_DEFAULT,
    DOTBOT_ADDRESS_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    SERIAL_BAUDRATE_DEFAULT,
    SERIAL_PORT_DEFAULT,
    SWARM_ID_DEFAULT,
    pydotbot_version,
)
from dotbot.controller import Controller, ControllerSettings
from dotbot.logger import setup_logging


@click.command()
@click.option(
    "-p",
    "--port",
    type=str,
    default=SERIAL_PORT_DEFAULT,
    help=f"Virtual com port. Defaults to '{SERIAL_PORT_DEFAULT}'",
)
@click.option(
    "-b",
    "--baudrate",
    type=int,
    default=SERIAL_BAUDRATE_DEFAULT,
    help=f"Serial baudrate. Defaults to {SERIAL_BAUDRATE_DEFAULT}",
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
    "--swarm-id",
    type=str,
    default=SWARM_ID_DEFAULT,
    help=f"Swarm ID in hex. Defaults to {SWARM_ID_DEFAULT:>0{4}}",
)
@click.option(
    "-c",
    "--controller-port",
    type=int,
    default=CONTROLLER_PORT_DEFAULT,
    help=f"Controller port. Defaults to '{CONTROLLER_PORT_DEFAULT}'",
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
@click.option(
    "--handshake",
    is_flag=True,
    default=False,
    help="Perform a basic handshake with the gateway board on startup",
)
@click.option(
    "--edge",
    is_flag=True,
    default=False,
    help="Connect to the edge gateway via MQTT instead of local serial connection",
)
def main(
    port,
    baudrate,
    dotbot_address,
    gw_address,
    swarm_id,
    controller_port,
    webbrowser,
    verbose,
    log_level,
    log_output,
    handshake,
    edge,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    setup_logging(log_output, log_level, ["console", "file"])
    try:
        controller = Controller(
            ControllerSettings(
                port=port,
                baudrate=baudrate,
                dotbot_address=dotbot_address,
                gw_address=gw_address,
                swarm_id=swarm_id,
                controller_port=controller_port,
                webbrowser=webbrowser,
                handshake=handshake,
                edge=edge,
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
