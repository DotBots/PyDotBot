# The site editor

The site editor is where a room is set up and checked: its floor, origin, areas,
walls and objects, which LH2 calibration the controller uses, which station
covers which part of the floor and how far off a position may be. It writes
the site pack's `site.toml` and calibration files, and it never moves a robot.
Everything it does has a CLI twin, which it names where it matters, so a
script or an agent can do the same thing.

## Open it

- From the console: **Edit site** in the right pane's Layers tab, or
  <http://localhost:8000/controller/site-editor/> on the controller's machine.
  Opened this way it shows the robots live, and using a calibration changes
  what that controller uses.
- With no controller: `dotbot site edit [SITE]` serves it on 127.0.0.1 and
  opens it (`--headless` prints the URL instead). No robots, nothing in use;
  the files only.

It edits only from the controller's own machine, at `127.0.0.1` or
`localhost`. Opened from another machine it is **view only**: everything
shows, a banner says so, and Stop still works as in the console.

## The status line and the Checks home

The top bar carries one status line: what the controller uses, by name
(its tag, else the spin's date; the id is in its tooltip), and how many
robots have it. It is read from the controller every two seconds, so a
calibration chosen elsewhere or a restart shows up on its own. A second
part says when the page is looking at another file or has edited coverage
that is not saved yet. **Send** opens the push to the robots that lack it.

The left pane opens on **Checks**: rows of the same shape, each in one of
three states (good, needs you, cannot tell) with one action. A row whose
data is missing, such as which calibration the robots have when the fleet
sends no device info, is "cannot tell", never a pass and never a failure.

- **This room**: the floor, the origin (verified with a robot or not), the
  stations (fit, and whether they look moved since the other spins of this
  room), coverage (where the handover is), accuracy against the site's limit,
  the field and staging.
- **Before a run**: the robots (how many have the calibration in use) and
  the last verification with a robot on a measured spot.

**More** holds chargers and walls, **Present** (the status and the Room view,
large, for a projector; Esc leaves it), **Copy setup summary** (a block for
an experiment log: site, frame id, calibration in use, fit, accuracy, the
last verification, and the date; `dotbot swarm calibrate-lh2 show` prints
the same block), and **Snapshots**.

**Snapshots** keep `site.toml` and the id of the calibration in use together
under a name ("Monday class"); restoring one puts both back. The last 20
saved versions of `site.toml` are listed under them, each restorable, so any
Save can be undone.

## Edit the room

The top of the plan picks what you edit: **Floor** (its size and the origin),
**Areas**, **Walls**, **Objects** and **Stations**. Click to select,
Shift-click or drag a box to select several, drag to move, drag a handle to
resize, arrows to nudge; numbers can be typed in the inspector on the right
in mm, cm or m. **Room** draws the same room as a twin: the stations on poles
at their estimated heights, coverage tinted on the floor with the handover
line, the areas and the robots; drag to orbit it. **Table** lists everything
as rows, **File** shows `site.toml` as Save will write it, and can be edited
there. `?` lists the shortcuts.

The editor checks the rules as you go: one field at most, the field and
staging apart, names unique. **Save** shows what changes, line by line, then
writes `site.toml` (and, for edited coverage, a new calibration file). It
never touches a robot. A draft not yet saved is kept in this browser until you
save or discard it (**Discard unsaved changes** in the ⋯ menu); another tab of
the same room shows it too, and a reload re-applies it on top of a file that
changed meanwhile, keeping any text it could not re-apply for copying.

## Calibrations: use, send, verify

**Calibrations** in the left pane lists this room's LH2 calibration files by
name, grouped by the measurement they came from. A row shows its coverage on
the plan, compares with another file, renames it (the id never changes), or
archives it (moved into `archived/`, still found by its full id). Archiving or
renaming a file the controller's config or a snapshot names asks first. Files
written by an older version that this build cannot read are listed as older
files, not hidden.

**Use** is one sheet in three steps: the controller uses the file now (and
after a restart, if you tick it: written to the controller's config), it is
sent to the robots you tick (a robot takes a calibration in its bootloader,
so a running app stops; robots that send no device info cannot be ticked),
and a verification is offered after. It refuses a file not in this room, and
refuses to switch when the controller changed meanwhile, showing what it uses
now. Robots not sent to keep what they have.

## Stations

The Stations kind draws **coverage**: which station a robot uses where, by
the robots' own rule, with the **handover** line between them; and
**accuracy**, the predicted error of the station used across the floor,
against the site's `lh2_error_limit_mm` (2 mm by default). The probe (I)
reads both at any point. A coverage edge or the handover can be dragged
(**Add a handover** splits the floor when both stations cover all of it);
Save writes the result as a new calibration file and the original is kept. The
panel shows where the stations stand, estimated from the calibration, and
their heights; a spin that disagrees with this room's other spins is flagged
"Moved?". The rule robots follow is under "How robots choose a station, in
detail".

## The origin

The Floor kind moves the origin, with **Turn or shift** (T) or **From robots**
(C): put robots on spots you measured from where the origin should be, type
where each stands (one spot sets the origin, two set the turn as well, more
check each other), then drag the plan to carry the room over the dots (hold
Alt or Shift as you press to turn it) or nudge with the arrows until the dots
sit on their spots, and apply. The plan hatches where the origin may not go: robots report
unsigned millimetres, so every measured point must stay right of and below
it. Either tool writes a new frame id into `site.toml` and a new calibration
made from the one in use, then uses it. Until robots have it, the status line
says "origin moved" and offers Send; data logged before keeps the old origin.
`dotbot site turn` is the CLI twin.

## Verify a position

**Verify** (from the Checks home, the Use sheet, or a robot's inspector)
compares a robot's position with a spot you measured from the origin: park
the robot's sensor on the spot, type it, and read the robot while it stays
still for 2 s. The error is recorded in `checks.toml` beside the
calibrations, never in the calibration file itself, and the Checks home and
the setup summary name the last one. A robot that cannot say which
calibration it has can still be read; that check is recorded as unverified
and does not turn the origin green.

## A new room

With no site pack yet, the editor opens on **A new room**; from any site,
**New site…** in the ⋯ menu does the same.

1. **Name the room** (up to 16 letters, digits, `-` and `_`, since robots
   receive the name) and say where the origin is. Start from an empty floor, a floor
   of a known size, or a spin calibration already done. The controller
   switches to the new site at once; **Switch site…** goes back.
2. **Mount two stations** at opposite corners, outside the floor, high enough
   to see all of it; the plan shows where once the floor's size is known.
3. **Spin robots in the console**: its Localization tab spins the robots
   where they stand (they must run the calibrate-spin app) and saves a
   calibration in its own frame. The editor follows the spin as it runs.
4. **Put it in the room**: round the robots as they stood, from two robots
   that spun on measured spots (type where each is; the page checks the
   tape against the spin), or from a typed turn and shift. **Save and use**
   writes `site.toml` with the floor and field proposed from the spins, then
   the calibration placed in the room, then uses it.
5. Send it to the robots, then verify it with a robot on a measured spot.

The CLI path is the same steps: `dotbot swarm calibrate-lh2 collect --spin`,
then `dotbot site init <name> --from-calibration <id>`.

## See also

- [`dotbot site`](../cli/site.md) - `edit`, `new`, `init`, `turn`.
- [LH2 calibration](lh2-calibration.md) - collecting a calibration.
- [Configuration reference: sites](../reference/configuration.md#sites) - `site.toml` keys.
