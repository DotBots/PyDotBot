# Lighthouse 2 (LH2) calibration

Lighthouse 2 gives every DotBot a real-world **(x, y) position** on your arena
floor. Two SteamVR base stations sweep the room with IR; each bot's LH2 sensor
times the sweeps. Calibration is the one-time step that maps those raw sweep
counts to metric coordinates: you place one bot on four known corners of a
square, capture, and the resulting transform is pushed to the whole fleet.

You do this once per physical setup (move a base station -> recalibrate).

**The default flow is over the air** - drive one already-deployed bot through the
corners over the swarm, no cable and no firmware swap. If you'd rather calibrate
a single bot on the bench over USB, see
[LH2 calibration over a cable](lh2-calibration-cabled.md).

## Prerequisites

- A provisioned swarm: a gateway plus sandbox-host bots, reachable from your
  config (see [swarm](../cli/swarm.md)).
- Two LH2 base stations mounted ~2 m up, facing the arena.
- A square marked on the floor with a known side length.
- The `[calibrate]` extra (the homography solve uses opencv):

```bash
pip install --pre 'pydotbot[calibrate]'
```

## Capture and push

The calibration is a property of the **arena** (the base-station layout), not the
individual bot, so you capture once from any one bot and apply the result to the
whole fleet. Two steps:

```bash
dotbot swarm stop                                  # put the bots in READY
dotbot swarm lh2-calibration collect \
    --device BC3D3C8A2A6F8E68 -d 500               # capture from one bot -> solve -> save
dotbot swarm lh2-calibration push \
    ~/.dotbot/calibration-<UTC>.toml               # apply to every ready bot
```

`collect` walks one bot through the four corners - **top-left -> top-right ->
bottom-left -> bottom-right** - (capture only runs while the bot is in READY, so
`swarm stop` first). Each prompt triggers a raw-count capture over the air; it
then solves the homography and saves a `calibration-<UTC>.toml` under `~/.dotbot/`
(the path is printed at the end). Find the `--device` address with
`dotbot swarm status`.

`push` with **no `--device`** sends that calibration to **every ready bot** - the
whole arena shares one transform. It accepts a `calibration-*.toml` or the legacy
raw `calibration.out` payload; the format is picked by file extension.

```{note}
`collect --push` is a **single-bot shortcut**: it sends the result to *only* the
`--device` bot you captured from (handy to spot-check that one bot, or for a
single-bot setup). To calibrate the fleet, run the standalone `push` above - it
targets all ready bots.
```

Once pushed, the bots report positions, which show up live in the
[controller](../cli/run.md) Web UI.

### `collect` flags

| Flag | Default | Meaning |
|---|---|---|
| `--device` | (required) | DotBot link-layer address in hex (from `dotbot swarm status`). |
| `-d`, `--distance` | calibration default | Square side length, **in mm** (see sizing below). |
| `-n`, `--conn` / `-s`, `--swarm-id` | from config | Swarm connection, like the other `dotbot swarm` commands. |
| `--timeout` | `5` s | Seconds to wait for each capture before re-triggering. |
| `--retries` | `3` | Re-trigger this many times per corner before giving up. |
| `--tag` | - | Arena/setup label (e.g. `office-2x2m`) added to the filename + metadata. |
| `--push` | off | After solving, send to the captured `--device` bot **only** (use the standalone `push` for the whole fleet). |

See `dotbot swarm lh2-calibration collect --help` for the full list.

## Sizing `-d`

`-d` is the **side of your reference square, in millimeters**. The usable arena
is **5× the square side**, with the square centered (a `2·d` margin on every
side):

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

## Troubleshooting

- **Capture times out** - the bot isn't in READY (run `dotbot swarm stop`
  first), or it can't see both base stations. The address passed to `--device`
  must match one from `dotbot swarm status`.
- **Positions look skewed or mirrored** - the corners were captured out of
  order. Re-run `collect` and follow TL -> TR -> BL -> BR exactly.
- **Positions are scaled wrong** - `-d` didn't match the real square. It's in
  millimeters, not centimeters.
