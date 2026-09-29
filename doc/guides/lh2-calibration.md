# Lighthouse 2 (LH2) calibration

Lighthouse 2 gives every DotBot a real-world **(x, y) position** in your
[site](../reference/configuration.md#sites). SteamVR base stations sweep the
room with IR; each DotBot's LH2 sensor times the sweeps. Calibration is the
step that maps those raw sweep counts to millimetres: you place one DotBot on
four known points, by default the corners of the site's **field**, capture at
each, and push the result to the whole fleet.

You do this once per physical setup (move a base station -> recalibrate).

**The default flow is over the air** - one already-deployed DotBot, no cable
and no firmware swap. If you'd rather calibrate a single DotBot on the bench
over USB, see [LH2 calibration over a cable](lh2-calibration-cabled.md).

## Prerequisites

- A provisioned swarm: a gateway plus sandbox-host DotBots, reachable from your
  config (see [swarm](../cli/swarm.md)).
- LH2 base stations mounted ~2 m up, facing the field.
- A site whose field matches the floor: `dotbot config init --field <size>`
  writes one, and the [configuration reference](../reference/configuration.md#sites)
  covers measuring your own. Tape the field's corners on the floor.
- The `[calibrate]` extra (the homography solve uses opencv):

```bash
pip install 'pydotbot[calibrate]'
```

```{note}
**Base-station channels.** Set your base stations to channels 1, 2, ... N,
with no gaps, one channel per station. Avoid channel 14 for now: it is a known
issue.
```

## Choose the points

By default `collect` uses the four corners of the site's field. A four-point
calibration is tight inside the span of its points and its error grows
outside it, so the whole field is the right default; a smaller span only saves
taping. Three flags choose other points, and they are mutually exclusive:

| Command | Points |
|---|---|
| `collect` | The field's four corners. |
| `collect --over dev-corner` | Another area's four corners, e.g. a bench corner for development work. |
| `collect --square 800` | The corners of an 800 mm square centred in the field. Quicker to tape; the rest of the field is extrapolated, and `collect` says so. |
| `collect --points ...` | Points you give by hand, repeatable: `x,y` in mm, an area name or `x,y,w,h` for its centre, `<area>:<corner>`, or `<area>:corners` for all four. |

The calibration file records which of these you used, as its
[`points_from`](../reference/configuration.md#how-calibration-points-were-chosen).

A corner mark is where the DotBot's photodiode lands with the robot inside the
rectangle, its PCB edges on the rectangle's lines and its nose toward the
nearest top or bottom edge. `collect` prints each position as it asks for it.

## Capture and push

The calibration belongs to the **site** (the base-station layout), not to the
DotBot, so you capture once from any one DotBot and push the result to the
whole fleet.

Flash and start the `calibrate` app, which captures when you press the
DotBot's button:

```bash
dotbot swarm stop                     # DotBots back in the bootloader
dotbot swarm flash calibrate -ys      # flash and start the calibrate app
dotbot swarm calibrate-lh2 collect    # the field's four corners -> solve -> save
```

`collect` asks for the points in order - **top-left -> top-right ->
bottom-left -> bottom-right**. Place the DotBot on each, and press its button
once it is still. It then solves every station that saw all four points and
saves `calibration-<UTC>-<id>.toml` under `~/.dotbot/calibrations/<site>/`,
printing the path, the id and the command to push it:

```bash
dotbot swarm calibrate-lh2 push <id>  # send it to every robot
```

`push` takes a file path, the exact `--tag` the calibration was collected
with, or a prefix of its id. It refuses robots that report another site, and
lists the robots that still hold another calibration afterwards.

```{note}
`collect --push` is a **shortcut**: it sends the result only to the robots
whose captures built it. To calibrate the fleet, run the standalone `push`.
```

`--device <addr>` still captures from Enter, with the robot's app stopped
(READY), instead of from the button; it is deprecated in favour of the
calibrate app.

## Check it on the map

Run the controller on the calibration:

```bash
dotbot run controller --lh2-calibration <id> --headless
```

In the console, the **Calibrated span** layer outlines where the calibration
was fitted and hatches the rest of the site: a position in the hatch is
extrapolated. Its tooltip gives the calibration's tag and id, its age in days
and how its points were chosen.

The controller warns at load when the calibration is older than
`[run.controller] lh2_calibration_max_age_days` (default 30, `0` never warns),
and when robots hold calibrations for stations it did not solve. A moved
station keeps its channel, so age is the only reminder that one might have
moved.

A calibration belongs to the site it was made in. The controller refuses one
from another site, and one whose recorded anchor differs from the site's. To
move a calibration into another site's frame without capturing again, use
`dotbot swarm calibrate-lh2 reframe`.

## `collect` flags

| Flag | Default | Meaning |
|---|---|---|
| `--over AREA` | - | Calibrate over another area's corners. |
| `--square MM` | - | Calibrate over a square this many mm wide, centred in the field. |
| `--points` | the field's corners | Points given by hand (see above). |
| `--site` | from config | The site the points are in, and the folder the calibration is saved under. |
| `--tag` | - | A label (e.g. `hall-2x4m`) added to the metadata; `push` and `--lh2-calibration` accept it. |
| `--push` | off | After solving, send to the robots whose captures built it. |
| `-n`, `--conn` / `-s`, `--swarm-id` | from config | Swarm connection, like the other `dotbot swarm` commands. |
| `--device` | - | Deprecated: capture from Enter on this DotBot, in READY. |

See `dotbot swarm calibrate-lh2 collect --help` for the full list.

## Troubleshooting

- **No capture arrives** - the `calibrate` app is not running on the DotBot
  (`dotbot swarm flash calibrate -ys`), or it cannot see the base stations.
- **A station is "not solved"** - it did not see all four points. Check its
  channel (1..N, no gaps) and that nothing blocks its view of the field.
- **Positions look skewed or mirrored** - the DotBot was placed on the corners
  out of order. Re-run `collect` and follow the prompts exactly.
- **Positions are off near the edges** - they are outside the calibrated span.
  Calibrate over the whole field rather than `--square` or `--over`.
- **The controller refuses the calibration** - it was made in another site.
  Select that site with `--site`, or calibrate this one.
