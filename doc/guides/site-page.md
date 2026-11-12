# The site page

The site page is where a site is set up and checked: its extent, origin,
areas, walls and objects, which LH2 calibration the controller uses, which
station covers which part of the extent and how far off a position may be. It
writes the site pack's `site.toml` and calibration files, and it never moves a
robot. Everything it does has a CLI twin, which it names where it matters, so
a script or an agent can do the same thing.

## Words

The page uses the words of `site.toml` and the calibration file:

| Key | On the page | What it is |
|---|---|---|
| `site` | **Site** | the site's name, in the header |
| `extent_mm` | **Extent** | the rectangle positions are measured in; its top-left corner is the **origin**, (0, 0) |
| `frame` | **Frame** | the id of the coordinate system, shown under the Extent inspector |
| `anchor`, `[[anchor_spots]]` | **Anchor** | how the frame is tied to the floor |
| `areas` | **Areas** | named rectangles; `field` is one area's name |
| `[[walls]]`, `[[obstacles]]` | **Walls** | lines and shapes robots cannot cross |
| `[objects.<name>]` | **Objects** | chargers, docks, landmarks and camera positions |
| `[[station]]` | **Stations** | S0, S1... |
| `coverage_mm` | **Coverage** | where robots may use a station; where two overlap is the **handover**: the band where both are allowed, the line where robots switch |
| `tag` | **Tag** | a calibration's name in lists and the status line |

## Open it

- From the console: **Open Site ↗** in the right pane's Layers tab, or
  <http://localhost:8000/controller/site-editor/> on the controller's machine.
  Opened this way it shows the robots live, and using a calibration changes
  what that controller uses.
- With no controller: `dotbot site edit [SITE]` serves it on 127.0.0.1 and
  opens it (`--headless` prints the URL instead). No robots, nothing in use;
  the files only.

It edits only from the controller's own machine, at `127.0.0.1` or
`localhost`. Opened from another machine it is **view only**: everything
shows, a banner says so, and Stop still works as in the console.

## View and Checks

The page opens on **View**: the site in 3D, from the 3/4 corner view, with the
stations on poles at their estimated heights, coverage tinted on the extent
with the handover line, the areas and the robots. Drag to orbit; double-click
goes back to 3/4.

The top bar carries one status line: what the controller uses, by name (its
tag, else the spin's date; the id is in its tooltip), and how many robots have
it. It is read from the controller every two seconds, so a calibration chosen
elsewhere or a restart shows up on its own.

The left pane opens on **Checks**: rows of the same shape, each in one of
three states (good, needs you, cannot tell) with one action. A row whose data
is missing, such as which calibration the robots have when the fleet sends no
device info, is "cannot tell", never a pass and never a failure. The rows
cover the extent, the stations, the anchor, the areas, walls and objects, and
the robots. Beside them, **Snapshots** keep `site.toml` and the id of the
calibration in use together under a name ("Monday class"); restoring one puts
both back, and the last saved versions of `site.toml` are listed, each
restorable. **Copy setup summary** gives a block for an experiment log;
`dotbot swarm calibrate-lh2 show` prints the same.

## Edit, Save, Push

**Edit** turns the camera straight down and picks what you edit: **Extent**,
**Stations**, **Anchor**, **Areas**, **Walls** or **Objects** (each has a
number key). Click to select, Shift-click or drag a rectangle to select
several, drag to move, drag a handle to resize, arrows to nudge; numbers can
be typed in the inspector on the right in mm, cm or m. Esc goes back to View
and the draft stays. The ⋯ menu shows the site as tables, and `site.toml` as
Save will write it, editable there; `?` lists the shortcuts.

Every change goes into one draft, checked as you go: one field at most, the
field and staging apart, names unique. The draft is kept in this browser
until you save or discard it (**Discard unsaved changes** in the ⋯ menu);
another tab of the same site shows it too, and a reload re-applies it on top
of a file that changed meanwhile, keeping any text it could not re-apply for
copying.

**Save** opens a review of what changes, line by line, then writes
`site.toml` and at most one calibration file (when the draft moved the frame
or edited coverage); the calibration it was made from is kept. Saving never
touches a robot. **Push to robots**, in the title bar, then sends what the
controller uses to the robots that lack it; robots hold the calibration they
were last sent until then.

## The extent and the origin

In **Extent**, drag the origin to move it, or drag one of the extent's eight
handles to resize it. The frame moves rigidly: areas, walls, objects and
coverage keep their place on the floor. **Turn or shift** (T) types a turn
and a shift instead. The plan hatches where the origin may not go: robots
report unsigned millimetres, so every measured point must stay right of and
below it. Moving the frame gives it a new id, and Save writes it into
`site.toml` with a calibration in the new frame; data logged before keeps the
old origin. `dotbot site turn` is the CLI twin.

## Anchor with a robot

**Anchor with a robot…** ties the frame to the floor: put robots on spots you
measured from where the origin should be (one robot moved from spot to spot,
or several at once), type where each stands, and read each while it stays
still. One spot sets the origin, two set the turn as well, more check each
other. The page lines the frame up with the reads; the spots and how far each
read stayed from its spot are saved as `[[anchor_spots]]`. **Check again**
reads a robot on a measured spot later, and moves the frame only if you
choose; the result is recorded in `checks.toml` beside the calibrations. A
robot that cannot say which calibration it has can still be read, but that
check is recorded as unverified.

## Calibrations

**Calibrations** in the left pane lists this site's LH2 calibration files by
tag, grouped by the measurement they came from. A row shows its coverage on
the map, compares with another file, renames it (the id never changes), or
archives it (moved into `archived/`, still found by its full id). Archiving or
renaming a file the controller's config or a snapshot names asks first. Files
written by an older version that this build cannot read are listed as older
files, not hidden.

**Use** makes the controller use a file now, and after a restart if you tick
it (written to the controller's config). It refuses a file not placed in this
site, and refuses to switch when the controller changed meanwhile, showing
what it uses now. Robots keep what they hold until **Push to robots**. A
robot takes a calibration in its bootloader, so a running app is stopped
first and started again after; robots that send no device info cannot be
picked.

## Stations

**Stations** draws coverage, which station a robot uses where by the robots'
own rule with the handover line between them, and accuracy, the predicted
error of the station used across the extent, against the site's
`lh2_error_limit_mm` (2 mm by default). The point inspector (I) reads both at
any point. A coverage edge or the handover can be dragged (**Add a handover**
splits the extent when both stations cover all of it); Save writes the result
as a new calibration file. The panel shows where the stations stand,
estimated from the calibration, and their heights; a spin that disagrees with
this site's other spins is flagged "Moved?".

## A new site

With no site pack yet, the page opens on **A new site**; from any site, **New
site…** in the ⋯ menu does the same, and **Set up a site, step by step** walks
the steps below in the right pane.

1. **Name the site** (up to 16 letters, digits, `-` and `_`, since robots
   receive the name) and say where the origin is. The controller switches to
   the new site at once; **Switch site…** goes back.
2. **Mount two stations** at opposite corners, outside the extent, high
   enough to see all of it; the map shows where once the extent is known.
3. **Spin robots in the console**: its Localization tab spins the robots where
   they stand (they must run the calibrate-spin app) and saves a calibration
   in its own frame.
4. **Place it in this site** (from the spin's row in Calibrations, or **Place
   it in Site ↗** in the console): **Around** puts the origin a margin above
   and left of the robots as they stood, **Two marks** uses two robots that
   spun on taped marks (the page checks the tape against the spin), and
   **Typed** takes a turn and a shift. The placement goes into the draft;
   Save writes `site.toml` and the calibration placed in the site (the
   spin's file is kept), then the controller uses it.
5. Push it to the robots, then anchor the frame with a robot on measured
   spots.

The CLI path is the same steps: `dotbot swarm calibrate-lh2 collect --spin`,
then `dotbot site init <name> --from-calibration <id>`.

## See also

- [`dotbot site`](../cli/site.md) - `edit`, `new`, `init`, `turn`.
- [LH2 calibration](lh2-calibration.md) - collecting a calibration.
- [Configuration reference: sites](../reference/configuration.md#sites) - `site.toml` keys.
