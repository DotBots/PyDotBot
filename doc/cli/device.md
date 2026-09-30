# `dotbot device` - flash one cabled board

`dotbot device` programs **one board on your desk**, connected over a cable. It
talks to the board's on-board programmer over the SWD/J-Link interface - no
external probe needed for normal flashing. On the **DotBot v3** the programmer
(a J-Link-OB / DAPLink behind an SWD mux) is reached over **USB-C**; on an
nRF5340-DK over its micro-USB port. A separate J-Link is only required for
[`flash programmer`](#flash-the-programmer).

To put firmware on the **whole fleet over the air**, use [`swarm`](swarm.md)
instead. To build or fetch the images first, see [`fw`](fw.md).

```{tip}
**`device flash mari-gateway` flashes _firmware onto a board_.** The host-side
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
| `flash mari-gateway` | Turn an nRF5340-DK into the swarm gateway (both cores + network id) |
| `flash swarmit-sandbox` | Turn a DotBot v3 into a swarm sandbox host (bootloader + netcore + id) |
| `flash programmer` | Re-flash the board's on-board debug chip (J-Link OB / DAPLink), for first-time setup and recovery - needs a J-Link |
| `info` | Read a board's provisioning state (chip id + network id) |

## Flash an app

`flash` takes the names [`dotbot fw`](fw.md) builds and fetches: a role
(`swarmit-sandbox`, `mari-gateway`, see [Flash a role](#flash-a-role)) or an
app. It resolves `<app>` to its image in the DotBot-firmware set `-f` selects
(under `~/.dotbot/artifacts/`): sandboxed (`<app>-sandbox-<board>.bin`) on a
board that has a sandbox, bare (`<app>-<board>.hex`) with `--bare` or
elsewhere. An explicit `.hex`/`.bin` path is flashed as-is. It never builds.

```bash
# The bare DotBot app from the pinned release (fetched if missing)
dotbot device flash dotbot --bare --probe 77

# Your own build: build it, then flash the local set
dotbot fw build dotbot --bare
dotbot device flash dotbot --bare -f local --probe 77
```

`-b/--board` selects the **chip family and core** to program. The nrfjprog family
and coprocessor are derived from it: nRF52 boards → `-f NRF52`, no coprocessor;
nRF5340 → `-f NRF53` with `CP_APPLICATION`, or `CP_NETWORK` for a `*-net` board.

`-b` only sets the family/core nrfjprog is *told* to program; the CLI doesn't
read it back from the attached chip. Make sure the cabled board matches `-b` -
e.g. don't flash an nRF53 image onto a connected nRF52 (or vice versa).

```bash
# DotBot-firmware's own gateway onto an nRF52840-DK (nrfjprog -f NRF52 from the board)
dotbot device flash dotbot_gateway -b nrf52840dk --probe 10
```

### nRF5340 = two cores

The nRF5340's radio lives on the **net core**, so an app-core app also needs a
net-core image. Build and flash each for its own target - the app image is
`dotbot_gateway`, the net image is **`nrf5340_net`** (not `dotbot_gateway`):

```bash
# App core
dotbot device flash dotbot_gateway -b nrf5340dk-app --probe 10

# Net core (-b *-net routes to CP_NETWORK)
dotbot device flash nrf5340_net -b nrf5340dk-net --probe 10
```

**`flash` flags** (see `dotbot device flash --help` for the full list):

| Flag | Meaning |
|---|---|
| `-b, --board` | Target board → chip family + core (default `dotbot-v3`) |
| `--probe` | J-Link serial **prefix**, e.g. `77` (v3) or `10` (DK); omit it when only one probe is attached |
| `--bare` / `--sandboxed` | Bare-metal (`.hex`) or sandboxed (`.bin`) app; default: `[fw].bare`, else sandboxed where the board has a sandbox |
| `-f, --fw-version` | Which set: see [Which firmware: `-f`](#which-firmware--f) |

A flag that does not apply to what is being flashed is refused: `--bare` on a
role, or `--swarm-id` on an app, stops with a message naming what it applies to.

## Flash a role

`flash mari-gateway` and `flash swarmit-sandbox` flash a **complete system
firmware** (both cores) and write the **network identity** in one shot. Each
role sets its own board, so `-b` and `--bare` do not apply.

```bash
# nRF5340-DK → swarm gateway, from the pinned swarmit release
dotbot device flash mari-gateway --swarm-id 0100 --probe 10

# DotBot v3 → swarm sandbox host (the firmware that runs OTA apps)
dotbot device flash swarmit-sandbox --swarm-id 0100 --probe 77

# Your own builds
dotbot fw build swarmit-sandbox
dotbot device flash swarmit-sandbox --swarm-id 0100 -f local --probe 77
dotbot fw build mari-gateway --schedule big
dotbot device flash mari-gateway --swarm-id 0100 --schedule big -f local --probe 10
```

| Flag | `mari-gateway` | `swarmit-sandbox` |
|---|---|---|
| `--swarm-id` | 16-bit hex swarm id (or from config) | 16-bit hex swarm id (or from config) |
| `-f, --fw-version` | a swarmit release (it carries the gateway; Mari's releases carry no firmware), or a `mari` set | a swarmit release or set |
| `--schedule` | the TSCH schedule image, from a swarmit release that ships it or built by `dotbot fw build mari-gateway --schedule` | - |
| `--probe` | J-Link serial prefix | J-Link serial prefix |
| `--lh2-calibration` | - | optional LH2 calibration file to bake in |

The gateway's schedule is compiled into its net-core image, so `--schedule`
picks `03app_gateway_net-<schedule>.hex` from the set. swarmit releases that
include them ship all four; if the release has no image for that schedule, the
flash says so and suggests `-f latest` or
`dotbot fw build mari-gateway --schedule <schedule>`.

## Which firmware: `-f`

Every flash command takes the same `-f`:

| `-f` | Reads |
|---|---|
| omitted | the release this `dotbot` pins, fetched if missing |
| a tag, e.g. `0.10.0` | that release, fetched if missing |
| `latest` | the newest release, resolved to its tag first |
| `local`, or a name given with `fw build --as` | the set [`dotbot fw build`](fw.md) collected; an error that prints the build line if it is not there |
| a path containing `/` | a directory of release-named files, used as is (relative to the current directory); a source folder is refused with the `fw build --path` line that turns it into a set |

No flash command builds: a local build is always an explicit `dotbot fw build`.

A board flashed with `flash swarmit-sandbox` is what [`swarm flash`](swarm.md)
targets to run sandboxed apps over the air.

Both roles **erase the whole chip** first (`nrfjprog --recover` on each
core), so they work on a factory-fresh nRF5340 whose access port protection
(APPROTECT) is still on. They finish by disabling APPROTECT in UICR, so the board
stays flashable after a power cycle. Flashing an app or a file, and `info`,
never recover: on a protected chip they stop and say what to run. See
[Set up a bench](../guides/bench-setup.md).

## Inspect a board

```bash
dotbot device info --probe 77
```

Reports the chip id, the network identity, and whether the debug port stays open
across a power cycle. It never fails on a blank board - it says *not
provisioned* and how to fix it.

## Flash the programmer

`flash programmer` re-flashes the on-board debug chip's own firmware (J-Link
OB or DAPLink). It is only for a board's first flash at the factory, or for
recovery when that chip is in a bad state, and it **requires an external
J-Link**.

```bash
dotbot device flash programmer -p daplink -d ./programmer-firmware/
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
