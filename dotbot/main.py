#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import sys
import asyncio

import click
import serial

from dotbot import pydotbot_version

from dotbot.controller import (
    ControllerSettings,
    controller_factory,
    register_controller,
)
from dotbot.keyboard import KeyboardController
from dotbot.joystick import JoystickController


SERIAL_PORT_DEFAULT = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 1000000
DOTBOT_ADDRESS_DEFAULT = "FFFFFFFFFFFFFFFF"  # Broadcast by default
GATEWAY_ADDRESS_DEFAULT = "0000000000000000"
SWARM_ID_DEFAULT = "0000"
CONTROLLER_TYPE_DEFAULT = "keyboard"
DEFAULT_CONTROLLERS = {
    "keyboard": KeyboardController,
    "joystick": JoystickController,
}


@click.command()
@click.option(
    "-t",
    "--type",
    type=click.Choice(["joystick", "keyboard"]),
    default=CONTROLLER_TYPE_DEFAULT,
    help="Type of your controller. Defaults to 'keyboard'",
)
@click.option(
    "-p",
    "--port",
    type=str,
    default=SERIAL_PORT_DEFAULT,
    help=f"Linux users: path to port in '/dev' folder ; Windows users: COM port. Defaults to '{SERIAL_PORT_DEFAULT}'",
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
def main(
    type,
    port,
    baudrate,
    dotbot_address,
    gw_address,
    swarm_id,
    webbrowser,
    verbose,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """BotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    for controller, controller_cls in DEFAULT_CONTROLLERS.items():
        register_controller(controller, controller_cls)
    try:
        controller = controller_factory(
            type,
            ControllerSettings(
                port,
                baudrate,
                dotbot_address,
                gw_address,
                swarm_id,
                webbrowser,
                verbose,
            ),
        )
        asyncio.run(controller.run())
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
