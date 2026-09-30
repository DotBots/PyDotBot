# `dotbot fw` - firmware artifacts

Build, fetch, and inventory firmware **without touching hardware**. Flashing
lives elsewhere: one cabled board → [`dotbot device`](device.md), the fleet
over the air → [`dotbot swarm`](swarm.md).

Two verbs fill one cache, `~/.dotbot/artifacts/`, as mirror images of each
other, under the **same file names**:

| | From | Into |
|---|---|---|
| `dotbot fw fetch [SOURCE]...` | a GitHub release | `<source>-<version>/`, e.g. `swarmit-0.10.0/` |
| `dotbot fw build [SOURCE]...` | your local checkouts, via SEGGER Embedded Studio | `<source>-<set>/`, e.g. `swarmit-local/` |

Every flash command then picks one with `-f`: a release tag, `latest`, a set
you built (`local`, or a name you gave with `--as`), or a directory path. A
flash command fetches a missing release by itself, and **never builds**.

## Sources

| Source | What it holds | `fw fetch` | `fw build` |
|---|---|---|---|
| `dotbot-firmware` | the apps: sandboxed (`.bin`, flashed over the air) and bare (`.hex`, flashed by cable) | yes | yes |
| `swarmit` | the sandbox host: the bootloader and the network core | yes, with the Mari gateway images | yes |
| `mari` | the Mari gateway, `mari-gateway` (app + net core images) | no: Mari's releases publish no firmware | yes, per schedule too |

The gateway images a release carries come with swarmit's release, so
`dotbot device flash-mari-gateway -f 0.10.0` names a swarmit release, while
`-f local` reads what `dotbot fw build mari` put in `mari-local/`.

## Setup

`fw build` needs SEGGER Embedded Studio (SES) and your checkouts. SES is
auto-detected only on macOS (a standard `/Applications/SEGGER/` install); set it
once per machine in `~/.dotbot/config.toml`:

```toml
# ~/.dotbot/config.toml  (once per machine)
[fw]
segger_dir = "/path/to/SEGGER Embedded Studio X.YY"
```

The checkouts default to `repos/DotBot-firmware`, `repos/swarmit` and
`repos/mari` next to the `dotbot.toml` in use. Point elsewhere per project, with
a path relative to that file:

```toml
# ./dotbot.toml  (per project)
[fw]
firmware_repo = "../DotBot-firmware"
swarmit_repo = "../swarmit"
mari_repo = "../mari"
```

or with `DOTBOT_FIRMWARE_REPO` / `DOTBOT_SWARMIT_REPO` / `DOTBOT_MARI_REPO`, or
for one run with `--checkout`.

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
| Download one source at another version | `dotbot fw fetch swarmit -f 0.10.0` |
| Build everything from your checkouts into `<source>-local/` | `dotbot fw build` |
| Build one app | `dotbot fw build dotbot-firmware -a spin` |
| Build the Mari gateway for one schedule, or all four | `dotbot fw build mari --schedule tiny` / `--schedule all` |
| Build from another checkout into its own set | `dotbot fw build swarmit --checkout ../wt-swarmit-x --as lh2-fix` |
| See what is cached, and where each set came from | `dotbot fw list` |
| List the boards `-t` takes | `dotbot fw targets` |
| A Makefile knob the CLI doesn't model | `dotbot fw make <args…>` |

## `build`

```bash
dotbot fw build                              # every source, set "local"
dotbot fw build dotbot-firmware              # the apps a release ships, sandboxed on dotbot-v3
dotbot fw build dotbot-firmware --bare       # the bare-metal apps instead
dotbot fw build swarmit                      # bootloader for -t + network core
dotbot fw build mari                         # the Mari gateway, default schedule
dotbot fw build -a spin -a bootloader        # the source is inferred from each -a
```

Each run copies the images into `~/.dotbot/artifacts/<source>-<set>/` under
their release file names (`bootloader-dotbot-v3.hex`,
`03app_gateway_app-nrf5340-app.hex`, `spin-sandbox-dotbot-v3.bin`, ...) and
records a `manifest.json` next to them: the checkout, its git sha, whether it
had uncommitted changes, the build configuration and a sha256 per image. Builds
are incremental; each file is reported as `new`, `changed` or `unchanged`.

| Flag | Meaning |
|---|---|
| `SOURCE` | `dotbot-firmware`, `swarmit`, `mari`; default: all three |
| `-a, --app <name>` | Build only this part (repeatable). swarmit: `bootloader`, `netcore`; mari: `mari-gateway`; dotbot-firmware: an app's project name. Default: what the source's release ships |
| `-t, --target <board>` | Board (default `dotbot-v3`); picks the dotbot-firmware apps and the swarmit bootloader. See `dotbot fw targets` |
| `--bare` / `--sandboxed` | Bare-metal (`.hex`) or sandboxed (`.bin`) dotbot-firmware apps. Default: `[fw].bare` in config, else sandboxed on boards that have a sandbox |
| `--schedule <name>\|all` | Build the Mari gateway net image for this TSCH schedule (repeatable), in place of the default net image |
| `--checkout <path>` | Build from this checkout for this run (needs exactly one `SOURCE`) |
| `--as <name>` | Name the set (default `local`): flash commands take it as `-f <name>` |
| `--build-config Debug\|Release` | Default: `Debug` for swarmit and mari (what the swarmit release ships), `Release` for dotbot-firmware |
| `--rebuild` | Force a full rebuild |
| `--print-path` | Print where each image would be collected, without building |
| `-v, --verbose` | Full SES output |

> **Flag mismatch to remember:** `fw` selects a board with `--target/-t`, but
> [`device flash`](device.md) uses `--board/-b`.

### Gateway schedules

The Mari gateway's TSCH schedule is compiled into its net-core image, so each
schedule is its own image. `--schedule` builds them under the names
[`device flash-mari-gateway --schedule`](device.md#flash-a-role) looks for:

```bash
dotbot fw build mari --schedule all          # 03app_gateway_net-{tiny,medium,big,huge}.hex
dotbot device flash-mari-gateway --schedule big -f local --swarm-id 0100
```

To select a schedule, the build temporarily edits
`app/03app_gateway_net/main.c` in the mari checkout and restores it byte for
byte afterwards. Releases carry only the default net image, so the schedule
images always come from a build.

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

- **`mari-gateway`** (source `mari`) is the swarm gateway that
  [`device flash-mari-gateway`](device.md) puts on an nRF5340-DK.
- **`dotbot_gateway`** (source `dotbot-firmware`) is DotBot-firmware's own
  gateway app for a DK. On an nRF5340-DK it needs two images:
  `dotbot_gateway` on `nrf5340dk-app` **and** `nrf5340_net` on `nrf5340dk-net`.

## `fetch`

`dotbot fw fetch` downloads prebuilt firmware from two release sources,
**swarmit** (the sandbox host and the Mari gateway) and **dotbot-firmware**
(the apps), into `~/.dotbot/artifacts/<source>-<version>/`, each with a
`manifest.json` recording where it came from.

With no `-f` it fetches the **exact versions this `dotbot` is pinned to**:

- **swarmit** is also a Python dependency, so its firmware version is the
  installed `swarmit` package's.
- **dotbot-firmware** is not a Python package, so the version `dotbot` is built
  and tested against is declared in `dotbot` and bumped deliberately.

The two version independently, so a tag needs its source:

```bash
dotbot fw fetch                              # pinned versions, both sources
dotbot fw fetch dotbot-firmware -f latest    # newest dotbot-firmware release
dotbot fw fetch swarmit -f 0.10.0            # a specific swarmit release
```

The cache is user-level and shared across projects (override the location with
`$DOTBOT_ARTIFACTS_DIR`).

## `list`

```bash
dotbot fw list
```

Every set in the cache with its images, and where it came from: the release
and fetch time, or the checkout, git sha, `dirty` flag and build time.

## `make` - the escape hatch

`dotbot fw make` runs `make` inside your `DotBot-firmware` checkout with the
resolved `SEGGER_DIR`, forwarding every argument verbatim. Use it only when
`build` doesn't model the Makefile knob you need.

```bash
dotbot fw make list-projects BUILD_TARGET=sandbox-dotbot-v3
```

Do **not** run `make docker` - that's the CI path.

## See also

- [`dotbot device`](device.md) - flash an image onto one cabled board.
- [`dotbot swarm`](swarm.md) - push a sandboxed app to the fleet over the air.
