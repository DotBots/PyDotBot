# `dotbot site` - add and export site packs

A **site pack** is a site in its own folder, so it can be committed, zipped or
handed to someone: `<name>/site.toml` holds the keys of a `[sites.<name>]`
table, and an optional `<name>/calibrations/` holds the site's LH2 and camera
calibration files. `site add` installs one on this machine and `site export`
writes one. How packs are found, and how they relate to inline `[sites.*]`
tables, is in the [configuration reference](../reference/configuration.md#site-packs).

## Which command do I want?

| Goal | Command |
|---|---|
| Use a site someone shared with you | `dotbot site add <folder, zip, git URL or ->` |
| Share a site, or move an inline table into a pack | `dotbot site export <name>` |
| See every site and where it was read from | `dotbot config show` |

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

Then select the site with `site = "lab"` in your config, `--site lab` or
`DOTBOT_SITE=lab`.

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
- [`dotbot config`](config.md) - `config show` lists every site and its source.
- [LH2 calibration](../guides/lh2-calibration.md) - calibrating a site.
