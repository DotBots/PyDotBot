# `dotbot swarm` - operate the fleet over the air

Run experiments across many robots at once. `dotbot swarm` drives the
[SwarmIT](https://github.com/DotBots/swarmit) orchestration backend: it
OTA-flashes a sandbox app to every bot, starts/stops it, and watches status -
all wirelessly through a gateway.

For one cabled board, use [`device`](device.md). To build the apps you flash,
see [`fw`](fw.md). The host bridge and dashboard come from [`run`](run.md).

## The flow

```text
1. provision (once)   device flash-mari-gateway + device flash-swarmit-sandbox
2. host bridge        run gateway          (UART <-> MQTT)
3. build the payload  fw artifacts --sandbox  (or fw fetch)
4. operate            swarm               flash | start | stop | status | monitor
```

## 1. Provision once

Each robot needs the SwarmIT sandbox-host firmware; the gateway is an
nRF5340-DK running the Mari gateway firmware. Both are cabled flashes over
USB-C (the DotBot v3 has an on-board programmer - no separate J-Link needed).
Details and chip caveats live in [`device`](device.md).

```bash
dotbot device flash-mari-gateway      -n 1234 -s 10 -f 0.8.0rc1   # a DK -> gateway, net id 0x1234
dotbot device flash-swarmit-sandbox -n 1234 -s 77 -f 0.8.0rc1   # each bot -> sandbox host
```

## 2. Start the host bridge

The gateway board needs a host process bridging its UART to MQTT:

```bash
dotbot run gateway -m mqtts://argus.paris.inria.fr:8883 -p /dev/cu.usbmodem...
```

`run gateway` is the host *process*; `device flash-mari-gateway` flashed the
*firmware* - same word, different objects.

## 3. Build the OTA payload

The OTA payload is a **sandbox** app - a TrustZone non-secure `.bin`. Build it,
or fetch a pre-compiled release:

```bash
dotbot fw artifacts --sandbox          # builds -> ./artifacts/<app>-sandbox-<board>.bin
dotbot fw fetch -f 0.8.0rc1            # or pull from a release into ./artifacts/<version>/
```

Sandbox apps include `dotbot`, `move`, `rgbled`, `spin`, `timer`. Artifact
names look like `spin-sandbox-dotbot-v3.bin`. (Bare `.hex` apps are *not* OTA
payloads - those are cabled via [`device flash`](device.md).)

## 4. Connect

The connection is given as global options *before* the subcommand, or in a
`.toml` via `-c`:

| Option | Meaning |
|---|---|
| `-n`, `--conn`, `--connection` | one string: `mqtts://host:port` (broker) or `/dev/ttyACM0` (serial gateway) |
| `-s`, `--swarm-id` | hex swarm id - **required for MQTT**, ignored for serial |
| `-c`, `--config-path` | a `.toml` carrying the same fields |
| `-b`, `--baudrate` | serial baudrate (default `1000000`) |
| `-d`, `--devices` | restrict to a comma-separated subset of addresses |

See `dotbot swarm --help` for the full list.

```bash
dotbot config init --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234
```

This writes `./dotbot.toml`; `dotbot swarm` discovers it from the current
directory like the other `dotbot` commands (pass `--conn` / `--swarm-id` / `-c`
to override). If the broker needs auth, set `DOTBOT_MQTT_USER` /
`DOTBOT_MQTT_PASS`.

## 5. Operate the fleet

```bash
dotbot swarm status                                # who's out there + their state
dotbot swarm status -w                             # keep watching
dotbot swarm flash ./artifacts/spin-sandbox-dotbot-v3.bin -ys
dotbot swarm stop                                  # back to bootloader (before re-flashing)
dotbot swarm start                                 # (re)start the loaded app
dotbot swarm monitor                               # tail SWARMIT_EVENT_LOG from bots
dotbot swarm message "hello"                       # custom text to the bots
```

To replace a running experiment: `stop`, then `flash ... -ys`.

### `swarm flash` flags

| Flag | Meaning |
|---|---|
| `-y`, `--yes` | flash without the confirmation prompt |
| `-s`, `--start` | start the app once flashed |
| `-t`, `--ota-timeout` | seconds per OTA ACK (default `0.7`) |
| `-r`, `--ota-max-retries` | retries per OTA message (default `10`) |

## 6. Push an LH2 calibration over the air

Send a calibration (captured from one cabled bot - see
[LH2 calibration](../guides/lh2-calibration.md)) to the whole fleet:

```bash
dotbot swarm stop
dotbot swarm calibrate-lh2 ~/.dotbot/calibration-<UTC>.toml
```

It accepts a `calibration-*.toml` or the legacy raw payload; the format is
picked by file extension.

## Two web servers - don't mix them up

| Command | What it serves | Default port |
|---|---|---|
| `dotbot run controller -w` | drive/visualize Web UI + REST/WS | `8000` |
| `dotbot swarm serve` | SwarmIT FastAPI orchestration backend | `8001` |

`dotbot swarm` auto-discovers a running `serve` daemon; pass `--no-server` to
skip the probe and run an in-process controller for that one invocation. Use
`serve --local` for a zero-config local backend.

See `dotbot swarm <command> --help` for every flag.
