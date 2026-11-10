# The site editor

The site editor is where a room is set up and checked: its floor, zero, areas,
walls and objects, which LH2 calibration the controller serves, which station
gives each robot its position and how far off that position may be. It writes
the site pack's `site.toml` and calibration files, and it never moves a robot.
Everything it does has a CLI twin, which it names where it matters, so a
script or an agent can do the same thing.

## Open it

- From the console: **Edit site** in the right pane's Layers tab, or
  <http://localhost:8000/controller/site-editor/> on the controller's machine.
  Opened this way it shows the robots live, and serving a calibration changes
  what that controller uses.
- With no controller: `dotbot site edit [SITE]` serves it on 127.0.0.1 and
  opens it (`--headless` prints the URL instead). No robots, nothing served;
  the files only.

It edits only from the controller's own machine, at `127.0.0.1` or
`localhost`. Opened from another machine it is **view only**: everything
shows, a banner says so, and Stop still works as in the console.

## The Checks home

The left pane opens on **Checks**: one verdict for the room, "Ready to run" or
"Not ready", computed from the goals below it. A goal whose data is missing,
such as which calibration the robots hold when the fleet does not report it,
is counted as an unknown and never as a pass.

- **Set up this room**: the floor, zero, the stations (and whether they look
  moved since the other spins of this room), who gives the fix, the predicted
  error against the site's limit, the field and staging, chargers and walls.
- **Before a run**: the served calibration, robots on the floor, which
  calibration they hold, and the last check on a mark.

Each goal has a button that opens where it is fixed. **Present** puts the
verdict over the plan, large, for a projector; Esc leaves it. **Copy
provenance** copies a block for an experiment log: site, frame id, served
calibration, residuals, predicted error, the last check, and the date
(`dotbot swarm calibrate-lh2 show` prints the same block).

**Restore points** keep `site.toml` and the served calibration's id together
under a name ("Monday class"); restoring one puts both back. The last 20
saved versions of `site.toml` are kept too, so any Save can be undone.

## Edit the room

The top of the plan picks what you edit: **Frame** (zero and the floor),
**Areas**, **Walls**, **Objects** and **Stations**. Click to select,
Shift-click or drag a box to select several, drag to move, drag a handle to
resize, arrows to nudge; numbers can be typed in the inspector on the right
in mm, cm or m. **Table** lists everything as rows, **File** shows `site.toml`
as Save will write it, and can be edited there. `?` lists the shortcuts.

The editor checks the rules as you go: one field at most, the field and
staging apart, names unique. **Save** shows what changes, line by line, then
writes `site.toml` (and, for new station boxes, a calibration file). It never
touches a robot. A draft not yet saved is kept in this browser until you save
or discard it.

## Calibrations and serving

**Calibrations** in the left pane lists this room's LH2 calibration files,
grouped by the spin they came from. A row previews its station boxes on the
plan, compares with another file, renames its tag (the id never changes), or
archives it (moved into `archived/`, still found by its full id).

**Serve** switches the calibration the controller uses, for this run, or also
at the next start (written to the controller's config). It refuses a file in
another frame. Serving changes the controller only: robots keep the
calibration they hold until it is pushed to them, which is the console's job,
in its Localization tab, with nothing ticked for you.

## Stations

The Stations kind draws **who gives the fix**, which station each robot keeps
by the robots' own rule from the station boxes, and the **predicted error**
of that station across the floor, against the site's `lh2_error_limit_mm`
(2 mm by default). The probe (I) reads both at any point. Station boxes can be
dragged; Save writes them into a new calibration file and the original is
kept. The inset shows where the stations stand, estimated from the
calibration, and their heights; a spin that disagrees with this room's other
spins is flagged "Moved?".

## Zero and the frame

The Frame kind turns the frame or moves zero, with **Turn** (T) or **Capture
zero from a robot** (C): a robot parked on the new zero, read while it stays
still. Either writes a new frame id into `site.toml` and the served
calibration re-expressed in the new frame, then serves it. Until robots hold
it, a banner says a push is needed, and data logged before is in the old
frame. `dotbot site turn` is the CLI twin.

## Check on a mark

**Check on a mark** (from the Checks home, or a robot's inspector) compares a
robot's position with a mark you taped and measured from zero: park the
robot's sensor on the mark, type the mark, and read the robot while it stays
still for 2 s. The error is recorded in `checks.toml` beside the
calibrations, never in the calibration file itself, and the Checks home and
the provenance block name the last one.

## A new room

With no site pack yet, the editor opens on **A new room**; from any site,
**New site…** in the ⋯ menu does the same.

1. **Name the room** (up to 16 letters, digits, `-` and `_`, since robots
   receive the name) and say where zero is. Start from an empty floor, a floor
   of a known size, or a spin calibration already done. The controller
   switches to the new site at once; **Switch site…** goes back.
2. **Mount two stations** at opposite corners, outside the floor, high enough
   to see all of it; the plan shows where once the floor's size is known.
3. **Spin robots in the console**: its Localization tab spins the robots
   where they stand (they must run the calibrate-spin app) and saves a
   calibration in its own frame. The editor follows the spin as it runs.
4. **Put it in the room**: round the robots as they stood, from two robots
   that spun on taped marks (type where each mark is; the page checks the
   tape against the spin), or from a typed turn and shift. **Write and
   serve** writes `site.toml` with the floor and field proposed from the
   spins, then the calibration placed in the room, then serves it.
5. Push it to the robots in the console, then check it on a mark.

The CLI path is the same steps: `dotbot swarm calibrate-lh2 collect --spin`,
then `dotbot site init <name> --from-calibration <id>`.

## See also

- [`dotbot site`](../cli/site.md) - `edit`, `new`, `init`, `turn`.
- [LH2 calibration](lh2-calibration.md) - collecting a calibration.
- [Configuration reference: sites](../reference/configuration.md#sites) - `site.toml` keys.
