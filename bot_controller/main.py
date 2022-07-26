import argparse
import sys
from server import start_server
from joystick import start_joystick
from bc_serial import dotbot


JOYSTICK_AXIS_COUNT     = 4
REFRESH_PERIOD          = 0.05
SERIAL_PORT_DEFAULT     = "/dev/ttyACM0"
SERIAL_BAUDRATE_DEFAULT = 115200
CONTROLLER_TYPE_DEFAULT = "keyboard"


parser = argparse.ArgumentParser(description='BotController, universal SailBot and DotBot controller')
parser.add_argument('-t', '--type', help='Type of your controller. Defaults to "keyboard"', type=str,
                    choices=['joystick', 'keyboard'], default=CONTROLLER_TYPE_DEFAULT)
parser.add_argument('-s', '--serial', help='Linux users: path to port in "/dev" folder ; Windows users: COM port. '
                                           'Defaults to "/dev/ttyACM0"',
                    type=str, default=SERIAL_PORT_DEFAULT)
parser.add_argument('-b', '--baudrate', help='Serial baudrate. Defaults to 115200',
                    type=int, default=SERIAL_BAUDRATE_DEFAULT)
args = parser.parse_args()


def main():
    # welcome sentence
    print("Welcome to BotController, the universal SailBot and DotBot controller.\nFor help,"
          " please type '-h' or '--help' in the command line.\n\n")

    print("Type:    ", args.type, "\nSerial Port:    ", args.serial, "\nBaudrate:   ", args.baudrate, "\n")
    print("Starting the server on http://localhost:8080/dotbot")
    start_server()                                                      # start server

    if args.type == "keyboard":
        sys.exit("KEYBOARD NOT YET IMPLEMENTED.\nExisting...")
        #   TODO
    elif args.type == "joystick":
        start_joystick()
        dotbot(args.baud, args.serial)


if __name__ == "__main__":
    main()
