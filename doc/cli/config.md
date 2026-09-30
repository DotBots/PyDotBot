# `dotbot config` - inspect and scaffold the config

`dotbot` reads a `dotbot.toml` so commands don't repeat shared settings - your
gateway connection, swarm id, firmware paths, the site you work on. `config` scaffolds that file and
shows you what the CLI actually resolved. For the full file format - every key,
deployments, the precedence rules - see the
[configuration reference](../reference/configuration.md).

## Which command do I want?

| Goal | Command |
|---|---|
| Write a starter `dotbot.toml` you can edit | `dotbot config init` |
| See the merged, effective config + which file it came from | `dotbot config show` |
| Print just the resolved config-file path | `dotbot config path` |

## `init`

Writes a starter `./dotbot.toml` holding a site, so the simulator, calibration
and the examples have a floor to work on from the first run:

```toml
site = "default"

# Zero is the top-left corner of the extent, x right, y down, millimetres.
[sites.default]
anchor = "top-left corner of a 5 x 5 m floor; the field starts 1.5 m in from each wall"
extent_mm = [5000, 5000]

[sites.default.areas]
field   = { x = 1500, y = 1500, w = 2000, h = 2000 }
staging = { x = 1500, y = 3500, w = 2000, h = 600 }
```

The **field** is where experiments happen and what a calibration covers; the
**staging** strip along its bottom edge is where robots park. Once you have
measured a real room, edit the file: the site is plain TOML, and the
[configuration reference](../reference/configuration.md#sites) has every key.

```bash
dotbot config init                                             # ./dotbot.toml with a 2 x 2 m field
dotbot config init --field 1.5m --site lab                     # a 1.5 x 1.5 m field in a site named lab
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234  # pre-fill the two common keys
dotbot config init --global                                    # ~/.dotbot/config.toml
```

| Flag | Meaning |
|---|---|
| `--field` | The field's size (default `2m`): one value for a square, `WxH` for a rectangle. A bare number is mm, and `1500mm`, `1.5m` and `2x3m` also work; decimals only with `m`. From 100 mm to 100 m. The extent and the staging strip follow from it. Above 5 m on a side it warns that one LH2 station rarely covers that well. |
| `--site` | The site's name (default `default`); its calibrations are kept under `~/.dotbot/calibrations/<site>/`. |
| `--conn` / `--swarm-id` | Pre-fill the shared connection and swarm id. |
| `--global` | Write the per-machine `~/.dotbot/config.toml` instead of `./dotbot.toml`. |
| `-f`, `--force` | Overwrite an existing file, whole. |

`dotbot.example.toml` in the repository is exactly what `dotbot config init`
writes with no flags.

> MQTT credentials are never file keys - set `DOTBOT_MQTT_USER` /
> `DOTBOT_MQTT_PASS` in the environment.

## `show` / `path`

`show` prints the source file, the selected deployment, the active site, every
site with its areas' roles and where it was read from (inline, or a site pack's
folder), and the resolved config as TOML - only the keys actually set, not the
full schema. `path` prints just
the file path (or notes that built-in defaults are in use). Both are read-only;
there is no per-key `set` - edit the file, it's yours.

```bash
dotbot config show
dotbot config path
```

## Where the config comes from

`dotbot` uses the first of: a `-c/--config FILE` flag (or `DOTBOT_CONFIG`), a
`dotbot.toml` in the current directory, then `~/.dotbot/config.toml`. A flag or a
`DOTBOT_*` env var overrides the file for a single run. The full precedence chain
is in the [configuration reference](../reference/configuration.md#precedence).

## See also

- [Configuration reference](../reference/configuration.md) - the file format, every key, deployments, precedence.
- [`dotbot site`](site.md) - install a site pack, or export a site to share.
- [`dotbot fw`](fw.md) - reads its `[fw]` keys (`segger_dir`, `[fw.sources]`) from this same config.
