# `dotbot device` - flash one cabled board

`dotbot device` programs **one board on your desk**, connected over a cable. It
talks to the board's on-board programmer over the SWD/J-Link interface - no
external probe needed for normal flashing. On the **DotBot v3** the programmer
(a J-Link-OB / DAPLink behind an SWD mux) is reached over **USB-C**; on an
nRF5340-DK over its micro-USB port. A separate J-Link is only required for
[`flash-programmer`](#flash-programmer).

To put firmware on the **whole fleet over the air**, use [`swarm`](swarm.md)
instead. To build the `.hex` first, see [`fw`](fw.md).

```{tip}
**`device flash-mari-gateway` flashes _firmware onto a board_.** The host-side
UART↔MQTT bridge process is a different thing - that's [`run gateway`](run.md).
```

```{note}
`dotbot device` drives **`nrfjprog`** (Nordic's nRF Command Line Tools), not
`nrfutil` - install it and put its `bin/` on your `PATH` before flashing.
```

## Commands

| Command | What it does |
|---|---|
| `flash <app\|file>` | Whole-chip program one app (or a `.hex`/`.bin`) onto the board |
| `flash-mari-gateway` | Turn an nRF5340-DK into the swarm gateway (both cores + network id) |
| `flash-swarmit-sandbox` | Turn a DotBot v3 into a swarm sandbox host (bootloader + netcore + id) |
| `flash-programmer` | Re-flash the board's on-board debug chip (J-Link OB / DAPLink) - needs a J-Link |
| `info` | Read a board's provisioning state (chip id + network id) |

## Flash an app

`flash` resolves `<app>` to `./artifacts/<app>-<board>.hex`, **building it if the
file isn't there**; an explicit `.hex`/`.bin` path is flashed as-is.

```bash
export DOTBOT_FIRMWARE_REPO=$(pwd)/repos/DotBot-firmware

# Build, then flash the bare DotBot app onto a DotBot v3 (board defaults to dotbot-v3)
dotbot fw artifacts --app dotbot
dotbot device flash dotbot -s 77
```

`-b/--board` selects the **chip family and core** to program. The nrfjprog family
and coprocessor are derived from it: nRF52 boards → `-f NRF52`, no coprocessor;
nRF5340 → `-f NRF53` with `CP_APPLICATION`, or `CP_NETWORK` for a `*-net` board.

`-b` only sets the family/core nrfjprog is *told* to program; the CLI doesn't
read it back from the attached chip. Make sure the cabled board matches `-b` -
e.g. don't flash an nRF53 image onto a connected nRF52 (or vice versa).

```bash
# Gateway onto an nRF52840-DK (device flash picks -f NRF52 from the board)
dotbot fw artifacts --app dotbot_gateway -t nrf52840dk
dotbot device flash dotbot_gateway -b nrf52840dk -s 10
```

### nRF5340 = two cores

The nRF5340's radio lives on the **net core**, so an app-core app also needs a
net-core image. Build and flash each for its own target - the app image is
`dotbot_gateway`, the net image is **`nrf5340_net`** (not `dotbot_gateway`):

```bash
# App core
dotbot fw artifacts --app dotbot_gateway -t nrf5340dk-app
dotbot device flash dotbot_gateway -b nrf5340dk-app -s 10

# Net core (-b *-net routes to CP_NETWORK)
dotbot fw artifacts --app nrf5340_net -t nrf5340dk-net
dotbot device flash nrf5340_net -b nrf5340dk-net -s 10
```

**`flash` flags** (see `dotbot device flash --help` for the full list):

| Flag | Meaning |
|---|---|
| `-b, --board` | Target board → chip family + core (default `dotbot-v3`) |
| `-s, --sn-starting-digits` | J-Link serial **prefix**, e.g. `77` (v3) or `10` (DK) |
| `--sandbox` | Resolve the sandbox-app flavor (`.bin`) |
| `--build-config` | `Debug` \| `Release` (default `Release`) |

## Flash a role

`flash-mari-gateway` and `flash-swarmit-sandbox` flash a **complete system firmware**
(both cores) and write the **network identity** in one shot. They auto-fetch the
named release into `./artifacts/` if it isn't cached.

```bash
# nRF5340-DK → swarm gateway
dotbot device flash-mari-gateway -n 0100 -f 0.8.0rc1 -s 10

# DotBot v3 → swarm sandbox host (the firmware that runs OTA apps)
dotbot device flash-swarmit-sandbox -n 0100 -f 0.8.0rc1 -s 77
```

| Flag | `flash-mari-gateway` | `flash-swarmit-sandbox` |
|---|---|---|
| `-n, --network-id` | 16-bit hex net id (required) | 16-bit hex net id (required) |
| `-f, --fw-version` | release to flash (required) | release to flash (required) |
| `-s, --sn-starting-digits` | J-Link serial prefix | J-Link serial prefix |
| `-l, --calibration` | - | optional LH2 calibration file to bake in |

A board flashed with `flash-swarmit-sandbox` is what [`swarm flash`](swarm.md)
targets to run sandboxed apps over the air.

## Inspect a board

```bash
dotbot device info -s 77
```

Reports the chip id and network identity. It never fails on a blank board - it
says *not provisioned* and how to fix it.

## flash-programmer

Re-flashes the on-board debug chip's own firmware (J-Link OB or DAPLink). This is
obscure, one-time-per-board bring-up and **requires an external J-Link**.

```bash
dotbot device flash-programmer -p daplink -d ./programmer-firmware/
```

| Flag | Meaning |
|---|---|
| `-p, --programmer-firmware` | `jlink` \| `daplink` (required) |
| `-d, --files-dir` | directory with the programmer firmware files (required) |
| `--probe-uid` | pyOCD probe UID, when multiple probes are attached |

```{note}
**Never run `nrfjprog` (or these commands) under `sudo`.** One sudo run leaves
`/tmp/boost_interprocess/` owned by root and every later call fails with
*Operation not permitted*. Recover with
`sudo rm -rf /tmp/boost_interprocess`.
```
