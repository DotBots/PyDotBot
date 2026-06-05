# Configuration

`dotbot` reads one optional config file so you don't retype the same flags on
every command. A value can come from a flag, an environment variable, the file,
or a built-in default - the resolver merges them through a single precedence
chain, so the file is just a place to park the defaults you'd otherwise pass by
hand.

You never need a config file: every setting also has a flag and an env var. The
file just makes a repeated setup (a broker URL, a board name, a swarm id) the
default.

Create one with `dotbot config init` (it writes a minimal `./dotbot.toml`);
pass `--conn` / `--swarm-id` to pre-fill the two most common keys:

```bash
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234
```

This page is the file-format reference. For the `config` command itself
(`init` / `show` / `path`), see [`dotbot config`](../cli/config.md).

## Where the file comes from

`dotbot` looks in this order and uses the first hit:

| Order | Source | How |
|---|---|---|
| 1 | `-c PATH` / `--config PATH` | An explicit path on the command line. |
| 2 | `DOTBOT_CONFIG` | An explicit path in the environment. |
| 3 | `./dotbot.toml` | A `dotbot.toml` in the current directory (the cwd only - parent directories are not searched). |
| 4 | `~/.dotbot/config.toml` | Your user-level file. |
| 5 | (none) | Built-in defaults only. |

A `dotbot.toml` in your working directory (3) takes precedence over your
personal file (4), so a per-experiment config wins while you work in that
directory. Discovery looks only at the cwd - it does not walk up to parent
directories, so the active config is always unambiguous.

`~/.dotbot/config.toml` (4) is the per-machine fallback for settings you set
once and want everywhere - typically `[fw].segger_dir`, since the SEGGER
Embedded Studio install path rarely changes. Per-project settings like `[fw].firmware_repo` belong in
the project's `./dotbot.toml` instead. Every command, including `dotbot fw`,
reads through this same resolver.

## Precedence

For any single setting, the highest-priority source that has a value wins:

```text
CLI flag  >  env DOTBOT_<SECTION>_<KEY> (then shared DOTBOT_<KEY>)
          >  file: section value > selected deployment > top-level
          >  built-in default
```

Inside the file, a key set in its own section table beats the same key on the
selected deployment, which beats a shared top-level key.

**Worked example** - resolving the controller's broker URL (`conn`):

| Source | Value | Wins? |
|---|---|---|
| `--conn mqtts://cli:8883` flag | `mqtts://cli:8883` | yes, flag is highest |
| `DOTBOT_RUN_CONN` env | `mqtts://env:8883` | only if no flag |
| `[run] conn` in the file | `mqtts://run:8883` | only if no flag/env |
| `[deployment.inria] conn` (selected) | `mqtts://inria:8883` | only if `[run]` has no `conn` |
| top-level `conn` | `mqtts://shared:8883` | only if nothing above is set |
| built-in default | - | last resort |

Env-var names are mechanical: a section key becomes `DOTBOT_<SECTION>_<KEY>`
(e.g. `DOTBOT_FW_BOARD`, `DOTBOT_RUN_CONN`), and a shared top-level key becomes
`DOTBOT_<KEY>` (e.g. `DOTBOT_CONN`, `DOTBOT_SWARM_ID`). A sectioned key also
accepts the shared `DOTBOT_<KEY>` form as a fallback.

## Top-level (shared) keys

Set once at the top of the file; any section or deployment can override them.

| Key | Meaning |
|---|---|
| `conn` | Default connection string (`mqtts://host:port`, a serial path, or `simulator`). |
| `swarm_id` | Swarm id selecting the MQTT topic namespace. |
| `log_level` | Logging verbosity. |
| `default_deployment` | Name of the deployment to select when neither `--deployment` nor `DOTBOT_DEPLOYMENT` is given. |

## Section tables

The four tables mirror the four CLI namespaces (`fw` / `device` / `swarm` /
`run`); a section key is the per-namespace default for the matching flag.

`[fw]` - firmware-artifact builds (`dotbot fw`):

| Key | Meaning |
|---|---|
| `board` | Target board, e.g. `dotbot-v3`. |
| `sandbox` | Build TrustZone sandbox apps (`.bin`) instead of bare apps. |
| `build_config` | `Debug` or `Release`. |
| `segger_dir` | SEGGER Embedded Studio install path. |
| `firmware_repo` | Path to your `DotBot-firmware` clone (so `fw build`/`artifacts` find it without `cd` or `DOTBOT_FIRMWARE_REPO`). |

`[device]` - one cabled device (`dotbot device`):

| Key | Meaning |
|---|---|
| `board` | Target board for flashing. |
| `sn_starting_digits` | J-Link serial-number prefix selecting which probe. |
| `build_config` | `Debug` or `Release`. |

`[swarm]` - the fleet over the air (`dotbot swarm`):

| Key | Meaning |
|---|---|
| `conn` | Connection string for the fleet link. |
| `swarm_id` | Swarm id (topic namespace). |
| `devices` | Device selection for fleet operations. |

`[run]` plus `[run.controller]` and `[run.gateway]` - host processes
(`dotbot run`):

| Key | Meaning |
|---|---|
| `conn` | Connection string for `dotbot run`. |
| `swarm_id` | Swarm id (topic namespace). |
| `[run.controller] http_port` | REST/WebSocket port (default 8000). |
| `[run.controller] map_size` | Controller map size. |
| `[run.controller] background_map` | Background map image. |
| `[run.controller] log_output` | Log output path. |
| `[run.controller] csv_data_output` | CSV data output path. |
| `[run.controller] webbrowser` | Open the web UI on start (default true; set false to stay headless). |
| `[run.controller] gw_address` | Gateway address. |
| `[run.controller] simulator_init_state` | Initial simulator state. |
| `[run.gateway] serial_port` | Gateway serial port. |
| `[run.gateway] mqtt` | Gateway MQTT connection string. |

Unknown keys are rejected: a typo in a section or key name fails loud rather
than being silently ignored.

## What a deployment is

A **deployment** here means one physical deployment - one set of real DotBots
behind one broker, in one place (e.g. the ~100-DotBot setup at Inria Paris, or a
1000-DotBot campaign). You define each one as a `[deployment.<name>]` table and
**select** it; you do not edit the file to switch between them.

Select the active deployment with, in precedence order, `--deployment NAME`, the
`DOTBOT_DEPLOYMENT` env var, or the top-level `default_deployment`. The selected
deployment's keys slot into the file layer (above top-level, below sections), so an
explicit flag or env var still overrides it. Selecting a name with no matching
`[deployment.<name>]` table is an error that lists the defined deployments.

A deployment is **not** the simulator. To drive simulated DotBots, set the connection
to `simulator` (`--conn simulator`, or `conn = "simulator"`); that is a
connection kind, not a deployment.

A `[deployment.<name>]` table holds the deployment-binding keys plus descriptive
metadata:

| Key | Meaning |
|---|---|
| `conn` | Broker / link for this deployment. |
| `swarm_id` | Swarm id for this deployment. |
| `serial_port` | Default serial port for this deployment. |
| `location` | Descriptive label (shown by `dotbot deployment list`). |
| `bots` | Descriptive DotBot count. |

## Managing deployments

The `dotbot deployment` group inspects, switches, and fetches deployments:

| Command | Does |
|---|---|
| `dotbot deployment list` | List defined deployments; mark the active one. |
| `dotbot deployment show NAME` | Print one deployment's fields. |
| `dotbot deployment use NAME` | Set NAME as `default_deployment`, written into your config file (comments preserved). |
| `dotbot deployment fetch [SOURCE]` | Fetch published deployments and merge them into your config. |

`fetch` takes a URL or a local file holding `[deployment.*]` tables; with no
SOURCE it uses the built-in DotBots registry. It **merges**: a same-named
deployment is replaced (you are asked first), and everything else in the file
(other deployments, sections, comments) is left intact. Like `dotbot fw fetch`,
it only acquires the deployment - select it afterwards with `dotbot deployment
use` or `--deployment`. Useful flags: `--into project` (write the nearest
`dotbot.toml` instead of `~/.dotbot/config.toml`), `--dry-run`, and `--yes`.

Because MQTT credentials are env-only (below), a published deployment file is not
secret - it carries only the broker URL, swarm id, and descriptive labels.

## MQTT credentials are env-only

MQTT username and password are read **only** from the environment:

```bash
export DOTBOT_MQTT_USER=alice
export DOTBOT_MQTT_PASS=…
```

They are never file keys - don't put them in `dotbot.toml`, and don't commit
them. Keep the broker URL in the file and the credentials in your environment
(or a secret manager).

## Inspecting the resolved config

Two helpers show what `dotbot` actually resolved, so you don't have to trace the
precedence chain by hand:

| Command | Shows |
|---|---|
| `dotbot config show` | The merged, effective config and which file (if any) it came from. |
| `dotbot deployment list` | The defined deployments, their metadata, and which one is selected. |

## Full example

An annotated `dotbot.toml` exercising every layer:

```toml
# Top-level shared keys: every section and deployment inherits these unless it
# sets its own value.
default_deployment = "inria"                 # used when --deployment / DOTBOT_DEPLOYMENT unset
conn            = "mqtts://broker.local:8883"
swarm_id        = "0001"
log_level       = "info"

# A physical deployment. Select it with `--deployment inria`, DOTBOT_DEPLOYMENT, or
# default_deployment above - don't edit this table to switch deployments.
[deployment.inria]
conn        = "mqtts://broker.inria.fr:8883"
swarm_id    = "0001"
serial_port = "/dev/ttyACM0"
location    = "Inria Paris"               # descriptive, for `dotbot deployment list`
bots        = 100                          # descriptive

[deployment.limerick]
conn     = "mqtts://broker.limerick:8883"
swarm_id = "0002"
location = "Limerick campaign"
bots     = 725

# Firmware-artifact builds (dotbot fw).
[fw]
board        = "dotbot-v3"
sandbox      = false
build_config = "Release"
# segger_dir = "/Applications/SEGGER/SEGGER Embedded Studio 8.22a"

# One cabled device (dotbot device).
[device]
board              = "dotbot-v3"
sn_starting_digits = "77"                  # J-Link serial prefix
build_config       = "Release"

# The fleet over the air (dotbot swarm).
[swarm]
swarm_id = "0001"

# Host-side processes (dotbot run).
[run]
conn = "mqtts://broker.local:8883"

[run.controller]
http_port      = 8000
webbrowser     = false   # default is true; set false to stay headless
# background_map = "./map.png"

[run.gateway]
serial_port = "/dev/ttyACM0"

# Note: MQTT credentials are env-only - DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS.
# Never a file key.
```
