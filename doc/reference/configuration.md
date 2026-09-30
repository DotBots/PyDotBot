# Configuration

`dotbot` reads one optional config file so you don't retype the same flags on
every command. A value can come from a flag, an environment variable, the file,
or a built-in default - the resolver merges them through a single precedence
chain, so the file is just a place to park the defaults you'd otherwise pass by
hand.

You never need a config file: every setting also has a flag and an env var. The
file just makes a repeated setup (a broker URL, a board name, a swarm id) the
default.

Create one with `dotbot config init` (it writes a `./dotbot.toml` holding a
starter [site](#sites)); pass `--conn` / `--swarm-id` to pre-fill the two most
common keys (a broker becomes the site's [connection](#a-sites-connection), the
swarm id a key of your own):

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
| 4 | `~/.dotbot/dotbot.toml` | Your user-level file. |
| 5 | (none) | Built-in defaults only. |

A `dotbot.toml` in your working directory (3) takes precedence over your
personal file (4), so a per-experiment config wins while you work in that
directory. Discovery looks only at the cwd - it does not walk up to parent
directories, so the active config is always unambiguous.

`~/.dotbot/dotbot.toml` (4) is the per-machine fallback for settings you set
once and want everywhere - typically `[fw].segger_dir`, since the SEGGER
Embedded Studio install path rarely changes. Per-project settings like `[fw.sources]` belong in
the project's `./dotbot.toml` instead. Every command, including `dotbot fw`,
reads through this same resolver.

The user-level file is named `dotbot.toml`, like a project's. A file still under
its former name, `~/.dotbot/config.toml`, is refused with one line: rename it to
`~/.dotbot/dotbot.toml`.

## Precedence

For any single setting, the highest-priority source that has a value wins:

```text
CLI flag  >  env DOTBOT_<SECTION>_<KEY> (then shared DOTBOT_<KEY>)
          >  your file: section value > top-level
          >  the active site's [connection]   (conn and swarm_id only)
          >  built-in default
```

Inside your file, a key set in its own section table beats a shared top-level
key. The active site's `[connection]` sits below your whole file, even when it
is an inline `[sites.<name>.connection]` table in that file: it is the site's
value, and anything you set yourself overrides it. `dotbot config show` prints
where each value came from and what it hides.

**Worked example** - resolving the controller's broker URL (`conn`):

| Source | Value | Wins? |
|---|---|---|
| `--conn mqtts://cli:8883` flag | `mqtts://cli:8883` | yes, flag is highest |
| `DOTBOT_RUN_CONN` env | `mqtts://env:8883` | only if no flag |
| `[run] conn` in the file | `mqtts://run:8883` | only if no flag/env |
| top-level `conn` | `mqtts://shared:8883` | only if `[run]` has no `conn` |
| the active site's `[connection] conn` | `mqtts://site:8883` | only if nothing above is set |
| built-in default | - | last resort |

Env-var names are mechanical: a section key becomes `DOTBOT_<SECTION>_<KEY>`
(e.g. `DOTBOT_FW_BOARD`, `DOTBOT_RUN_CONN`), and a shared top-level key becomes
`DOTBOT_<KEY>` (e.g. `DOTBOT_CONN`, `DOTBOT_SWARM_ID`). A sectioned key also
accepts the shared `DOTBOT_<KEY>` form as a fallback.

## Top-level (shared) keys

Set once at the top of the file; any section can override them.

| Key | Meaning |
|---|---|
| `conn` | Default connection string (`mqtts://host:port`, a serial path, or `simulator`). Overrides the active site's [connection](#a-sites-connection). |
| `swarm_id` | Swarm id selecting the MQTT topic namespace. |
| `log_level` | Logging verbosity. |
| `site` | The active [site](#sites): its frame, its areas and the folder its calibrations are kept under. `--site` or `DOTBOT_SITE` overrides it. |
| `site_dirs` | Folders searched, in order, for [site packs](#site-packs) (default `["sites", "~/.dotbot/sites"]`). |

## Section tables

The four tables mirror the four CLI namespaces (`fw` / `device` / `swarm` /
`run`); a section key is the per-namespace default for the matching flag.

`[fw]` - firmware-artifact builds (`dotbot fw`):

| Key | Meaning |
|---|---|
| `board` | Target board, e.g. `dotbot-v3`. |
| `bare` | Default to bare-metal apps (`.hex`) instead of sandboxed apps (`.bin`) on boards that have a sandbox; `--bare` / `--sandboxed` override it per run. |
| `build_config` | `Debug` or `Release`. |
| `segger_dir` | SEGGER Embedded Studio install path. |

`[fw.sources]` - the source folder `dotbot fw build` reads, one key per source
repo:

| Key | Meaning |
|---|---|
| `dotbot-firmware` | Your `DotBot-firmware` folder, for apps (env `DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE`). Default: `repos/DotBot-firmware` next to this file. |
| `swarmit` | Your `swarmit` folder, for `swarmit-sandbox` (env `DOTBOT_FW_SOURCES_SWARMIT`). Default: `repos/swarmit` next to this file. |
| `mari` | Your `mari` folder, for `mari-gateway` (env `DOTBOT_FW_SOURCES_MARI`). Default: `repos/mari` next to this file. |

```toml
[fw.sources]
dotbot-firmware = "../DotBot-firmware"
swarmit = "../swarmit"
```

A relative path resolves against the config file that sets it;
`dotbot fw build <role|app> --path <folder>` overrides it for one run.

`[device]` - one cabled device (`dotbot device`):

| Key | Meaning |
|---|---|
| `board` | Target board for flashing. |
| `probe` | J-Link serial-number prefix selecting which probe (the `--probe` flag). |
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
| `[run.controller] http_host` | Interface the REST/WebSocket API binds to (default `127.0.0.1`). `0.0.0.0` exposes it to the network; the API is unauthenticated. |
| `[run.controller] background_map` | Background map image. |
| `[run.controller] lh2_calibration` | Lighthouse calibration to run on: a file path, the exact `--tag` it was collected with, or an id prefix of one of the site's calibrations (see [where calibrations are found](#where-calibrations-are-found)). |
| `[run.controller] lh2_calibration_max_age_days` | Warn at load when the LH2 calibration is older than this many days (default 30, `0` never warns). Also `DOTBOT_RUN_CONTROLLER_LH2_CALIBRATION_MAX_AGE_DAYS`. |
| `[run.controller] camera_calibration` | Overhead camera registration to draw on the map, same form. Written by `dotbot run calibrate-camera collect`. |
| `[run.controller] camera_detect` | Run the robot detector on a registered camera (default true). False serves the layer as a picture only, and writes no `-camera.csv`. |
| `[run.controller] log_output` | Log output path. |
| `[run.controller] csv_data_output` | CSV data output path. A registered camera writes a second file, `<name>-camera.csv`, beside it, with a `<name>-camera.toml` sidecar pinning the geometry and the frames its columns are in. |
| `[run.controller] headless` | Stay headless - don't open the web UI in a browser on start (default false; it's still served). |
| `[run.controller] gw_address` | Gateway address. |
| `[run.controller] simulator_init_state` | Initial simulator state. |
| `[run.controller] simulator_area` | Where a simulator places its robots (`--area`): an area name, a `+`-joined composite or `x,y,w,h` in mm. Defaults to the site's field. |
| `[run.controller] swarmit_url` | swarmit server the console's orchestration panel talks to, proxied at `/swarmit/*` (default `http://localhost:8001`, which matches `swarmit serve`). |
| `[run.controller] mrta_url` | MRTA mode server (dotbot-logistics) the console's MRTA toggle talks to, proxied at `/mrta/*`. Unset by default (no default URL) - the console shows no MRTA control until this is set (typically `http://localhost:8002`, dotbot-logistics' own default port). |
| `[run.gateway] serial_port` | Gateway serial port. |
| `[run.gateway] mqtt` | Gateway MQTT connection string. |

Unknown keys are rejected: a typo in a section or key name fails loud rather
than being silently ignored.

## Sites

A **site** is the place you work in and its usual way in. Its `[sites.<name>]`
table says where zero is, how big the floor is, which named rectangles,
**areas**, it holds, and optionally which broker the site is reached through.
Positions, calibrations and the console map are all in the active site's
frame: millimetres, zero at the top-left corner of the extent, x to the right,
y down.

```toml
site = "lab"

[sites.lab]
anchor    = "corner of the tiles by the door; x along the window wall"
extent_mm = [5000, 5000]

[sites.lab.areas]
field      = { x = 1500, y = 1500, w = 2000, h = 2000 }
staging    = { x = 1500, y = 3500, w = 2000, h = 600 }
dev-corner = { x = 4000, y = 300,  w = 700,  h = 700, role = "corner" }
```

| Key | Meaning |
|---|---|
| `anchor` | Prose saying where zero is on the real floor. No code reads it, but a calibration records it, and one made against another anchor is refused. |
| `extent_mm` | `[width, height]` of the floor. |
| `areas.<name>` | A rectangle `{ x, y, w, h }` in mm, with an optional `role`. |
| `connection` | The site's usual broker and, optionally, swarm id; see [below](#a-sites-connection). |
| `virtual` | `true` for a site that exists only in simulation. |

The active site is, in order: `--site`, `DOTBOT_SITE`, the top-level `site`,
then `default`. `dotbot site use NAME` writes the top-level `site` for you.
`dotbot config init` writes a `default` site; see [`dotbot config`](../cli/config.md).

### A site's connection

A site may name the broker it is usually reached through, so working in it
needs no `conn` of your own:

```toml
[sites.lab.connection]           # in a pack's site.toml: [connection]
conn     = "mqtts://broker.lab.example:8883"
swarm_id = "0A1B"                # only if whoever publishes the site owns the network
```

| Key | Meaning |
|---|---|
| `conn` | A broker URL, `mqtt://` or `mqtts://`. A serial path names a port on one machine and is refused; pass it with `--conn` or set it in your own file. A URL with `user:pass@` is refused too. |
| `swarm_id` | The swarm id, when the site has one network that everyone working there shares. Leave it out when several people flash gateways at their own ids; each then sets their own `swarm_id`. |

A site has one network: all of its gateways share one net id, even at a
thousand robots. A second network in the same room is `--conn` / `--swarm-id`
or a `conn` in a project `dotbot.toml`, never a copy of the site, since the
site's name keys its calibrations and is stored on the robots.

Your own `conn` and `swarm_id` beat the site's (see [precedence](#precedence)),
so a leftover top-level `conn` hides every site's. The one-line banner that
`run controller`, `run gateway` and the swarm commands that act on robots print
before connecting names each value's source, and `dotbot site use` warns when
your file or environment overrides the site it switches to.

An MQTT `conn` with no swarm id anywhere fails with `site lab names no swarm;
set --swarm-id or DOTBOT_SWARM_ID`.

A **virtual** site exists only in simulation. It may take `conn = "simulator"`,
and that is the only `conn` it takes; no other site does:

```toml
[sites.virtual-lab]
virtual   = true
extent_mm = [20000, 30000]

[sites.virtual-lab.connection]
conn = "simulator"
```

On a virtual site `dotbot run controller` and `dotbot run simulator` do the same
thing. `dotbot run simulator` is `run controller --conn simulator` on whatever
site is active, so a real site can be rehearsed in simulation too.

### Area roles

An area can have one of three roles:

| Role | Meaning |
|---|---|
| `field` | Where experiments happen and what a calibration covers. The simulator fleet, `swarm calibrate-lh2 collect`, the camera `collect --area` and the console's calibration setup all default to it. |
| `staging` | Where robots park and charge. The charging example needs one. |
| `corner` | A small patch, such as a bench, that may overlap other areas. The console starts it hidden. |

An area named `field`, `staging` or `corner` has that role; `role = "..."`
gives one to any other name, and beats the one the name implies. An area with
neither has no role.

A site has **at most one field**; two is a config error naming both. When no
area has the `field` role, the field is the first area that is neither staging
nor corner, else the first area, else the whole extent. Areas keep the order
they are declared in.

### Site packs

A site can also live in its own folder, a **site pack**, to commit, zip or hand
to someone:

```text
lab/
├── site.toml          # the keys of [sites.lab]: anchor, extent_mm, areas
└── calibrations/      # optional: the site's LH2 and camera calibration files
```

The folder's name is the site's name. Packs are found in the `site_dirs`
folders, searched in order, and the first folder holding a pack of a name wins.
The default is `["sites", "~/.dotbot/sites"]`: a `sites/` folder next to the
config file, then the folder `dotbot site add` copies packs into. A relative
entry is read from the config file's folder.

```toml
site      = "lab"
site_dirs = ["sites"]
```

An inline `[sites.<name>]` table wins over a pack of the same name, with a
one-line notice naming the pack it hides. `dotbot site list` lists every site,
its connection and where it was read from. To install or share a pack, see
[`dotbot site`](../cli/site.md).

### Where calibrations are found

A calibration is always the one you name: a file path, the exact `--tag` it was
collected with, or a prefix of its id, never "the latest". A tag or an id is
looked up in the site's pack `calibrations/` folder first, then in
`~/.dotbot/calibrations/<site>/`, where `collect` writes; the first folder with
a match wins.

At load, the controller refuses an LH2 or camera calibration made in another
site, and one whose recorded anchor differs from the site's when both record
one. Select the calibration's site with `--site`, or pick a calibration of the
active site.

### How calibration points were chosen

Each placement in an LH2 calibration file records how its four points were
chosen, as a `points_from` table:

| `points_from` | Meaning |
|---|---|
| `{ kind = "field" }` | The field's corners (`collect` with no flag). |
| `{ kind = "over", area = "dev-corner" }` | Another area's corners (`--over`). |
| `{ kind = "square", side_mm = 800 }` | A square centred in the field (`--square`). |
| `{ kind = "points" }` | Points given by hand (`--points`). |

The console shows it in the calibrated span's tooltip. It is not part of the
calibration's id.

## MQTT credentials are env-only

MQTT username and password are read **only** from the environment, and tied to
the broker they are for:

```bash
export DOTBOT_MQTT_USER=alice
export DOTBOT_MQTT_PASS=…
export DOTBOT_MQTT_HOST=broker.lab.example
```

They are never file keys - don't put them in `dotbot.toml`, and don't commit
them. Keep the broker URL in the file and the credentials in your environment
(or a secret manager).

A shared site pack must not quietly choose where your login goes, so the
credentials go to a broker only when:

- `DOTBOT_MQTT_HOST` names it, or
- you named the broker yourself: a flag, an env var, or your own file, or
- it runs on this machine (`localhost`).

They never go over plain `mqtt://` to another host. When they are withheld, a
one-line warning says so and names the `DOTBOT_MQTT_HOST=<host>` that would
allow it; `dotbot config show` says where they would go.

## Inspecting the resolved config

Two helpers show what `dotbot` actually resolved, so you don't have to trace the
precedence chain by hand:

| Command | Shows |
|---|---|
| `dotbot config show` | The file in use, where the site, `conn` and `swarm_id` each came from and what they hide, where the credentials go, and the file's own keys. `--json` for scripts. |
| `dotbot site list` | Every site the config can name, its connection, and which one is active. |

## Full example

An annotated `dotbot.toml` exercising every layer:

```toml
# Top-level shared keys: every section inherits these unless it sets its own
# value, and they beat the active site's [connection].
swarm_id        = "0001"
log_level       = "info"
site            = "lab"                      # the active site; --site / DOTBOT_SITE override
site_dirs       = ["sites"]                  # site packs next to this file, e.g. sites/hall/site.toml

# A site: where zero is, the floor's size, its broker and its areas.
[sites.lab]
anchor    = "corner of the tiles by the door; x along the window wall"
extent_mm = [5000, 5000]

[sites.lab.connection]
conn = "mqtts://broker.local:8883"   # used unless you set conn yourself

[sites.lab.areas]
field      = { x = 1500, y = 1500, w = 2000, h = 2000 }  # named after its role
staging    = { x = 1500, y = 3500, w = 2000, h = 600 }
dev-corner = { x = 4000, y = 300,  w = 700,  h = 700, role = "corner" }

# Firmware-artifact builds (dotbot fw).
[fw]
board        = "dotbot-v3"
bare         = false
build_config = "Release"
# segger_dir = "/Applications/SEGGER/SEGGER Embedded Studio 8.22a"

# One cabled device (dotbot device).
[device]
board        = "dotbot-v3"
probe        = "77"                        # J-Link serial prefix
build_config = "Release"

# The fleet over the air (dotbot swarm).
[swarm]
swarm_id = "0001"

# Host-side processes (dotbot run).
[run.controller]
http_port      = 8000
lh2_calibration_max_age_days = 30   # warn when the loaded LH2 calibration is older
headless       = true    # default is false; set true to suppress the browser (still served)
# background_map = "./map.png"

[run.gateway]
serial_port = "/dev/ttyACM0"

# Note: MQTT credentials are env-only - DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS,
# tied to a broker by DOTBOT_MQTT_HOST. Never a file key.
```
