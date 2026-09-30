# `dotbot site` - the places you work in

A **site** is a place and its usual way in: its frame and areas, and optionally
the broker it is reached through. A **site pack** is a site in its own folder,
so it can be committed, zipped or handed to someone: `<name>/site.toml` holds
the keys of a `[sites.<name>]` table, and an optional `<name>/calibrations/`
holds the site's LH2 and camera calibration files. How packs are found, and how
they relate to inline `[sites.*]` tables, is in the
[configuration reference](../reference/configuration.md#site-packs).

## Which command do I want?

| Goal | Command |
|---|---|
| Start working in a site someone shared with you | `dotbot site add <folder, zip, git URL or -> --use` |
| Switch to another site | `dotbot site use <name>` |
| See every site, its connection and which is active | `dotbot site list` |
| See one site in full | `dotbot site show [<name>]` |
| Share a site, or move an inline table into a pack | `dotbot site export <name>` |

Onboarding at a site that publishes a pack is one command, then the controller:

```bash
curl -L https://example.org/lab.zip | dotbot site add - --use
BROWSER=true dotbot run controller --headless
```

## `add`

Copies a pack into `~/.dotbot/sites/<name>/`, one of the default `site_dirs`,
so any config on this machine can then name the site. The source can be:

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
Commands in lab will connect there unless you set conn yourself.
Add site lab? [y/N]:
```

A re-add that changes the broker or swarm id asks again, showing old and new. A
pack with no connection is never asked about. When the pack comes in on stdin,
the question goes to the terminal.

| Flag | Meaning |
|---|---|
| `--use` | Make it the active site too, as `site use` does. |
| `-y`, `--yes` | Don't ask; for scripts. |
| `-f`, `--force` | Replace a pack of the same name. |

Without `--use`, select the site with `dotbot site use lab`, `--site lab` or
`DOTBOT_SITE=lab`.

## `use`

Makes a site the active one by writing `site = "<name>"` into the config file in
use, the one `dotbot config path` reports, keeping its comments. With no config
file in use, it creates `~/.dotbot/dotbot.toml` holding just that line.

```bash
dotbot site use lab
```

It warns when something will override the site's connection - a `conn` or
`swarm_id` in your file, or a `DOTBOT_CONN` style variable - since your own
values beat the site's:

```text
wrote site = "lab" to ./dotbot.toml
warning: dotbot.toml sets conn at top level, which overrides lab's connection; remove it to follow the site
```

## `list` / `show`

`list` prints every site the config can name, marking the active one with `*`,
with its connection and where it was read from. `show` prints one site, the
active one by default: where it is defined, its anchor and extent, its
connection, its areas with their roles, and its calibration folders.

```bash
dotbot site list
dotbot site show lab
```

## `export`

Writes the site `<name>` as a pack zip, `<name>.zip` in the current directory
by default. The site can be an inline `[sites.<name>]` table, which is written
out as the pack's `site.toml`, or a pack already.

```bash
dotbot site export lab                                    # lab.zip
dotbot site export lab --out ~/share/lab.zip --with-calibrations
```

| Flag | Meaning |
|---|---|
| `--out FILE` | The zip to write (default `<name>.zip`). |
| `--with-calibrations` | Include the site's calibration files, from its pack's `calibrations/` and from `~/.dotbot/calibrations/<name>/`. |
| `-f`, `--force` | Overwrite an existing zip. |

A pack is plain files, so `unzip`, `git clone` or `cp` into a `site_dirs`
folder work just as well as `site add`.

## See also

- [Configuration reference: sites](../reference/configuration.md#sites) - the site table, area roles, `site_dirs`.
- [`dotbot config`](config.md) - `config show` names where the site, conn and swarm id came from.
- [LH2 calibration](../guides/lh2-calibration.md) - calibrating a site.
