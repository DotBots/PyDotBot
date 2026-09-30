[![CI][ci-badge]][ci-link]
[![PyPI version][pypi-badge]][pypi-link]
[![Documentation][doc-badge]][doc-link]
[![Coverage][codecov-badge]][codecov-link]
[![License][license-badge]][license-link]

# PyDotBot

The control plane for the [DotBot](http://www.dotbots.org) - a small wireless
wheeled robot built to operate in large swarms, for research and education.

PyDotBot allows you to flash a DotBot and control a whole fleet over the air,
from one DotBot to a thousand.

[▶️ Click to see a DotBot swarm in action](https://www.youtube.com/watch?v=pXGTLqafReU)

```text
┌───────────┐           ┌────────────┐               ┌─────────┐
│  web UI / │           │            │               │         │
│   CLI /   │──REST/WS─▶│ controller │──serial/MQTT─▶│ gateway │──radio─▶ 🤖🤖🤖 DotBot swarm
│ your code │           │            │               │         │
└───────────┘           └────────────┘               └─────────┘
  ╰─────────── PyDotBot ───────────╯
```

**What you can do**

- 🕹️ Drive one DotBot or a whole fleet from a **web UI** (live map + joystick) or your own **Python** code
- 📡 Flash the swarm **over the air** - one command, hundreds of DotBots at once
- 🛰️ Get real-world **(x, y) positions** with Lighthouse 2 localization
- 🧪 Try it all with **zero hardware** using the built-in simulator
- 🛠️ One `dotbot` CLI takes you from build → flash → run

## Install

PyDotBot is available on [PyPi](https://pypi.org/project/pydotbot/), install it with:

```bash
pip install pydotbot
```

Then, check your installation with `dotbot --version` and learn what's possible with `dotbot --help`.

Every command and flag is documented in the [CLI reference][cli-doc].

## Try the simulator

See the whole thing run with nothing but Python!

First, in an empty folder, write a config:

```bash
dotbot config init
```

This writes `./dotbot.toml` with a site named `default`: a 2 x 2 m **field**,
where experiments happen, and a **staging** strip below it, where robots park.
`--field 1.5m` or `--field 2x3m` sizes the field, and the rest follows from it.
Commands run from this folder read the file, and it is yours to edit once you
measure a real room.

Then run a simulated swarm, which you can observe in the web console at http://localhost:8000/console/ :

```bash
dotbot run simulator --robots 20
```

The console opens automatically; pass `--headless` to suppress it (it's still
served). It is one map-first UI for both driving the fleet and orchestrating the
testbed - firmware flashing, start/stop and live events - when a swarmit server
is reachable.

Drive the simulated DotBots from the console, or run a bundled demo in a
second terminal:

```bash
dotbot run demo circle   # drive one DotBot in a circle (the simplest demo)
```

Learn how to script the swarm from your own code, run the richer examples, and more - all with
no hardware - in the [simulator guide][simulator-doc].

## Deploy a real swarm

The DotBot is made to operate as a swarm, here is how you can deploy it on real robots.

### Prerequisites

Minimal hardware setup:
- DotBot v3, as well as a USB-C cable and a barrel-jack charger (2.5 mm, 6–18 V, 5/10 A)
- nRF5340-DK to use as gateway, as well as a micro-USB cable

Software to install (as needed):
- Python ≥ 3.11 - ensure you also have [pip](https://pip.pypa.io/en/stable/) available in your PATH
- [nRF Command Line Tools](https://www.nordicsemi.com/Products/Development-tools/nRF-Command-Line-Tools) (`nrfjprog`), for commands such as `dotbot device flash`

### Setup

To operate as a swarm, set your swarm connection config:

```bash
dotbot config init --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234
```

> `--conn` is your MQTT broker and `--swarm-id` a 16-bit hex id that identifies
> your swarm. Running your own handful of DotBots? Pick any swarm
> id - the example points `--conn` at our Inria Paris broker so it works out of
> the box, but swap in your own broker once you have one. (On a shared testbed,
> your admin gives you the broker and swarm id to use, or a site pack that
> carries the broker: `dotbot site add <pack> --use`.) This writes
> `./dotbot.toml`, with the broker as the site's connection and the swarm id
> as your own; commands run from this directory pick it up, so you don't
> repeat the flags. MQTT credentials go in `DOTBOT_MQTT_USER` /
> `DOTBOT_MQTT_PASS`, with `DOTBOT_MQTT_HOST` naming the broker they are for.
> Full schema: the [configuration reference][config-doc].

The swarm mode also requires a special "sandbox" firmware in each DotBot.
We also need a more powerful gateway firmware. Let's flash both - the network
id comes from your config:

```bash
dotbot fw fetch  # pull the pinned pre-compiled firmwares (swarmit + dotbot-firmware)
dotbot device flash mari-gateway --probe 10  # flash the gateway
dotbot device flash swarmit-sandbox --probe 77  # the sandbox firmware - do this on each DotBot
```

(`device flash mari-gateway` / `flash swarmit-sandbox` fetch the pinned
firmware into `~/.dotbot/artifacts/` if it isn't already there.)

Now, run the gateway (the broker comes from your config):

```bash
dotbot run gateway -p /dev/cu.usbmodem0010500324491
```

### Deploy and control

You can flash as many DotBots as you want, all at once! First, how about making them spinnnn 🔄 🔄

```bash
# flash the whole fleet with a simple spinning app
# the -ys flags confirms (y) the flash,
# and tell the app to start (s) right away after flashing is done
dotbot swarm flash spin -ys
```

(`dotbot swarm` reads the same `dotbot.toml` as the rest - pass `--conn` /
`--swarm-id` to override it for one run. `spin` is a bundled app name -
`dotbot swarm flash --list` shows them all, and an explicit `.bin` path still
works. Names resolve to what `dotbot fw fetch` cached; `dotbot fw list` shows
the exact paths and versions on your machine.)

Then, flash another experiment:

```bash
dotbot swarm stop  # ensure all DotBots are in bootloader
dotbot swarm flash remote-control -ys  # this firmware lets DotBots be remote-controlled
```

Observe and control your swarm from a web interface:

```bash
dotbot run controller  # opens the console at http://localhost:8000/console/
```

Full walkthrough of fleet operations - status, OTA flash, start/stop, monitor -
is in the [`swarm` reference][swarm-doc].

### Calibrate positions (optional)

Give the DotBots real-world `(x, y)` with Lighthouse 2. It's a two-step flow:
**collect** a calibration by placing one DotBot on the four corners of your
site's field, then **push** it to the whole fleet - one capture calibrates the
whole site. This needs the `[calibrate]` extra (opencv, for the homography
solve):

```bash
pip install 'pydotbot[calibrate]'
```

First, flash the `calibrate` app and collect. Each corner is captured when you
press the DotBot's button:

```bash
dotbot swarm flash calibrate -ys          # the app that captures on a button press
dotbot swarm calibrate-lh2 collect        # the field's four corners -> solve -> save
```

This saves the calibration under `~/.dotbot/calibrations/<site>/` and prints
its id. Then push it to the whole fleet:

```bash
dotbot swarm calibrate-lh2 push <id>
```

Full walkthrough - choosing the points and the cabled alternative - is in the
[LH2 calibration guide][lh2-doc].

## Going further

- **Drive a single DotBot** end to end - build, flash, and control one DotBot:
  the [one-bot guide][one-bot-doc].
- **Position tracking with Lighthouse 2** - give the fleet real-world `(x, y)`,
  calibrated over the air: the [LH2 calibration guide][lh2-doc] (a cabled
  alternative is covered there too).
- **The controller + web UI** - drive and visualize a swarm from the browser:
  the [controller guide][controller-doc].
- **Build firmware from source** instead of `dotbot fw fetch` - needs
  [SEGGER Embedded Studio](https://www.segger.com/products/development-tools/embedded-studio/)
  and a clone of the source:
  ```bash
  git clone --recurse-submodules https://github.com/DotBots/DotBot-firmware.git
  export DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE=$(pwd)/DotBot-firmware
  dotbot fw build spin                     # -> ~/.dotbot/artifacts/dotbot-firmware-local/
  dotbot swarm flash spin -f local -ys     # flash your build instead of the release
  ```
  `swarmit-sandbox` and `mari-gateway` build the same way (see [`fw`][fw-doc]).
- **Everything else** - the full `dotbot` CLI (`fw` / `device` / `swarm` / `run`
  + `config`), the REST/WS and MQTT surfaces, and hardware notes: the
  [documentation][doc-link].

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
[cli-doc]: https://pydotbot.readthedocs.io/en/latest/cli/index.html
[fw-doc]: https://pydotbot.readthedocs.io/en/latest/cli/fw.html
[swarm-doc]: https://pydotbot.readthedocs.io/en/latest/cli/swarm.html
[config-doc]: https://pydotbot.readthedocs.io/en/latest/reference/configuration.html
[simulator-doc]: https://pydotbot.readthedocs.io/en/latest/guides/simulator.html
[controller-doc]: https://pydotbot.readthedocs.io/en/latest/guides/controller.html
[one-bot-doc]: https://pydotbot.readthedocs.io/en/latest/guides/one-bot.html
[lh2-doc]: https://pydotbot.readthedocs.io/en/latest/guides/lh2-calibration.html
[troubleshooting-doc]: https://pydotbot.readthedocs.io/en/latest/reference/troubleshooting.html
