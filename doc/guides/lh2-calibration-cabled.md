# LH2 calibration over a serial cable

The bench alternative to the [over-the-air flow](lh2-calibration.md): calibrate a
single DotBot connected over USB, with no swarm provisioned. Reach for this when
you're working with one bot on the bench, or before the fleet is set up. For
already-deployed bots, prefer the over-the-air flow - no cable, no firmware swap.

What LH2 calibration is, and the arena geometry (the `-d` square sizing), are
covered in the [main guide](lh2-calibration.md); this page is just the cabled
capture path.

## Prerequisites

- A DotBot v3 you can cable to your machine over USB-C (no external probe - the
  v3 flashes over its on-board programmer).
- Two LH2 base stations facing the arena, and a square marked on the floor (see
  [Sizing `-d`](lh2-calibration.md) in the main guide).
- The `[calibrate]` extra:

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

Place the bot on the floor square and run the TUI. `-d` is the side length of
the square, in millimeters:

```bash
dotbot run lh2-calibration collect -p /dev/cu.usbmodem... -d 500
```

Move the bot to each corner - Top left -> Top right -> Bottom left -> Bottom
right - pressing the matching button in the TUI at each. When all four are
captured, save. The calibration is written under `~/.dotbot/` (a
`calibration-<UTC>.toml`), the same place the over-the-air flow uses.

| Flag | Default | Meaning |
|---|---|---|
| `-p`, `--port` | auto-detect | Serial port of the calibration firmware. |
| `-d`, `--distance` | calibration default | Square side length, **in mm**. |
| `-n`, `--extra-lh-num` | `0` | Extra base stations beyond the first (0–5). |
| `--input-data` | - | Re-process a saved capture instead of capturing live. |

See `dotbot run lh2-calibration collect --help` for the full list.

## 3. Use the calibration

Send the saved calibration to the fleet over the air (the same command the
over-the-air flow uses - stop any running app first):

```bash
dotbot swarm stop
dotbot swarm lh2-calibration push ~/.dotbot/calibration-<UTC>.toml
```

### Bake it into the bootloader (header path)

For a fresh board whose bootloader bakes the calibration in at compile time
(rather than receiving it over the air), export the saved calibration as a C
header instead:

```bash
dotbot run lh2-calibration apply ./lh2_calibration.h
```

The swarmit secure bootloader `#include`s this file; rebuild and reflash the
bootloader for it to take effect. For already-running bots, prefer the
over-the-air push above - no reflash needed.

## Troubleshooting

- **No counts in the TUI** - wrong `-p` port, or the bot can't see both base
  stations. Confirm line-of-sight and that the base-station LEDs are steady.
- **Positions look skewed or mirrored** - the corners were captured out of
  order. Re-run `collect` and follow TL -> TR -> BL -> BR exactly.
- **Positions are scaled wrong** - `-d` didn't match the real square. It's in
  millimeters, not centimeters.
