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

A single `dotbot` CLI dispatches to every workflow. The top level is four
namespaces, each one *kind of thing* — firmware artifacts, one connected
device, the fleet, and host-side processes you launch:

```
dotbot --help
Usage: dotbot [OPTIONS] COMMAND [ARGS]...

  Control DotBots. Four namespaces: firmware artifacts (fw), one connected
  device (device), the fleet over the air (swarm), and host-side processes
  you launch (run).

Commands:
  fw      Firmware artifacts (no hardware): build / fetch / list / make.
  device  One connected device (cable/probe): flash an app/role, read info.
  swarm   The fleet over the air: status, start/stop, OTA flash, monitor.
  run     Host-side processes: controller, gateway, sim, calibration, demos, teleop.
```

Three groups are nouns you *manage*; `run` is the verb — the long-running
software you launch on your own computer:

```
dotbot run controller            # control plane + REST/WS + dashboard
dotbot run gateway               # host-side UART <-> MQTT bridge
dotbot run sim                   # ≡ run controller --conn simulator (no hardware)
dotbot run lh2-calibration       # LH2 calibration workflow
dotbot run demo qr               # built-in research demos
dotbot run keyboard              # teleop a bot from the keyboard
```

Note the two "gateway"s the namespaces disambiguate: `dotbot device
flash-gateway` flashes gateway *firmware* onto a board; `dotbot run
gateway` runs the host-side bridge *process* that talks to it.

Some subcommands need optional runtime deps:

```
pip install pydotbot[swarm]      # adds swarmit (fleet orchestration)
pip install pydotbot[calibrate]  # adds opencv-python + textual (LH2 calibration TUI + exporter)
pip install pydotbot[all]        # all of the above
```

Device flashing/provisioning (`dotbot device flash-…`) works out of the
box — its `intelhex` dep is part of the core install. The LH2 calibration
TUI/exporter (`dotbot run lh2-calibration`) keeps its heavyweight deps
(textual / opencv-python) behind the `[calibrate]` extra so the core
install stays lean.

### Starting the controller

Run `dotbot run controller --help` for the full flag list (`--conn`, MQTT,
HTTP port, map size, etc.). By default the controller expects the serial
port to be `/dev/ttyACM0` on Linux — use `--port` to override (e.g.
`--port COM3` on Windows).

With `--webbrowser`, a tab opens at
[http://localhost:8000/PyDotBot](http://localhost:8000/PyDotBot). The
page lists available DotBots, lets you select and control one, and
exposes a virtual joystick and RGB LED control.

Use `--config-path` for a TOML config file:

```bash
# Use settings from the config file
dotbot run controller --config-path config_sample.toml
# Use config file but override the connection (run a simulator instead)
dotbot run controller --config-path config_sample.toml --conn simulator
```

CLI flags override config-file values when both are provided.

The `dotbot` dispatcher is the only console script — every workflow is a
`dotbot <group> <verb>` subcommand. There are no per-command `dotbot-*`
binaries.

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
