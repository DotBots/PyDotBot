[![CI][ci-badge]][ci-link]
[![PyPI version][pypi-badge]][pypi-link]
[![Documentation][doc-badge]][doc-link]
[![Coverage][codecov-badge]][codecov-link]
[![License][license-badge]][license-link]

# PyDotBot

This package contains a complete environment for controlling and visualizing
[DotBots](http://www.dotbots.org).

The DotBots hardware design can be found [here (PCB)][dotbot-pcb-repo].
The firmware running on the DotBots can be found [here][dotbot-firmware-repo].

This package can also be used to control devices running the SailBot firmware
application.

![DotBots controller overview][pydotbot-overview]

## Installation

Run `pip install pydotbot`

## Setup

Flash the required firmwares on the DotBots and gateway board (use an
nRF52833DK/nRF52840DK/nrf5340DK board as gateway), as explained in
[the DotBots firmware repository][dotbot-firmware-repo].

## Usage

```
dotbot-controller --help
Usage: dotbot-controller [OPTIONS]

  DotBotController, universal SailBot and DotBot controller.

Options:
  -a, --adapter [serial|edge|cloud]
                                  Controller interface adapter. Defaults to
                                  serial
  -p, --port TEXT                 Serial port used by 'serial' and 'edge'
                                  adapters. Defaults to '/dev/ttyACM0'
  -b, --baudrate INTEGER          Serial baudrate used by 'serial' and 'edge'
                                  adapters. Defaults to 1000000
  -H, --mqtt-host TEXT            MQTT host used by cloud adapter. Default:
                                  localhost.
  -P, --mqtt-port INTEGER         MQTT port used by cloud adapter. Default:
                                  1883.
  -T, --mqtt-use_tls              Use TLS with MQTT (for cloud adapter).
  -d, --dotbot-address TEXT       Address in hex of the DotBot to control.
                                  Defaults to FFFFFFFFFFFFFFFF
  -g, --gw-address TEXT           Gateway address in hex. Defaults to
                                  0000000000000000
  -s, --network-id TEXT           Network ID in hex. Defaults to 0000
  -c, --controller-http-port INTEGER
                                  Controller HTTP port of the REST API.
                                  Defaults to '8000'
  -w, --webbrowser                Open a web browser automatically
  -v, --verbose                   Run in verbose mode (all payloads received
                                  are printed in terminal)
  --log-level [debug|info|warning|error]
                                  Logging level. Defaults to info
  --log-output PATH               Filename where logs are redirected
  --config-path FILE              Path to a .toml configuration file.
  --help                          Show this message and exit.
```

By default, the controller expects the serial port to be `/dev/ttyACM0`, as on
Linux, use the `--port` option to specify another one if it's different. For
example, on Windows, you'll need to check which COM port is connected to the
gateway and add `--port COM3` if it's COM3.

Using the `--webbrowser` option, a tab will automatically open at
[http://localhost:8000/PyDotBot](http://localhost:8000/PyDotBot). The page maintains
a list of available DotBots, allows to set which one is selected and controllable
and provide a virtual joystick to control it or change the color of the on-board
RGB LED.

Use `--config-path` to specify the file:

```bash
# Use settings from the config file
dotbot-controller --config-path config_sample.toml
# Use config file but override port and adapter (simulator example)
dotbot-controller --config-path config_sample.toml -p dotbot-simulator -a dotbot-simulator
```

Values defined in the config file behave exactly like CLI options.
If both are provided, CLI flags override config values.

**Firefox users:**
If the webapp is not working, press `Ctrl + L`, type `about:config`,
and set `network.http.http2.websockets` to `false`.

## Tests

To run the tests, install [tox](https://pypi.org/project/tox/) and use it:

```
tox
```


[ci-badge]: https://github.com/DotBots/PyDotBot/workflows/CI/badge.svg
[ci-link]: https://github.com/DotBots/PyDotBot/actions?query=workflow%3ACI+branch%3Amain
[pypi-badge]: https://badge.fury.io/py/pydotbot.svg
[pypi-link]: https://badge.fury.io/py/pydotbot
[doc-badge]: https://readthedocs.org/projects/pydotbot/badge/?version=latest
[doc-link]: https://pydotbot.readthedocs.io/en/latest
[license-badge]: https://img.shields.io/pypi/l/pydotbot
[license-link]: https://github.com/DotBots/pydotbot/blob/main/LICENSE.txt

[codecov-badge]: https://codecov.io/gh/DotBots/PyDotBot/branch/main/graph/badge.svg
[codecov-link]: https://codecov.io/gh/DotBots/PyDotBot

[pydotbot-overview]: https://github.com/DotBots/PyDotBot/blob/main/dotbots.png?raw=True
[dotbot-firmware-repo]: https://github.com/DotBots/DotBot-firmware
[dotbot-pcb-repo]: https://github.com/DotBots/DotBot-hardware
