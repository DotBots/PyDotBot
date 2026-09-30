# `dotbot fw` - firmware artifacts

Build, fetch, and inventory firmware **without touching hardware**. Flashing
lives elsewhere: one cabled board → [`dotbot device`](device.md), the fleet
over the air → [`dotbot swarm`](swarm.md).

Two verbs fill one cache, `~/.dotbot/artifacts/`, as mirror images of each
other, under the **same file names**:

| | From | Into |
|---|---|---|
| `dotbot fw fetch [ROLE\|APP]...` | a GitHub release | `<release>-<version>/`, e.g. `swarmit-0.10.0/` |
| `dotbot fw build [ROLE\|APP]...` | your source folders, via SEGGER Embedded Studio | `<source>-<set>/`, e.g. `swarmit-local/` |

Every flash command then picks one with `-f`: a release tag, `latest`, a set
you built (`local`, or a name you gave with `--as`), or a directory path. A
flash command fetches a missing release by itself, and **never builds**.

## Roles and apps

`build` and `fetch` take the names [`dotbot device flash`](device.md) takes:

| Name | What it is | Built from | `fw fetch` gets it from |
|---|---|---|---|
| `swarmit-sandbox` | the sandbox host of a DotBot: the swarmit bootloader and the network core | swarmit | the swarmit release |
| `mari-gateway` | the swarm gateway of an nRF5340-DK: both Mari gateway cores | mari, per schedule too | the swarmit release, with the per-schedule images when it ships them: Mari's releases publish no firmware |
| an app, e.g. `spin` | a DotBot-firmware app: sandboxed (`.bin`, flashed over the air) or bare (`.hex`, flashed by cable) | DotBot-firmware | the DotBot-firmware release |

With no name, `build` builds both roles and the apps a DotBot-firmware release
ships, and `fetch` downloads both releases. Sets are named by the source they
came from, so `dotbot device flash mari-gateway -f 0.10.0` names a swarmit
release, while `-f local` reads what `dotbot fw build mari-gateway` put in
`mari-local/`.

## Setup

`fw build` needs SEGGER Embedded Studio (SES) and your source folders. SES is
auto-detected only on macOS (a standard `/Applications/SEGGER/` install); set it
once per machine in `~/.dotbot/config.toml`:

```toml
# ~/.dotbot/config.toml  (once per machine)
[fw]
segger_dir = "/path/to/SEGGER Embedded Studio X.YY"
```

The source folders default to `repos/DotBot-firmware`, `repos/swarmit` and
`repos/mari` next to the `dotbot.toml` in use. Point elsewhere per project, with
a path relative to that file:

```toml
# ./dotbot.toml  (per project)
[fw.sources]
dotbot-firmware = "../DotBot-firmware"
swarmit = "../swarmit"
mari = "../mari"
```

or with `DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE` / `DOTBOT_FW_SOURCES_SWARMIT` /
`DOTBOT_FW_SOURCES_MARI`, or for one run with `--path`.

> **First SES build needs the nRF + CMSIS_5 packages.** A fresh SES install has
> no chip headers, so the build fails with `fatal error: 'nrf.h' file not found`.
> In SES, open **Tools → Package Manager** and install the **nRF** and
> **CMSIS_5** packages (`nrf.h` ships in the nRF one). One-time per SES install.

You do **not** need SES to run released firmware: `dotbot fw fetch` downloads
it, and the flash commands fetch what they need.

## Which command do I want?

| Goal | Command |
|---|---|
| Download the pinned releases | `dotbot fw fetch` |
| Download the sandbox host and gateway at another version | `dotbot fw fetch swarmit-sandbox -f 0.10.0` |
| Build everything from your source folders into `<source>-local/` | `dotbot fw build` |
| Build one app | `dotbot fw build spin` |
| Build the Mari gateway for one schedule, or all four | `dotbot fw build mari-gateway --schedule tiny` / `--schedule all` |
| Build from another folder into its own set | `dotbot fw build swarmit-sandbox --path ../wt-swarmit-x --as lh2-fix` |
| See what is cached, and where each set came from | `dotbot fw list` |
| List the boards `-t` takes | `dotbot fw targets` (may be removed) |
| A Makefile knob the CLI doesn't model | `dotbot fw make <args…>` (may be removed) |

## `build`

```bash
dotbot fw build                              # both roles and the release apps, set "local"
dotbot fw build spin dotbot                  # two apps, sandboxed on dotbot-v3
dotbot fw build dotbot --bare                # the bare-metal app instead
dotbot fw build swarmit-sandbox              # bootloader for -t + network core
dotbot fw build swarmit-sandbox --part netcore  # only the network core
dotbot fw build mari-gateway                 # the Mari gateway, default schedule
```

Each run copies the images into `~/.dotbot/artifacts/<source>-<set>/` under
their release file names (`bootloader-dotbot-v3.hex`,
`03app_gateway_app-nrf5340-app.hex`, `spin-sandbox-dotbot-v3.bin`, ...) and
records a `manifest.json` next to them: the source folder, its git sha, whether
it had uncommitted changes, the build configuration and a sha256 per image.
Each file is reported as `new`, `changed` or `unchanged`.

Each source builds through its own entry point, SES underneath: apps through
the DotBot-firmware Makefile, incrementally; `swarmit-sandbox` through
`make bootloader netcore` in swarmit; `mari-gateway` through `make gateway` in
mari's `firmware/`, and its schedule images through Mari's
`firmware/build-schedules.sh`. The swarmit and mari Makefiles always rebuild
in full. Their compiler output is shown only when a build fails, or with `-v`.

| Flag | Meaning |
|---|---|
| `ROLE\|APP` | `swarmit-sandbox`, `mari-gateway`, or an app name (repeatable); default: both roles and the release apps |
| `--part <part>` | `swarmit-sandbox` only, named as an argument: build just `bootloader` or `netcore` (repeatable) |
| `-t, --target <board>` | Board (default `dotbot-v3`); picks the apps and the swarmit-sandbox bootloader. See `dotbot fw targets` |
| `--bare` / `--sandboxed` | Apps only: bare-metal (`.hex`) or sandboxed (`.bin`). Default: `[fw].bare` in config, else sandboxed on boards that have a sandbox |
| `--schedule <name>\|all` | `mari-gateway` only, named as an argument: build the net image for this TSCH schedule (repeatable), in place of the default net image |
| `--path <folder>` | Build from this source folder for this run, relative to the current directory (every name must build from the same source) |
| `--as <name>` | Name the set (default `local`): flash commands take it as `-f <name>` |
| `--build-config Debug\|Release` | Default: `Debug` for the roles (what the swarmit release ships), `Release` for apps |
| `--rebuild` | Apps: force a full rebuild (swarmit and mari always rebuild in full) |
| `--print-path` | Print where each image would be collected, without building |
| `-v, --verbose` | Show the full build output as it runs |

A flag that does not apply to anything being built is refused, e.g.
`dotbot fw build swarmit-sandbox --schedule tiny` says `--schedule` only
applies to `mari-gateway`. `--schedule` and `--part` never pick their role for
you: `dotbot fw build --schedule tiny` is refused too, and points at
`dotbot fw build mari-gateway --schedule tiny`.

> **Flag mismatch to remember:** `fw` selects a board with `--target/-t`, but
> [`device flash`](device.md) uses `--board/-b`.

### Gateway schedules

The Mari gateway's TSCH schedule is compiled into its net-core image, so each
schedule is its own image. `--schedule` builds them under the names
[`device flash mari-gateway --schedule`](device.md#flash-a-role) looks for:

```bash
dotbot fw build mari-gateway --schedule all  # 03app_gateway_net-{tiny,medium,big,huge}.hex
dotbot device flash mari-gateway --schedule big -f local --swarm-id 0100
```

`--schedule` runs Mari's `firmware/build-schedules.sh` with the schedules
named, after `make gateway-app`. The script edits
`app/03app_gateway_net/main.c` for each schedule and restores it byte for byte
afterwards, so the mari source folder is left as it was. swarmit releases
that include them ship the same four images under the same names, so a
fetched release works too:

```bash
dotbot device flash mari-gateway --schedule big --swarm-id 0100
```

If the release you flash from lacks the schedule's image, the flash stops and
suggests fetching the newest release or building the image.

## Boards × apps

`dotbot fw targets` lists the boards. On a board with a sandbox (`dotbot-v2`,
`dotbot-v3`, `nrf5340dk`) the default is the sandboxed apps: `calibrate`,
`dotbot`, `dotbot-simple`, `motors`, `move`, `rgbled`, `spin`, `timer`. These
run over the air via [`dotbot swarm`](swarm.md).

The bare apps (`--bare`, or a board without a sandbox) include:

| Target | Chip | Apps |
|---|---|---|
| `dotbot-v1` / `v2` / `v3` | DotBot board (v3 = nRF5340) | `dotbot`, `log_dump` |
| `nrf52833dk`, `nrf52840dk` | nRF52833 / nRF52840 DK | `dotbot`, `dotbot_gateway`, `dotbot_gateway_lr`, `lh2_mini_mote_app`, `lh2_mini_mote_test`, `log_dump`, `sailbot` |
| `nrf5340dk-app` | nRF5340 **app core** | `dotbot`, `dotbot_gateway`, `dotbot_gateway_lr`, `log_dump`, `sailbot`, `lh2_mini_mote_*` |
| `nrf5340dk-net` | nRF5340 **net core** | `dotbot_gateway`, `dotbot_gateway_lr`, `log_dump`, `nrf5340_net` |
| `sailbot-v1` | SailBot | `log_dump`, `sailbot` |
| `freebot-v1.0` | FreeBot | `freebot` |
| `lh2-mini-mote` | LH2 mini-mote | `lh2_mini_mote_*`, `log_dump` |
| `xgo-v1` / `v2` | XGO | `xgo` |

Two different gateways, not to be confused:

- **`mari-gateway`** (a role, built from mari) is the swarm gateway that
  [`device flash mari-gateway`](device.md) puts on an nRF5340-DK.
- **`dotbot_gateway`** (an app, built from DotBot-firmware) is
  DotBot-firmware's own gateway app for a DK. On an nRF5340-DK it needs two images:
  `dotbot_gateway` on `nrf5340dk-app` **and** `nrf5340_net` on `nrf5340dk-net`.

## `fetch`

`dotbot fw fetch` downloads prebuilt firmware from two releases, **swarmit**
(the sandbox host and the Mari gateway) and **DotBot-firmware** (the apps),
into `~/.dotbot/artifacts/<release>-<version>/`, each with a `manifest.json`
recording where it came from. A role fetches the swarmit release and an app
fetches the DotBot-firmware release, whole: naming an app also checks that the
release ships it.

With no `-f` it fetches the **exact versions this `dotbot` is pinned to**:

- **swarmit** is also a Python dependency, so its firmware version is the
  installed `swarmit` package's.
- **DotBot-firmware** is not a Python package, so the version `dotbot` is built
  and tested against is declared in `dotbot` and bumped deliberately.

The two version independently, so a tag takes names from one release:

```bash
dotbot fw fetch                              # pinned versions, both releases
dotbot fw fetch spin -f latest               # newest DotBot-firmware release
dotbot fw fetch swarmit-sandbox -f 0.10.0    # a specific swarmit release
```

swarmit releases that include them also ship the per-schedule gateway images
(`03app_gateway_net-<schedule>.hex`), which `fetch` downloads with the rest.
For a release without them, build them with
`dotbot fw build mari-gateway --schedule`.

The cache is user-level and shared across projects (override the location with
`$DOTBOT_ARTIFACTS_DIR`).

## `list`

```bash
dotbot fw list
```

Every set in the cache with its images, and where it came from:

```text
swarmit-0.10.0  release 0.10.0, fetched 2026-09-28T09:12:40+00:00
  bootloader-dotbot-v3.hex
  ...
swarmit-local  built from swarmit@a1b2c3d (dirty)  2h ago
  bootloader-dotbot-v3.hex
  netcore-nrf5340-net.hex
```

A built set names the source folder and commit it was built from, and
`(dirty)` when that folder had uncommitted changes. Its `manifest.json` holds
the rest: the full folder path, build configuration, board and a sha256 per
image.

## `make` - the escape hatch

```{note}
`fw make`, `fw targets` and `fw clean` may be removed: they act on the
DotBot-firmware source folder alone, and `fw targets` repeats
`dotbot fw make list-targets`.
```

`dotbot fw make` runs `make` inside your `DotBot-firmware` source folder with the
resolved `SEGGER_DIR`, forwarding every argument verbatim. Use it only when
`build` doesn't model the Makefile knob you need.

```bash
dotbot fw make list-projects BUILD_TARGET=sandbox-dotbot-v3
```

Do **not** run `make docker` - that's the CI path.

## See also

- [`dotbot device`](device.md) - flash an image onto one cabled board.
- [`dotbot swarm`](swarm.md) - push a sandboxed app to the fleet over the air.
