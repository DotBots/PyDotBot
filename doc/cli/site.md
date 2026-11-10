# `dotbot site` - the places you work in

A **site** is a place and its usual way in: its frame and areas, and optionally
the broker it is reached through. A **site pack** is a site in its own folder,
so it can be committed, zipped or handed to someone: `<name>/site.toml` holds
its anchor, extent, connection and areas, and an optional
`<name>/calibrations/` holds the site's LH2 and camera calibration files.
Packs live in two homes, `sites/` beside a project's `dotbot.toml` and
`~/.dotbot/sites/`; the
[configuration reference](../reference/configuration.md#site-packs) has the
detail.

## Which command do I want?

| Goal | Command |
|---|---|
| Start working in a site someone shared with you | `dotbot site add <folder, zip, git URL or -> --use` |
| Switch to another site | `dotbot site use <name>` |
| See every site, its connection and which is active | `dotbot site list` |
| See one site in full | `dotbot site show [<name>]` |
| Share a site | `dotbot site export <name>` |
| Make a site around a spin calibration's robots | `dotbot site init <name> --from-calibration <id>` |
| Edit a site's floor, areas and calibrations in the browser | `dotbot site edit [<name>]` |
| Start a new site and edit it | `dotbot site new <name>` |
| Turn the frame on the floor or move zero | `dotbot site turn [<name>] --rotate DEG --shift X,Y` |

The [site editor guide](../guides/site-editor.md) covers the editor itself;
the console opens the same editor on the controller's site.

Onboarding at a site that publishes a pack is one command, then the controller:

```bash
curl -L https://example.org/lab.zip | dotbot site add - --use
BROWSER=true dotbot run controller --headless
```

## `add`

Copies a pack into `~/.dotbot/sites/<name>/`, which is seen from every folder
on this machine. If the project you are in has a pack of that name in its own
`sites/` folder, `add` still installs the pack and warns that the project's
hides it. The source can be:

- a pack folder, whose name is the site's name;
- a zip of one, as `site export` writes it, whose top folder is the site's name;
- `-`, to read such a zip from stdin;
- a git URL whose repository is a pack, named after the site.

```bash
dotbot site add ./lab                                     # a folder
dotbot site add lab.zip                                   # a zip from `site export`
curl -L https://example.org/lab.zip | dotbot site add -   # a zip on stdin
dotbot site add https://github.com/<org>/lab.git          # a git repository
```

A zip is not downloaded from a bare `https://...zip` argument: pipe it in with
`-` as above. `add` refuses to replace a pack of the same name unless you pass
`-f/--force`; a replacement that fails part-way leaves the old pack as it was.
It also refuses a site name that is not letters, digits, `-` and `_`, and a
pack holding links.

A pack whose `site.toml` names a broker is shown before it is added, and you are
asked to confirm, since commands in that site will connect there:

```text
Site pack lab names its connection:
  broker:    mqtts://broker.lab.example:8883
  swarm id:  (none; set swarm_id yourself)
Commands in lab will connect there unless you set conn yourself, and send it DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS when they are set.
Add site lab? [y/N]:
```

Saying yes (or passing `--yes`) is also what trusts that broker with the
login in `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS`: from then on, commands in
`lab` send it those with nothing else to set. The approved broker is recorded
beside the pack, in `~/.dotbot/sites/lab/.approved.toml`. A login saved with
`dotbot config login <host>` needs no approval, since only that host's broker
ever gets it; when the pack names a TLS broker you have no saved login for,
`add` ends by printing that command.

A re-add that changes the broker or swarm id asks again, showing the approved
broker and the new one. A pack with no connection is never asked about. When
the pack comes in on stdin, the question goes to the terminal.

If the installed pack's broker no longer matches the approved one (its
`site.toml` was edited, or it was copied into `~/.dotbot/sites/` by hand), the
login is withheld with a one-line warning naming the command that approves it
again, which re-adds the pack in place and asks, old against new:

```text
warning: not sending DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS to evil.example: site lab's broker changed since you approved mqtts://broker.lab.example:8883; approve it with `dotbot site add --force /home/me/.dotbot/sites/lab`
```

A pack in a project's `sites/` folder, or one you name by its path, needs no
approval: it is trusted like the project file beside it.

| Flag | Meaning |
|---|---|
| `--use` | Make it the active site too, as `site use` does. |
| `-y`, `--yes` | Don't ask; for scripts. |
| `-f`, `--force` | Replace a pack of the same name. |

Without `--use`, select the site with `dotbot site use lab`, `--site lab` or
`DOTBOT_SITE=lab`.

## `use`

Makes a site the active one by writing `site = "<name>"` to a file git does
not track, keeping its comments: `./dotbot.local.toml` when a project's
`dotbot.toml` is in use, else `~/.dotbot/dotbot.toml`. NAME is a pack in one
of the two homes, or a pack folder's path.

```bash
dotbot site use lab
dotbot site use ../packs/hall-b            # a pack by its path
dotbot site use c405-arena --project       # change the team's default, in dotbot.toml
```

| Flag | Meaning |
|---|---|
| `--user` | Write `~/.dotbot/dotbot.toml`, even in a project. |
| `--project` | Write the project's `dotbot.toml`, which is committed; it says so. |

It warns when something will hide the site or its connection: a closer file,
a `conn` or `swarm_id` in any of your files, or `DOTBOT_SITE` / `DOTBOT_CONN`,
since your own values beat the site's:

```text
wrote site = "lab" to ./dotbot.local.toml
warning: dotbot.local.toml sets conn, which hides lab's conn; `dotbot config unset conn` to follow the site
```

## `list` / `show`

`list` prints every site in the two homes, marking the active one with `*`,
with its connection and where it was read from. `show` prints one site, the
active one by default: where it is defined, its anchor and extent, its
connection, its areas with their roles, and its calibration folders.

```bash
dotbot site list
dotbot site show lab
```

## `export`

Writes the site `<name>` as a pack zip, `<name>.zip` in the current directory
by default.

```bash
dotbot site export lab                                    # lab.zip
dotbot site export lab --out ~/share/lab.zip --with-calibrations
```

| Flag | Meaning |
|---|---|
| `--out FILE` | The zip to write (default `<name>.zip`). |
| `--with-calibrations` | Include the site's calibration files, from its pack's `calibrations/` and from `~/.dotbot/calibrations/<name>/`. |
| `-f`, `--force` | Overwrite an existing zip. |

A pack is plain files, so `unzip`, `git clone` or `cp` into a project's
`sites/` folder work just as well as `site add`: that is how a pack is shared
with a team.

## `init`

Writes a site pack around the robots of a spin calibration
(`dotbot swarm calibrate-lh2 collect --spin`), so no mark on the floor is
needed. The **field** is the minimum-area rectangle around the robots' spin
centres, grown by what a spinning robot sweeps; the frame is aligned to the
field, zero at its top-left and +y along the robots' starting heading. The
**site** is the same starter site [`config init`](config.md) writes, built
around that field: 1.5 m of floor round it and a 600 mm `staging` strip along
its bottom (+y) edge, as wide as the field, so the demos that park robots in
staging run without editing the pack. It adds a `field+staging` area, the
rectangle the two make together, for a fleet spread over both. With `--size WxH` the site is W x H mm
with the field centred and the strip below it, so it must be at least 1200 mm
taller than the field. The pack carries no `[connection]`: pass `-n` to
commands run in it, as the ones `init` prints do, or add one to its
`site.toml`. The pack goes into the nearest
home (`sites/` beside the project's `dotbot.toml`, else `~/.dotbot/sites/`),
and the calibration, re-expressed in the new site, under
`~/.dotbot/calibrations/<name>/` with a new id and, when it has a tag, the tag
with `-<name>` appended. The calibration's spin radius goes into the
`site.toml` as `spin_radius_mm`, so a later `collect --spin` in the site uses
the same scale. The site name must fit the 16 characters a robot
stores, since `calibrate-lh2 push` sends it to them.

```bash
dotbot site init spun --from-calibration 6b1a1c96                  # 1.5 m of floor round the field
dotbot site init spun --from-calibration 6b1a1c96 --size 3000x4000 # the field centred in 3 x 4 m
```

| Flag | Meaning |
|---|---|
| `--from-calibration ID` | The spin calibration: an id prefix, a tag or a path. |
| `--size WxH` | The site's size in mm, with the field in its middle and staging below it; refused when they do not fit (at least the field's width, and its height plus 1200 mm). |
| `-f`, `--force` | Replace the `site.toml` of a site of that name. |

## `edit`

Serves the [site editor](../guides/site-editor.md) on `127.0.0.1` for a site
pack, the active site by default, and opens it in a browser (`--headless`
prints the URL instead; `--port` picks the port). With no controller behind
it, it edits the files only: no robots, nothing served. A controller serves
the same editor at `/controller/site-editor/` on its own site.

```bash
dotbot site edit                 # the active site
dotbot site edit lab --headless  # print the URL
```

## `new`

Writes a new pack, a field with floor round it and a staging strip below as
`config init` writes one, then opens the editor on it. The pack goes in
`sites/<name>/` beside the project's `dotbot.toml` when one is in use, else
in `~/.dotbot/sites/<name>/`; it is not made the active site. `--field` sets
the starter field (`2m`, `2x3m`, `1500mm`). The editor's **New site…** writes
a pack too, empty, of a known size or around a spin, and switches the
controller to it.

## `turn`

Turns a site's frame on the floor (`--rotate DEG` about `--about X,Y`, the
middle of the extent by default) or moves its zero (`--shift X,Y`, in mm of
the frame as it is now), as a new frame. No number in `site.toml` changes,
since the areas move with the frame; `site.toml` takes a new `frame` id and
each calibration of the site (or each `--calibration`) is saved again in the
new frame under a new id. It sends nothing: serve and push the new files
once they look right. `--anchor` replaces the note on where zero is. When
zero is a mark on the floor it asks first; `-y` does not ask. When a shift
would put a robot's spin centre below zero, the refusal names the largest
shift that fits.

```bash
dotbot site turn --rotate 2                # turn 2 degrees about the middle
dotbot site turn --shift 0,40 -y           # zero moves 40 mm down
```

## See also

- [The site editor](../guides/site-editor.md) - the same work in the browser.
- [Configuration reference: sites](../reference/configuration.md#sites) - `site.toml`, area roles, the two homes.
- [`dotbot config`](config.md) - `config show` names where the site, conn and swarm id came from.
- [LH2 calibration](../guides/lh2-calibration.md) - calibrating a site.
