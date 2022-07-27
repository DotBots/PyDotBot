#!/usr/bin/env python3

import argparse
import sys
from bot_controller import joystick
from bot_controller import server


JOYSTICK_AXIS_COUNT     = 4
REFRESH_PERIOD          = 0.05
SERIAL_PORT_DEFAULT     = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 115200
CONTROLLER_TYPE_DEFAULT = "keyboard"


def main():
    parser = argparse.ArgumentParser(description='BotController, universal SailBot and DotBot controller')
    parser.add_argument('-t', '--type', help='Type of your controller. Defaults to "keyboard"', type=str,
                        choices=['joystick', 'keyboard', 'server'], default=CONTROLLER_TYPE_DEFAULT)
    parser.add_argument('-p', '--port',
                        help='Linux users: path to port in "/dev" folder ; Windows users: COM port. Defaults to "/dev/ttyACM0"',
                        type=str, default=SERIAL_PORT_DEFAULT)
    parser.add_argument('-b', '--baudrate', help='Serial baudrate. Defaults to 115200',
                        type=int, default=SERIAL_BAUDRATE_DEFAULT)
    args = parser.parse_args()

    # welcome sentence
    print("Welcome to BotController, the universal SailBot and DotBot controller.")
    sys.stdout.flush()

    try:
        if args.type == "keyboard":
            sys.exit("KEYBOARD NOT YET IMPLEMENTED.\nExiting...")
            #   TODO
        elif args.type == "joystick":
            joystick.start(args.port, args.baudrate)
        elif args.type == 'server':
            server.start()
        else:
            sys.exit("Invalid controller type.")
    except KeyboardInterrupt:
        sys.exit("Exiting")


if __name__ == "__main__":
    main()
