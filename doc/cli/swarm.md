# `dotbot swarm` - operate the fleet over the air

Run experiments across many DotBots at once. `dotbot swarm` drives the
[SwarmIT](https://github.com/DotBots/swarmit) orchestration backend: it
OTA-flashes a sandbox app to every DotBot, starts/stops it, and watches status -
all wirelessly through a gateway.

For one cabled board, use [`device`](device.md). To build the apps you flash,
see [`fw`](fw.md). The host bridge and dashboard come from [`run`](run.md).

## The flow

```text
1. provision (once)   device flash mari-gateway + device flash swarmit-sandbox
2. host bridge        run gateway          (UART <-> MQTT)
3. the payload        fw fetch  (or fw build <app>)
4. operate            swarm               flash | start | stop | status | monitor
```

## 1. Provision once

Each DotBot needs the SwarmIT sandbox-host firmware; the gateway is an
nRF5340-DK running the Mari gateway firmware. Both are cabled flashes over
USB-C (the DotBot v3 has an on-board programmer - no separate J-Link needed).
Details and chip caveats live in [`device`](device.md).

```bash
dotbot device flash mari-gateway    --swarm-id 1234 --probe 10   # a DK -> gateway, net id 0x1234
dotbot device flash swarmit-sandbox --swarm-id 1234 --probe 77   # each DotBot -> sandbox host
```

## 2. Start the host bridge

The gateway board needs a host process bridging its UART to MQTT:

```bash
dotbot run gateway -m mqtts://argus.paris.inria.fr:8883 -p /dev/cu.usbmodem...
```

`run gateway` is the host *process*; `device flash mari-gateway` flashed the
*firmware* - same word, different objects.

## 3. Get the OTA payload

The OTA payload is a **sandboxed** app - a TrustZone non-secure `.bin`. Fetch a
release, or build your own:

```bash
dotbot fw fetch                        # the pinned releases -> ~/.dotbot/artifacts/<release>-<version>/
dotbot fw build spin                   # or build -> ~/.dotbot/artifacts/dotbot-firmware-local/spin-sandbox-dotbot-v3.bin
```

Sandbox apps include `dotbot`, `move`, `rgbled`, `spin`, `timer`. Artifact
names look like `spin-sandbox-dotbot-v3.bin`. (Bare `.hex` apps are *not* OTA
payloads - those are cabled via [`device flash`](device.md).)

The common demos have short names, so you rarely type a path - see
[Flash by name](#flash-by-name) below.

## 4. Connect

The connection is given as global options *before* the subcommand, or comes
from your dotbot config:

| Option | Meaning |
|---|---|
| `-n`, `--conn`, `--connection` | one string: `mqtts://host:port` (broker) or `/dev/ttyACM0` (serial gateway) |
| `-s`, `--swarm-id` | hex swarm id - **required for MQTT**, ignored for serial |
| `-c`, `--config-path` | swarmit's own `.toml` carrying the same fields, in place of the dotbot config |
| `-b`, `--baudrate` | serial baudrate (default `1000000`) |
| `-d`, `--devices` | restrict to a comma-separated subset of addresses |

See `dotbot swarm --help` for the full list.

```bash
dotbot config init --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234
```

This writes a site whose broker is that one and selects it, with your swarm
id, in `~/.dotbot/dotbot.toml`; `dotbot swarm` reads it like the other
`dotbot` commands (pass `--conn` / `--swarm-id` to override). If the broker
needs a login, save it once with `dotbot config login argus.paris.inria.fr`,
or set `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` for one run. The commands that act on robots
(`flash`, `start`, `stop`, `reset`) first print one line naming the site, broker
and swarm id they use and where each came from.

## 5. Operate the fleet

```bash
dotbot swarm status                                # who's out there + their state
dotbot swarm status -w                             # keep watching
dotbot swarm flash spin -ys                        # flash a bundled demo by name
dotbot swarm stop                                  # back to bootloader (before re-flashing)
dotbot swarm start                                 # (re)start the loaded app
dotbot swarm monitor                               # tail SWARMIT_EVENT_LOG from bots
dotbot swarm message "hello"                       # custom text to the bots
```

To replace a running experiment: `stop`, then `flash ... -ys`.

### Flash by name

`swarm flash` takes either a bundled app **name** or an explicit `.hex`/`.bin`
**path**. A name resolves to the matching `<app>-sandbox-dotbot-v3.bin` in the
dotbot-firmware set `-f` selects: the pinned release by default (fetched if
missing), `-f local` for your own `dotbot fw build`, or any other value
[`device`](device.md#which-firmware--f) takes. A path is flashed as-is. List
the names with `dotbot swarm flash --list` (they're also summarized at the foot
of `dotbot swarm flash --help`):

| Name | Firmware | What it does |
|---|---|---|
| `remote-control` | `dotbot-sandbox-dotbot-v3.bin` | drive the DotBot from the UI / keyboard / joystick |
| `spin` | `spin-sandbox-dotbot-v3.bin` | the DotBots spin in place |
| `lights` | `rgbled-sandbox-dotbot-v3.bin` | the on-board RGB LED |
| `calibrate` | `calibrate-sandbox-dotbot-v3.bin` | LH2 capture on the robot's own button |

For another board or an app outside this list, pass the full `.bin` path.

### `swarm flash` flags

| Flag | Meaning |
|---|---|
| `--list` | print the bundled-app names and exit |
| `-f`, `--fw-version` | which dotbot-firmware set a bundled name comes from (default: the pinned release) |
| `-y`, `--yes` | flash without the confirmation prompt |
| `-s`, `--start` | start the app once flashed |
| `-t`, `--ota-timeout` | seconds per OTA ACK (default `0.7`) |
| `-r`, `--ota-max-retries` | retries per OTA message (default `10`) |

## 6. LH2 calibration over the air

Capture a Lighthouse-2 calibration from one DotBot without a cable, then push
it to the fleet. Choosing the points, the span overlay and troubleshooting live
in the [LH2 calibration guide](../guides/lh2-calibration.md).

```bash
dotbot swarm flash calibrate -ys          # the app that captures on a button press
dotbot swarm calibrate-lh2 collect        # the field's four corners -> solve -> save
dotbot swarm calibrate-lh2 push <id>      # send it to every robot
```

`collect` asks for the four corners of the site's field in turn, and captures
each when you press the DotBot's button; `--over <area>`, `--square <mm>` and
`--points` choose other points. It solves every station and saves the result
under `~/.dotbot/calibrations/<site>/`. `push` then sends it to every robot -
the whole site shares one calibration. It takes a file path, a `--tag` or an
id prefix, and refuses robots that report another site. (`collect --push` sends
only to the robots whose captures built it.)

## Two web servers - don't mix them up

| Command | What it serves | Default port |
|---|---|---|
| `dotbot run controller` | drive/visualize Web UI + REST/WS | `8000` |
| `dotbot swarm serve` | SwarmIT FastAPI orchestration backend | `8001` |

`dotbot swarm` auto-discovers a running `serve` daemon; pass `--no-server` to
skip the probe and run an in-process controller for that one invocation. Use
`serve --local` for a zero-config local backend.

See `dotbot swarm <command> --help` for every flag.
