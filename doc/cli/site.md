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
(`dotbot swarm calibrate-lh2 collect --spin`): its field is the rectangle the
robots stood in, grown by a robot's footprint, and its frame is the
calibration's, so no mark on the floor is needed. The pack goes into the
nearest home (`sites/` beside the project's `dotbot.toml`, else
`~/.dotbot/sites/`), and the calibration, re-expressed in the new site, under
`~/.dotbot/calibrations/<name>/` with a new id. The site name must fit the 16
characters a robot stores, since `calibrate-lh2 push` sends it to them.

```bash
dotbot site init spun --from-calibration 6b1a1c96                  # the site is the field
dotbot site init spun --from-calibration 6b1a1c96 --size 3000x4000 # the field centred in 3 x 4 m
```

| Flag | Meaning |
|---|---|
| `--from-calibration ID` | The spin calibration: an id prefix, a tag or a path. |
| `--size WxH` | The site's size in mm, with the field in its middle; refused when the field does not fit. |
| `-f`, `--force` | Replace the `site.toml` of a site of that name. |

## See also

- [Configuration reference: sites](../reference/configuration.md#sites) - `site.toml`, area roles, the two homes.
- [`dotbot config`](config.md) - `config show` names where the site, conn and swarm id came from.
- [LH2 calibration](../guides/lh2-calibration.md) - calibrating a site.
