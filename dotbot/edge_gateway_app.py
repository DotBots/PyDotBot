# SPDX-FileCopyrightText: 2025-present Inria
# SPDX-FileCopyrightText: 2025-present Alexandre Abadie <alexandre.abadie@inria.fr>
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
    DOTBOT_ADDRESS_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    SERIAL_BAUDRATE_DEFAULT,
    SERIAL_PORT_DEFAULT,
    pydotbot_version,
)
from dotbot.edge_gateway import EdgeGateway, EdgeGatewaySettings
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
    port,
    baudrate,
    dotbot_address,
    gw_address,
    verbose,
    log_level,
    log_output,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBots Edge Gateway entry point."""
    # welcome sentence
    print(
        f"Starting the DotBots Edge Gateway controller (version: {pydotbot_version()})."
    )

    setup_logging(log_output, log_level, ["console", "file"])
    try:
        controller = EdgeGateway(
            EdgeGatewaySettings(
                port=port,
                baudrate=baudrate,
                dotbot_address=dotbot_address,
                gw_address=gw_address,
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
