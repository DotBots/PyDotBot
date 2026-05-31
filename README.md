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

## Install

```bash
pip install --pre 'pydotbot[all]'   # --pre while 0.29 is in pre-release
git clone --recurse-submodules --branch develop https://github.com/DotBots/DotBot-firmware.git
```

## Usage

```
$ dotbot --help
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
dotbot fw fetch -f 0.8.0rc1
# configure where to connect and which swarm
cat > tb-config.toml <<'EOF'
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
dotbot swarm -c tb-config.toml flash ./artifacts/spin-sandbox-dotbot-v3.bin -ys  # flash the whole fleet with a simple spinning app
```

Then, flash another experiment:

```bash
dotbot swarm -c tb-config.toml stop  # ensure all robots are in bootloader
dotbot swarm -c tb-config.toml flash ./artifacts/dotbot-sandbox-dotbot-v3.bin -ys  # this firmware allows bots to be remote-controlled
```

Observe and control your swarm from a web interface:

```bash
dotbot run controller --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234 -w  # will open a webpage at http://localhost:8000/PyDotBot/
```

## Quickstart - Lighthouse 2 localization

Follow this section if you want your robots to have localization information.
You will need at least one Lighthouse 2 base station.

### collect calibration

Learn more about the calibration setup (guide TODO).

```bash
# flash the LH2-calibration capture firmware to a cabled dotbot, then collect:
dotbot device flash lh2_calibration -s 77
dotbot run lh2-calibration collect -p /dev/tty.usbmodem0007745943981 -d 200  # collect data from a dotbot, use a square of side 20 cm
```

Then, update the swarm with a new calibration:

```bash
dotbot swarm -c tb-config.toml stop  # ensure all robots are in bootloader
dotbot swarm -c tb-config.toml calibrate-lh2 ~/.dotbot/calibration-2026-05-26T14-00-36Z.toml
```

Now your bots should be reporting their `(x, y)` location!

## More things you can do

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
box. The LH2 calibration
TUI/exporter (`dotbot run lh2-calibration`) keeps its heavyweight deps
(textual / opencv-python) behind the `[calibrate]` extra so the core
install stays lean.

### Starting the controller

Run `dotbot run controller --help` for the full flag list (`--conn`, MQTT,
HTTP port, map size, etc.). By default the controller expects the serial
port to be `/dev/ttyACM0` on Linux - use `--port` to override (e.g.
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
