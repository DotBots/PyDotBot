[![CI][ci-badge]][ci-link]
[![Coverage][codecov-badge]][codecov-link]
[![PyPI version][pypi-badge]][pypi-link]

# PyDotBot

This package contains a complete environment for controlling and visualizing
[DotBots](http://www.dotbots.org).

The DotBots hardware design can be found
[here (PCB)][dotbot-pcb-repo] and [here (chassis)][dotbot-chassis-repo].
The firmware running on the DotBots can be found [here][dotbot-firmware-repo].

This package can also be used to control devices running the SailBot firmware
application.

![DotBots controller overview][pydotbot-overview]

## Installation

Run `pip install pydotbot`

## Setup

Flash the required firmwares on the DotBots and gateway board (use an
nRF52840DK board as gateway), as explained in
[the DotBots firmware repository][dotbot-firmware-repo].

## Usage

```
dotbots-controller --help
Usage: dotbots-controller [OPTIONS]

  BotController, universal SailBot and DotBot controller.

Options:
  -t, --type [joystick|keyboard]  Type of your controller. Defaults to
                                  'keyboard'
  -p, --port TEXT                 Linux users: path to port in '/dev' folder ;
                                  Windows users: COM port. Defaults to
                                  '/dev/ttyACM0'
  -b, --baudrate INTEGER          Serial baudrate. Defaults to 1000000
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -g, --gw-address TEXT           Gateway address in hex. Defaults to
                                  0000000000000000
  -s, --swarm-id TEXT             Swarm ID in hex. Defaults to 0000
  -w, --webbrowser                Open a web browser automatically
  -c, --calibrate                 Run controller in calibration mode
                                  (lighthouse mode)
  -D, --calibration-dir PATH      Directory containing calibration files
  -v, --verbose                   Run in verbose mode (all payloads received
                                  are printed in terminal)
  --help                          Show this message and exit.
```

By default, the controller expects the serial port to be `/dev/ttyACM0`, as on
Linux, use the `--port` option to specify another one if it's different. For
example, on Windows, you'll need to check which COM port is connected to the
gateway and add `--port COM3` if it's COM3.

Using the `--webbrowser` option, a tab will automatically open at
[http://localhost:8000/dotbots](http://localhost:8000/dotbots). The page maintains
a list of available DotBots, allows to set which one is active and controllable
and provide a virtual joystick to control it or change the color of the on-board
RGB LED.

### Lighthouse positioning

The DotBots firmware comes with a cheap indoor positioning system based on
[Valve Lighthouse 2](https://www.valvesoftware.com/en/index/base-stations).

To get the positioning to work and the DotBots to be tracked in real-time the
system must be first calibrated by clicking the "Start calibration" or
"Update calibration" button below the grid map and then by following the
instructions there.

## Tests

To run the tests, install [tox](https://pypi.org/project/tox/) and use it:

```
tox
```


[ci-badge]: https://github.com/DotBots/PyDotBot/workflows/CI/badge.svg
[ci-link]: https://github.com/DotBots/PyDotBot/actions?query=workflow%3ACI+branch%3Amain
[pypi-badge]: https://badge.fury.io/py/pydotbot.svg
[pypi-link]: https://badge.fury.io/py/pydotbot
[codecov-badge]: https://codecov.io/gh/DotBots/PyDotBot/branch/main/graph/badge.svg
[codecov-link]: https://codecov.io/gh/DotBots/PyDotBot

[pydotbot-overview]: https://github.com/DotBots/PyDotBot/blob/main/dotbots.png?raw=True
[dotbot-firmware-repo]: https://github.com/DotBots/DotBot-firmware
[dotbot-pcb-repo]: https://github.com/DotBots/DotBot-pcb
[dotbot-chassis-repo]: https://github.com/DotBots/DotBot-chassis
