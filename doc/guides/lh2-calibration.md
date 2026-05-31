# Lighthouse 2 (LH2) calibration

Lighthouse 2 gives every DotBot a real-world **(x, y) position** on your arena
floor. Two SteamVR base stations sweep the room with IR; each bot's LH2 sensor
times the sweeps. Calibration is the one-time step that maps those raw sweep
counts to metric coordinates: you place one bot on four known points of a
square, capture, and the resulting transform is pushed to the whole fleet.

You do this once per physical setup (move a base station → recalibrate).

## Prerequisites

- A DotBot v3 you can cable to your machine over USB-C (no external probe
  needed - the v3 flashes over its on-board programmer).
- Two LH2 base stations mounted ~2 m up, facing the arena.
- A square marked on the floor with a known side length, plus the
  `[calibrate]` extra installed:

```bash
pip install --pre 'pydotbot[calibrate]'
```

## 1. Flash the capture firmware

The `lh2_calibration` app streams raw LH2 counts over serial. Flash it to the
cabled bot (see [device](../cli/device.md) for serial-prefix selection):

```bash
dotbot device flash lh2_calibration -s 77      # board defaults to dotbot-v3
```

## 2. Capture the four reference points

Place the bot on the floor square and run the TUI. `-d` is the **side length of
the square, in millimeters**:

```bash
dotbot run lh2-calibration collect -p /dev/cu.usbmodem... -d 500
```

Move the bot to each corner - Top left → Top right → Bottom left → Bottom right
- pressing the matching button in the TUI at each. When all four are captured,
save. The calibration is written under `~/.dotbot/` (a `calibration-<UTC>.toml`).

Common `collect` flags:

| Flag | Default | Meaning |
|---|---|---|
| `-p`, `--port` | auto-detect | Serial port of the calibration firmware. |
| `-d`, `--distance` | - | Square side length, **in mm** (see sizing below). |
| `-n`, `--extra-lh-num` | `0` | Extra base stations beyond the first (0–5). |
| `--input-data` | - | Re-process a saved capture instead of capturing live. |

See `dotbot run lh2-calibration collect --help` for the full list.

**Sizing `-d`** - the usable arena is **5× the square side**, with the square
centered (a `2·d` margin on every side):

```
 ←─────────────── 5·d ────────────→
┌──────────────────────────────────┐  ↑
│                                  │  │
│                                  │  │
│           ←─── d ───→            │  │
│       TL  ●─────────●  TR        │  │
│           │         │            │ 5·d
│           │         │            │  │
│       BL  ●─────────●  BR        │  │
│                                  │  │
│←── 2·d ──→                       │  │
└──────────────────────────────────┘  ↓

                  ⌖ LH2 base station (mounted ~2 m up, facing the arena)
```

`TL/TR/BL/BR` are the four reference points you place the bot on; `d` is the
square side (`--distance`, in mm), `5·d` the resulting arena.

| `-d` | Square | Usable arena |
|---|---|---|
| `400` | 40 cm | 2.0 m × 2.0 m |
| `500` | 50 cm | 2.5 m × 2.5 m |
| `800` | 80 cm | 4.0 m × 4.0 m (used for the 725-bot Limerick run) |

## 3. Push the calibration to the fleet

Send the captured calibration over the air. Stop any running app first, then
push the `.toml` (see [swarm](../cli/swarm.md) for the connection config):

```bash
dotbot swarm -c tb-config.toml stop
dotbot swarm -c tb-config.toml calibrate-lh2 ~/.dotbot/calibration-<UTC>.toml
```

`calibrate-lh2` accepts either a `calibration-*.toml` or the legacy raw
`calibration.out` payload - the format is picked by file extension.

Once pushed, the bots report positions, which show up live in the
[controller](../cli/run.md) Web UI.

## First-time flashing (header path)

For a fresh board whose bootloader bakes the calibration in at compile time
(rather than receiving it over the air), export the saved calibration as a C
header instead:

```bash
dotbot run lh2-calibration apply ./lh2_calibration.h
```

The swarmit secure bootloader `#include`s this file; rebuild and reflash the
bootloader for it to take effect. For already-running bots, prefer the OTA path
in step 3 - no reflash needed.

## Troubleshooting

- **No counts in the TUI** - wrong `-p` port, or the bot can't see both base
  stations. Confirm line-of-sight and that the LEDs on the base stations are
  steady.
- **Positions look skewed or mirrored** - the corners were captured out of
  order. Re-run `collect` and follow TL → TR → BL → BR exactly.
- **Positions are scaled wrong** - `-d` didn't match the real square. It's in
  millimeters, not centimeters.
