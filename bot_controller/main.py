#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import sys

from importlib.metadata import version, PackageNotFoundError

import click
import serial

from bot_controller.controller import (
    controller_factory,
    register_controller,
)
from bot_controller.keyboard import KeyboardController
from bot_controller.joystick import JoystickController
from bot_controller.server import ServerController


SERIAL_PORT_DEFAULT = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 1000000
CONTROLLER_TYPE_DEFAULT = "keyboard"
DEFAULT_CONTROLLERS = {
    "keyboard": KeyboardController,
    "joystick": JoystickController,
    "server": ServerController,
}


@click.command()
@click.option(
    "-t",
    "--type",
    type=click.Choice(["joystick", "keyboard", "server"]),
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
def main(type, port, baudrate):  # pylint: disable=redefined-builtin
    """BotController, universal SailBot and DotBot controller."""
    # welcome sentence
    try:
        package_version = version("dotbot_controller")
    except PackageNotFoundError:
        package_version = "unknown"
    print(
        f"Welcome to BotController (version: {package_version}), the universal SailBot and DotBot controller."
    )

    for controller, controller_cls in DEFAULT_CONTROLLERS.items():
        register_controller(controller, controller_cls)
    try:
        controller = controller_factory(type, port, baudrate)
        controller.start()
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except KeyboardInterrupt:
        sys.exit("Exiting")


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
