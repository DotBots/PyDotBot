[![CI][ci-badge]][ci-link]
[![PyPI version][pypi-badge]][pypi-link]
[![Documentation][doc-badge]][doc-link]
[![Coverage][codecov-badge]][codecov-link]
[![License][license-badge]][license-link]

# PyDotBot

**The control plane for [DotBot](http://www.dotbots.org) swarms - build firmware,
flash a robot, and control a fleet over the air, from one bot to a thousand, all
from a single `dotbot` CLI and web UI.**

DotBots are small wireless wheeled robots built to operate in large swarms,
for research and education. Developed by the [AIO team](https://aio.inria.fr/) at
[Inria Paris](https://www.inria.fr/), and run routinely with ~100–200 bots,
with one 725-bot campaign.

▶️ [Click to see a DotBot swarm in action](https://www.youtube.com/watch?v=pXGTLqafReU)

PyDotBot is the control plane in the middle: your code, the web UI, and users
talk to it, and it drives the swarm through a gateway.

```text
┌───────────┐           ┌────────────┐               ┌─────────┐
│  web UI / │           │            │               │         │
│   CLI /   │──REST/WS─▶│ controller │──serial/MQTT─▶│ gateway │──radio─▶ 🤖🤖🤖 DotBot swarm
│ your code │           │            │               │         │
└───────────┘           └────────────┘               └─────────┘
  ╰─────────── PyDotBot ───────────╯
```

**What you can do**

- 🕹️ Drive one bot or a whole fleet from a **web UI** (live map + joystick) or your own **Python** code
- 📡 Flash the swarm **over the air** - one command, hundreds of bots at once
- 🛰️ Get real-world **(x, y) positions** with Lighthouse 2 localization
- 🧪 Try it all with **zero hardware** using the built-in simulator
- 🛠️ One `dotbot` CLI takes you from build → flash → run

## Try it now - no hardware

See the whole thing run with nothing but Python:

```bash
pip install --pre pydotbot  # using 'pre' while we are at release candidate
dotbot run simulator -w   # opens the web UI at http://localhost:8000/PyDotBot/, driving a simulated swarm
```

Drive the simulated bots from the joystick + map - then script them from your own
code (below), or set up real hardware further down.

## Drive it from your own code

The controller - real or simulated - exposes a REST + WebSocket API, so you can
command the swarm in a few lines of Python (only extra dependency:
[`requests`](https://pypi.org/project/requests/)):

```python
import requests, time

BASE = "http://localhost:8000"
bot = requests.get(f"{BASE}/controller/dotbots").json()[0]["address"]

# roll in a circle for ~5 s - left_y and right_y are the two wheel speeds
for _ in range(50):
    requests.put(f"{BASE}/controller/dotbots/{bot}/0/move_raw",
                 json={"left_x": 0, "left_y": 60, "right_x": 0, "right_y": 30})
    time.sleep(0.1)
requests.put(f"{BASE}/controller/dotbots/{bot}/0/move_raw",
             json={"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0})
```

The full surface - every endpoint, the live WebSocket stream, and CSV data
logging - is in the [REST / WebSocket reference][rest-doc] (or the
[MQTT bridge][mqtt-doc]). A higher-level Python SDK is planned; today you talk to
the controller over REST/WebSocket/MQTT.

The firmware for the DotBots can be found [here][dotbot-firmware-repo].

## Prerequisites (for real hardware)

Driving an already-provisioned swarm - or the simulator above - needs nothing but
Python. The tools below are only for building or cable-flashing firmware yourself.

Software to install (as needed):
- Python ≥ 3.11 - ensure you also have [pip](https://pip.pypa.io/en/stable/) available in your PATH
- [nRF Command Line Tools](https://www.nordicsemi.com/Products/Development-tools/nRF-Command-Line-Tools) (`nrfjprog`), for commands such as `dotbot device flash`
- [SEGGER Embedded Studio](https://www.segger.com/products/development-tools/embedded-studio/), for commands such as `dotbot fw build`

Minimal hardware setup:
- DotBot v3, as well as a USB-C cable and a barrel-jack charger (2.5 mm, 6–18 V, 5/10 A)
- nRF5340-DK to use as gateway, as well as a micro-USB cable

## Install

```bash
pip install --pre pydotbot   # --pre while 0.29 is in pre-release
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
  run     Host-side processes: controller, gateway, simulator, calibration, demos, teleop.
  config  Show the resolved config and where it came from; scaffold one with init.
```

Every command and flag is documented in the [CLI reference][cli-doc].

## Quickstart - a swarm

### setup the swarm

To operate as a swarm, set your swarm connection config:

```bash
dotbot config init --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234
```

> `argus.paris.inria.fr` is our Inria Paris broker and `1234` our swarm - pass
> your own `--conn` and `--swarm-id` (your testbed admin provides these). This
> writes `./dotbot.toml`; commands run from this directory pick it up, so you
> don't repeat the flags. Full schema: the [configuration reference][config-doc].

The swarm mode also requires a special "sandbox" firmware in each dotbot.
We also need a more powerful gateway firmware. Let's flash both - the network
id comes from your config:

```bash
dotbot fw fetch -f 0.8.0rc1  # pull the pre-compiled firmwares from a release
dotbot device flash-mari-gateway -s 10 -f 0.8.0rc1  # flash the gateway
dotbot device flash-swarmit-sandbox -s 77 -f 0.8.0rc1  # the sandbox firmware - do this on each dotbot
```

(`device flash-mari-gateway` / `flash-swarmit-sandbox` auto-fetch
the release into `./artifacts/` if it isn't already there.)

Now, run the gateway (the broker comes from your config):

```bash
dotbot run gateway -p /dev/cu.usbmodem0010500324491
```

### use the swarm

You can flash as many dotbots as you want, all at once! First, how about making them spinnnn 🔄 🔄

```bash
dotbot swarm flash ./artifacts/spin-sandbox-dotbot-v3.bin -ys  # flash the whole fleet with a simple spinning app
```

(`dotbot swarm` reads the same `dotbot.toml` as the rest - pass `--conn` /
`--swarm-id` to override it for one run.)

Then, flash another experiment:

```bash
dotbot swarm stop  # ensure all robots are in bootloader
dotbot swarm flash ./artifacts/dotbot-sandbox-dotbot-v3.bin -ys  # this firmware allows bots to be remote-controlled
```

Observe and control your swarm from a web interface:

```bash
dotbot run controller -w  # will open a webpage at http://localhost:8000/PyDotBot/
```

Full walkthrough of fleet operations - status, OTA flash, start/stop, monitor -
is in the [`swarm` reference][swarm-doc].

## Going further

- **Drive a single bot** - build, flash, and control one DotBot end to end:
  the [one-bot guide][one-bot-doc].
- **Lighthouse 2 localization** - give your bots real-world `(x, y)` positions:
  the [LH2 calibration guide][lh2-doc].
- **Everything else** - the `dotbot` commands (`fw` / `device` / `swarm` / `run`,
  plus `config`), the controller + web UI, and hardware notes are in the
  [documentation][doc-link].

Swarm orchestration is in the base install. Only LH2 calibration needs an extra:

```bash
pip install --pre 'pydotbot[calibrate]'  # opencv-python + textual (LH2 calibration)
```

Hitting a snag (e.g. the web UI not loading in Firefox)? See
[Troubleshooting][troubleshooting-doc].

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
[cli-doc]: https://pydotbot.readthedocs.io/en/latest/cli/index.html
[fw-doc]: https://pydotbot.readthedocs.io/en/latest/cli/fw.html
[device-doc]: https://pydotbot.readthedocs.io/en/latest/cli/device.html
[swarm-doc]: https://pydotbot.readthedocs.io/en/latest/cli/swarm.html
[config-doc]: https://pydotbot.readthedocs.io/en/latest/reference/configuration.html
[controller-doc]: https://pydotbot.readthedocs.io/en/latest/guides/controller.html
[one-bot-doc]: https://pydotbot.readthedocs.io/en/latest/guides/one-bot.html
[lh2-doc]: https://pydotbot.readthedocs.io/en/latest/guides/lh2-calibration.html
[troubleshooting-doc]: https://pydotbot.readthedocs.io/en/latest/reference/troubleshooting.html
[rest-doc]: https://pydotbot.readthedocs.io/en/latest/reference/rest.html
[mqtt-doc]: https://pydotbot.readthedocs.io/en/latest/reference/mqtt.html
