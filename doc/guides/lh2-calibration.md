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
To calibrate with no marks on the floor, robots spinning in place can stand in
for the corners: see
[spin calibration over several stations](#spin-calibration-over-several-stations)
(experimental; the corner flow below stays the reference).

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
**Base-station channels.** Give each base station its own channel, 1 to 16.
Gaps are fine: a calibration of stations on channels 3 and 9 is pushed as it
is. A station's index is its channel minus 1.
```

```{note}
**Firmware order.** Robots must run the sandbox firmware matching this
`dotbot`. Update in this order: install the host (`pip install -U pydotbot`)
first, then flash the bootloader and network core of each robot by cable
(`dotbot device flash swarmit-sandbox`), then the apps over the air
(`dotbot swarm flash <app> -ys`). Flashing the apps first leaves them on a
bootloader they do not match.
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
robots whose sandbox firmware is older than this `dotbot` (reflash those by
cable, see [Upgrading from schema 2](#upgrading-from-schema-2)), and lists the
robots that still hold another calibration afterwards.

```{note}
`collect --push` is a **shortcut**: it sends the result only to the robots
whose captures built it. To calibrate the fleet, run the standalone `push`.
```

## Spin calibration over several stations

Robots spinning in place stand in for the corners, so no floor marks are
needed, and one collect solves every station that sees the spins. A circle two
stations both see **ties** them into one frame. This is experimental; the
[`swarm` reference](../cli/swarm.md#spin-calibration-experimental) has every
flag.

1. **Collect.** Spread the robots about 250 mm apart over the area, where the
   stations overlap, and spin them:

   ```bash
   dotbot swarm -d <addresses> calibrate-lh2 collect --spin --tag hall
   ```

   It refuses before flashing anything if a robot gives no device info or is
   resetting, flashes `calibrate-spin` onto the robots on another app, spins
   them, and saves a calibration in a free frame aligned to the robots'
   field. The last line it prints puts the robots' own app back; keep it for
   step 6. A circle of the wrong size that keeps the rest from solving is left
   out and reported. A station tied to no other stops the solve: add robots
   where it and another station both see them, or leave it out with
   `--drop-station N`.
2. **Read the report.** The same report is printed by `collect` and, at any
   time, from the file alone:

   ```bash
   dotbot swarm calibrate-lh2 show <id>
   ```

   Each station needs at least 3 circles, and 8 or more hold it better. A tie
   needs 2 circles shared by its two stations, at least 300 mm apart; 4 or
   more over 600 mm are advised, and the report marks a tie below that as
   weak. The predicted error map gives the worst cell and how many cells are
   over 10 mm.
3. **Append rounds until the ties are strong.** Ask where to spin next, move
   the robots there, and collect again onto the same calibration:

   ```bash
   dotbot swarm calibrate-lh2 show <id> --next-round 4
   dotbot swarm -d <addresses> calibrate-lh2 collect --spin --append <id>
   ```

   Every round is solved together and saved as a new file with a new id; the
   old file stays. Repeat with the new id until no tie is weak.
4. **Put it on a site.** Make a site around the robots' field:

   ```bash
   dotbot site init hall --from-calibration <id>
   ```

   This writes the site pack, with the spin radius as `spin_radius_mm`, and the
   calibration re-expressed in it with a new id. To join an existing site
   instead, move the calibration onto one already made there, through a
   station both solved:

   ```bash
   dotbot swarm calibrate-lh2 place <id> --to-calibration <site calibration>
   ```

   Two or more `--anchor ADDRESS=X,Y` robots in step 1, spinning on known site
   points, put the calibration in the site's frame directly and skip this
   step. Rounds are appended only to a free-frame calibration, so finish
   step 3 first.
5. **Push.** Each station goes to the robots in its own message, by station
   mask:

   ```bash
   dotbot swarm -d <addresses> calibrate-lh2 push <id in the site> --site hall --site-changed
   ```

   `--site-changed` lets it through to robots that still report another site.
   `push --dry-run` prints the messages without sending.
6. **Check it live.** Put the robots' app back with the line `collect`
   printed, then run the controller on the calibration and drive a robot
   across the station boundaries:

   ```bash
   dotbot swarm -d <addresses> flash -y -f <set> remote-control
   dotbot run controller --site hall --lh2-calibration <id in the site> --headless
   ```

   See [Check it on the map](#check-it-on-the-map).

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

## Upgrading from schema 2

Calibration files are schema 3: positions are solved on the true pinhole
camera point of each station. A schema 2 file, written before PyDotBot
0.32.0, is refused with `unsupported calibration schema_version 2`, and robots
need the matching sandbox firmware (swarmit 0.11.0 or newer). In order:

1. **Re-solve the calibration.** A schema 2 file keeps its raw sweep counts,
   so it re-solves with no new capture. Save this as `resolve.py`:

   ```python
   import pathlib, sys, tempfile
   from dotbot.calibration.lighthouse2 import LighthouseManager, read_calibration_file, write_calibration

   old = pathlib.Path(sys.argv[1])
   copy = pathlib.Path(tempfile.mkdtemp()) / old.name
   copy.write_text(old.read_text().replace("schema_version = 2", "schema_version = 3", 1))
   cal = read_calibration_file(copy)
   manager = LighthouseManager(cal.placements, cal.site, cal.valid_mm, cal.robot)
   manager.solve()
   print(write_calibration(manager.calibration(tag=cal.tag or None)))
   ```

   `python resolve.py ~/.dotbot/calibrations/<site>/calibration-<old>.toml`
   writes the schema 3 file under `~/.dotbot/calibrations/<site>/`, with a
   new id, and prints its path.
   Or run `collect` again.
2. **Reflash each robot by cable**, both cores and the calibration at once:
   `dotbot device flash swarmit-sandbox --lh2-calibration <schema 3 file>`.
   Never flash the new bootloader alone over an old network core.
3. **Over the air**, flash the sandbox apps again and check positions.

A reflashed robot reports no position until it holds a schema 3 calibration.

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

See `dotbot swarm calibrate-lh2 collect --help` for the full list.

## Troubleshooting

- **No capture arrives** - the `calibrate` app is not running on the DotBot
  (`dotbot swarm flash calibrate -ys`), or it cannot see the base stations.
- **A station is "not solved"** - it did not see all four points. Check its
  channel and that nothing blocks its view of the field.
- **Positions look skewed or mirrored** - the DotBot was placed on the corners
  out of order. Re-run `collect` and follow the prompts exactly.
- **Positions are off near the edges** - they are outside the calibrated span.
  Calibrate over the whole field rather than `--square` or `--over`.
- **The controller refuses the calibration** - it was made in another site.
  Select that site with `--site`, or calibrate this one.
- **`unsupported calibration schema_version 2`** - the file predates schema
  3; see [Upgrading from schema 2](#upgrading-from-schema-2).
- **`push` refuses robots and asks for a reflash** - their sandbox firmware
  predates schema 3; reflash them by cable as in step 2 above.
