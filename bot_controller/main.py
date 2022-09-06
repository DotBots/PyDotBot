#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import argparse
import sys

from importlib.metadata import version, PackageNotFoundError

import serial

from bot_controller.factory import controller_factory, ControllerException


SERIAL_PORT_DEFAULT = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 1000000
CONTROLLER_TYPE_DEFAULT = "keyboard"


def main():
    """Main function."""

    parser = argparse.ArgumentParser(
        description="BotController, universal SailBot and DotBot controller"
    )
    parser.add_argument(
        "-t",
        "--type",
        help='Type of your controller. Defaults to "keyboard"',
        type=str,
        choices=["joystick", "keyboard", "server"],
        default=CONTROLLER_TYPE_DEFAULT,
    )
    parser.add_argument(
        "-p",
        "--port",
        help='Linux users: path to port in "/dev" folder ; Windows users: COM port. Defaults to "/dev/ttyACM0"',
        type=str,
        default=SERIAL_PORT_DEFAULT,
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        help="Serial baudrate. Defaults to 1000000",
        type=int,
        default=SERIAL_BAUDRATE_DEFAULT,
    )
    args = parser.parse_args()

    # welcome sentence
    try:
        package_version = version("dotbot_controller")
    except PackageNotFoundError:
        package_version = "unknown"
    print(
        f"Welcome to BotController (version: {package_version}), the universal SailBot and DotBot controller."
    )

    try:
        controller = controller_factory(args.type, args.port, args.baudrate)
        controller.start()
    except ControllerException:
        sys.exit("Invalid controller type.")
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except KeyboardInterrupt:
        sys.exit("Exiting")


if __name__ == "__main__":
    main()
