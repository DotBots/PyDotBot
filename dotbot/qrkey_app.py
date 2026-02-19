# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import asyncio
import sys

import click
import toml

from dotbot import (
    CONTROLLER_HTTP_HOSTNAME_DEFAULT,
    CONTROLLER_HTTP_PORT_DEFAULT,
    pydotbot_version,
)
from dotbot.logger import setup_logging
from dotbot.qrkey import QrKeyClient, QrKeyClientSettings
from dotbot.rest import rest_client


@click.command()
@click.option(
    "-H",
    "--http-host",
    type=int,
    help=f"Controller HTTP host of the REST API. Defaults to '{CONTROLLER_HTTP_HOSTNAME_DEFAULT}'",
)
@click.option(
    "-P",
    "--http-port",
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
    default="info",
    help="Logging level. Defaults to info",
)
@click.option(
    "--log-output",
    type=click.Path(),
    help="Filename where logs are redirected",
)
@click.option(
    "--config-path",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a .toml configuration file.",
)
def main(
    http_host,
    http_port,
    webbrowser,
    verbose,
    log_level,
    log_output,
    config_path,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBot QrKey client."""
    # welcome sentence
    print(f"Welcome to the DotBot QrKey client (version: {pydotbot_version()}).")

    # The priority order is CLI > ConfigFile (optional) > Defaults
    cli_args = {
        "http_host": http_host,
        "http_port": http_port,
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

    client_settings = QrKeyClientSettings(**data)

    setup_logging(
        client_settings.log_output,
        client_settings.log_level,
        ["console", "file"],
    )
    try:
        asyncio.run(cli(client_settings))
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


async def cli(settings: QrKeyClientSettings):
    async with rest_client(settings.http_host, settings.http_port, False) as client:
        qrkey_client = QrKeyClient(settings, client)
        await qrkey_client.run()


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
