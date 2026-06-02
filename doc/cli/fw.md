# `dotbot fw` - firmware artifacts

Build, fetch, and inventory firmware **without touching hardware**. Flashing
lives elsewhere: one cabled board → [`dotbot device`](device.md), the fleet
over the air → [`dotbot swarm`](swarm.md).

You get **bare apps** by default. Add `--sandbox` for the TrustZone
non-secure (NS) flavor that runs inside the swarm sandbox host.

## Setup

`dotbot fw` builds from a local `DotBot-firmware` checkout via SEGGER Embedded
Studio (SES), so it needs to find both. The checkout defaults to
`./DotBot-firmware/`; SES is auto-detected only on macOS (a standard
`/Applications/SEGGER/` install), so on Linux/Windows builds fail with
"SEGGER Embedded Studio ... wasn't found" until you point at it.

Your firmware checkout is per-project, so set it in the project's `./dotbot.toml`
(or export `DOTBOT_FIRMWARE_REPO`):

```toml
# ./dotbot.toml  (per project)
[fw]
firmware_repo = "/path/to/DotBot-firmware"
```

Your SES install rarely changes, so set it once per machine in
`~/.dotbot/config.toml`:

```toml
# ~/.dotbot/config.toml  (once per machine)
[fw]
segger_dir = "/path/to/SEGGER Embedded Studio X.YY"
```

> **First SES build needs the nRF + CMSIS_5 packages.** A fresh SES install has
> no chip headers, so the build fails with `fatal error: 'nrf.h' file not found`.
> In SES, open **Tools → Package Manager** and install the **nRF** and
> **CMSIS_5** packages (`nrf.h` ships in the nRF one). One-time per SES install.

## Which command do I want?

| Goal | Command |
|---|---|
| Compile an app, leave it in the SES `Output/` tree (path echoed) | `dotbot fw build` |
| Compile **and** collect a flat `<app>-<board>.hex` into `./artifacts/` | `dotbot fw artifacts` |
| Download a published release into `./artifacts/<version>/` | `dotbot fw fetch -f <version>` |
| List targets you can build | `dotbot fw targets [--sandbox]` |
| List what's cached locally | `dotbot fw list` |
| A Makefile knob the CLI doesn't model | `dotbot fw make <args…>` |

**`build` vs `artifacts`**: both compile via SES. `build` stops once SES is
done (output stays buried in the per-target `Output/` tree). `artifacts` goes
one step further and copies a flat, predictably-named `<app>-<board>.hex` into
`./artifacts/` - which is exactly where `dotbot device flash <app>` and the
swarm tools look. Reach for `artifacts` when you intend to flash; `build` when
you only want to know it compiles.

## `build` / `artifacts` flags

Both share the same build options:

| Flag | Meaning |
|---|---|
| `-a, --app <app>` | Build one app (default: every app for the target) |
| `-t, --target <target>` | Board/target (default: `dotbot-v3`) |
| `--build-config Debug\|Release` | Build configuration (default: `Release`) |
| `--sandbox` | TrustZone NS flavor → `sandbox-<board>`, emits `.bin` |
| `--rebuild` | Force a full rebuild (default: incremental) |
| `-v, --verbose` | Full SES output |

`artifacts` adds `--out <dir>` (default `./artifacts/`) and `--print-path`
(report where the artifact would land without building). See
`dotbot fw <cmd> --help` for the full list.

> **Flag mismatch to remember:** `fw` selects a board with `--target/-t`, but
> [`device flash`](device.md) uses `--board/-b`.

## Targets × apps

What builds where (verified `2026-05-30`). Run `dotbot fw targets` to list
bare targets, `dotbot fw targets --sandbox` for the sandbox set.

**Bare targets:**

| Target | Chip | Apps available |
|---|---|---|
| `dotbot-v1` / `v2` / `v3` | DotBot board (v3 = nRF5340) | `dotbot`, `lh2_calibration`, `log_dump` |
| `nrf52833dk`, `nrf52840dk` | nRF52833 / nRF52840 DK | `dotbot`, `dotbot_gateway`, `dotbot_gateway_lr`, `lh2_calibration`, `lh2_mini_mote_app`, `lh2_mini_mote_test`, `log_dump`, `sailbot` |
| `nrf5340dk-app` | nRF5340 **app core** | `dotbot`, `dotbot_gateway`, `dotbot_gateway_lr`, `lh2_calibration`, `log_dump`, `sailbot`, `lh2_mini_mote_*` |
| `nrf5340dk-net` | nRF5340 **net core** | `dotbot_gateway`, `dotbot_gateway_lr`, `log_dump`, `nrf5340_net` |
| `sailbot-v1` | SailBot | `lh2_calibration`, `log_dump`, `sailbot` |
| `freebot-v1.0` | FreeBot | `freebot` |
| `lh2-mini-mote` | LH2 mini-mote | `lh2_calibration`, `lh2_mini_mote_*`, `log_dump` |
| `xgo-v1` / `v2` | XGO | `xgo` |

**Sandbox targets** (`--sandbox` → `sandbox-dotbot-v2`, `sandbox-dotbot-v3`,
`sandbox-nrf5340dk`): apps `dotbot`, `dotbot-simple`, `motors`, `move`,
`rgbled`, `spin`, `timer`. These run over the air via
[`dotbot swarm`](swarm.md).

Notes:
- The gateway (`dotbot_gateway`) builds for the **DK** targets, not the DotBot
  boards - it runs on a DK plugged into your computer.
- The nRF5340 radio lives on the **net core**, so a gateway needs two images:
  `dotbot_gateway` on `nrf5340dk-app` **and** `nrf5340_net` on `nrf5340dk-net`.

## Examples

```bash
export DOTBOT_FIRMWARE_REPO=/path/to/DotBot-firmware

# Bare DotBot app for a DotBot v3 → ./artifacts/dotbot-dotbot-v3.hex
dotbot fw artifacts --app dotbot

# Just confirm an app compiles (no collection)
dotbot fw build --app sailbot -t nrf52840dk

# Gateway for an nRF5340-DK - both cores
dotbot fw artifacts --app dotbot_gateway -t nrf5340dk-app
dotbot fw artifacts --app nrf5340_net    -t nrf5340dk-net

# Sandbox (NS) "spin" app for a DotBot v3 → .bin, for OTA via swarm
dotbot fw artifacts --app spin -t dotbot-v3 --sandbox

# Pull a published release instead of building → ./artifacts/<version>/
dotbot fw fetch -f v1.0.0

# See what's cached
dotbot fw list
```

## `make` - the escape hatch

`dotbot fw make` runs `make` inside your `DotBot-firmware` checkout with the
workspace-resolved `SEGGER_DIR`, forwarding every argument verbatim. Use it
only when `build`/`artifacts` don't model the Makefile knob you need.

```bash
dotbot fw make list-projects
```

Do **not** run `make docker` - that's the CI path and crawls under emulation on
this machine.

## See also

- [`dotbot device`](device.md) - flash an artifact onto one cabled board.
- [`dotbot swarm`](swarm.md) - push a sandbox app to the fleet over the air.
- [LH2 calibration](../guides/lh2-calibration.md) - the `lh2_calibration` app workflow.
