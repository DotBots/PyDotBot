[![CI][ci-badge]][ci-link]
[![PyPI version][pypi-badge]][pypi-link]
[![Documentation][doc-badge]][doc-link]
[![Coverage][codecov-badge]][codecov-link]
[![License][license-badge]][license-link]

# PyDotBot

This package contains a complete environment for using [DotBots](http://www.dotbots.org).

The DotBot is a small wireless wheeled robot, built to operate in swarms of
thousands, for research and education.

The firmware for the DotBots can be found [here][dotbot-firmware-repo].

## Prerequisites

Software to install (as needed):
- Python ≥ 3.11 - ensure you have pip also installed
- [nRF Command Line Tools](https://www.nordicsemi.com/Products/Development-tools/nRF-Command-Line-Tools) (`nrfjprog`), for commands such as `dotbot device flash`
- [SEGGER Embedded Studio](https://www.segger.com/products/development-tools/embedded-studio/), for commands such as `dotbot fw build`

Minimal hardware setup:
- DotBot v3, as well as a USB-C cable and a barrel-jack charger (2.5 mm, 6–18 V, 5/10 A)
- nRF5340-DK to use as gateway, as well as a micro-USB cable

## Install

```bash
pip install --pre 'pydotbot[swarm]'   # --pre while 0.29 is in pre-release
git clone --recurse-submodules --branch develop https://github.com/DotBots/DotBot-firmware.git
```

## Usage

```
$ dotbot --help
Usage: dotbot [OPTIONS] COMMAND [ARGS]...

  One CLI for the whole DotBot workflow: build and flash firmware, program and
  control a single robot, and run experiments over the air across a swarm -
  from one bot to a thousand.

Commands:
  fw      Firmware artifacts (no hardware): build / fetch / list / make.
  device  One connected device (cable/probe): flash an app/role, read info.
  swarm   The fleet over the air: status, start/stop, OTA flash, monitor.
  run     Host-side processes: controller, gateway, sim, calibration, demos, teleop.
```

## Quickstart - one bot

Build and flash firmware for a single dotbot:

```bash
# build the bare dotbot app into ./artifacts/ (needs SEGGER Embedded Studio)
dotbot fw artifacts --app dotbot
# cable-flash it to the bot whose J-Link serial starts with 77
dotbot device flash dotbot -s 77
```

Now, build and flash the gateway to connect to a robot.
The gateway is a dev board (e.g. an nRF52840-DK) plugged into your
computer; it bridges the robot's radio to USB serial.

```bash
# build the gateway firmware for your DK board into ./artifacts/ (needs SEGGER Embedded Studio)
dotbot fw artifacts --app dotbot_gateway -t nrf52840dk
# cable-flash it to the DK whose J-Link serial starts with 10
dotbot device flash dotbot_gateway -b nrf52840dk -s 10
```

With a gateway plugged into your computer, point the controller at it
and open the web UI:

```bash
dotbot run controller --conn /dev/ttyACM0 -w  # serial gateway; no swarm-id needed
```

## Quickstart - a swarm

### swarm setup

To operate as a swarm, we need to fetch some firmware, and setup a configuration file:

```bash
# pull the pre-compiled firmwares from a release
dotbot fw fetch -f 0.8.0rc1  # or build yourself with: dotbot fw artifacts --sandbox
# configure where to connect and which swarm
cat > swarm-config.toml <<'EOF'
conn = "mqtts://argus.paris.inria.fr:8883"
swarm_id = "1234"
EOF
```

The swarm mode also requires a special "sandbox" firmware in each dotbot.
We also need a more powerful gateway firmware.
Let's flash both:

```bash
dotbot device flash-gateway -n 1234 -s 10 -f 0.8.0rc1  # flash the gateway, setting its swarm id to 0x1234
dotbot device flash-sandbox-host -n 1234 -s 77 -f 0.8.0rc1  # flash the sandbox firmware - do this on each dotbot
```

(`device flash-gateway` / `flash-sandbox-host` auto-fetch
the release into `./artifacts/` if it isn't already there.)

Now, run the gateway:

```bash
dotbot run gateway -m mqtts://argus.paris.inria.fr:8883 -p /dev/cu.usbmodem0010500324491
```

### swarm usage


You can flash as many dotbots as you want, all at once! First, how about making them spinnnn 🔄 🔄

```bash
dotbot swarm -c swarm-config.toml flash ./artifacts/spin-sandbox-dotbot-v3.bin -ys  # flash the whole fleet with a simple spinning app
```

Then, flash another experiment:

```bash
dotbot swarm -c swarm-config.toml stop  # ensure all robots are in bootloader
dotbot swarm -c swarm-config.toml flash ./artifacts/dotbot-sandbox-dotbot-v3.bin -ys  # this firmware allows bots to be remote-controlled
```

Observe and control your swarm from a web interface:

```bash
dotbot run controller --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234 -w  # will open a webpage at http://localhost:8000/PyDotBot/
```

## Quickstart - Lighthouse 2 localization

Follow this section if you want your robots to have localization information.
You will need at least one Lighthouse 2 base station.

Note: this section needs the calibration extra — `pip install --pre 'pydotbot[calibrate]'`.

### collect calibration

Learn more about the calibration setup (guide TODO).

```bash
# flash the LH2-calibration capture firmware to a cabled dotbot, then collect:
dotbot device flash lh2_calibration -s 77
dotbot run lh2-calibration collect -p /dev/tty.usbmodem0007745943981 -d 200  # collect data from a dotbot, use a square of side 20 cm
```

Then, update the swarm with a new calibration:

```bash
dotbot swarm -c swarm-config.toml stop  # ensure all robots are in bootloader
dotbot swarm -c swarm-config.toml calibrate-lh2 ~/.dotbot/calibration-2026-05-26T14-00-36Z.toml
```

Now your bots should be reporting their `(x, y)` location!

## Going further

Full command reference and guides — running the controller + web UI, the four
CLI namespaces (`fw` / `device` / `swarm` / `run`), hardware, and LH2
calibration — are in the [documentation][doc-link].

Some commands need optional runtime deps:

```bash
pip install --pre 'pydotbot[swarm]'      # swarmit (fleet orchestration)
pip install --pre 'pydotbot[calibrate]'  # opencv-python + textual (LH2 calibration)
pip install --pre 'pydotbot[all]'        # everything
```

The `dotbot` dispatcher is the only console script — every workflow is a
`dotbot <group> <verb>` subcommand; there are no `dotbot-*` binaries.

**Firefox users:**
If the webapp is not working, press `Ctrl + L`, type `about:config`,
and set `network.http.http2.websockets` to `false`.

## Tests

To run the tests, run [tox](https://pypi.org/project/tox/):

```
tox
```

## License

See `LICENSE` in each component repository.

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
[dotbot-firmware-repo]: https://github.com/DotBots/DotBot-firmware
