# `dotbot config` - inspect and scaffold the config

`dotbot` reads a `dotbot.toml` so commands don't repeat shared settings - your
gateway connection, swarm id, firmware paths. `config` scaffolds that file and
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

Writes a minimal `./dotbot.toml` - a one-line pointer to the docs, plus any keys
you pre-fill. `--global` writes your per-machine `~/.dotbot/config.toml` instead;
`-f/--force` overwrites an existing file.

```bash
dotbot config init                                             # commented starter in ./dotbot.toml
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234  # pre-fill the two common keys
dotbot config init --global                                    # ~/.dotbot/config.toml
```

> MQTT credentials are never file keys - set `DOTBOT_MQTT_USER` /
> `DOTBOT_MQTT_PASS` in the environment.

## `show` / `path`

`show` prints the source file, the selected deployment, and the resolved config
as TOML - only the keys actually set, not the full schema. `path` prints just
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
- [`dotbot fw`](fw.md) - reads its `[fw]` keys (`segger_dir`, `firmware_repo`) from this same config.
