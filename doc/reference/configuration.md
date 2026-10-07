# Configuration

`dotbot` reads up to three optional TOML files so you don't retype the same
flags on every command. You never need one: every setting also has a flag and
an environment variable. The files hold the defaults you would otherwise pass
by hand, and the CLI writes them for you (`dotbot config set`, `dotbot site
use`, `dotbot config login`), so you rarely edit one yourself.

This page is the file-format reference. For the commands, see
[`dotbot config`](../cli/config.md) and [`dotbot site`](../cli/site.md).

## The three files

| File | Who it is about | Tracked by git? | Holds, typically |
|---|---|---|---|
| `~/.dotbot/dotbot.toml` | you, on this machine | never | `[fw] segger_dir`, `[device] probe`, your swarm id, the site you work in outside a project, `[login]` |
| `./dotbot.toml` | a project, for everyone who clones it | yes | the team's default site, `[fw.sources]` |
| `./dotbot.local.toml` | you, in this project | no | your swarm id, a local broker, a firmware worktree, a calibration |

A new user after `pip install pydotbot` only ever meets the first. The other
two exist only inside a project folder.

`./dotbot.toml` is read from the current directory only; parent directories
are not searched. `-c FILE` (or `DOTBOT_CONFIG`) names another file to use in
its place, and then its overlay is `<stem>.local.toml` beside it:
`-c lab.toml` reads `lab.local.toml`. The user file applies in every case.

A user file still under its former name, `~/.dotbot/config.toml`, is refused
with one line: rename it to `~/.dotbot/dotbot.toml`.

## Closest to you wins

Every layer is merged key by key by one rule. For each setting, the first
layer below that sets it wins:

| Layer | Lasts for |
|---|---|
| a flag (`--conn`, `--swarm-id`, `--site`, ...) | one command |
| an env var (`DOTBOT_<SECTION>_<KEY>`, then `DOTBOT_<KEY>`) | one shell, or a CI job |
| `./dotbot.local.toml` | you, in this project |
| `./dotbot.toml` | everyone in this project |
| `~/.dotbot/dotbot.toml` | you, everywhere on this machine |
| the active site's `[connection]` (`conn` and `swarm_id` only) | everyone working in that site |
| the built-in default | - |

Tables merge key by key: a `[fw.sources] dotbot-firmware` in your overlay
replaces only that key of the project's `[fw.sources]`. A relative path in a
file is read from that file's folder; one in an env var or a flag, from the
current directory.

An env var is a one-off override and is never read from a file. Its name is
mechanical: a key in a table becomes `DOTBOT_<SECTION>_<KEY>`
(`DOTBOT_FW_BOARD`, `DOTBOT_RUN_CONTROLLER_LH2_CALIBRATION`), with the shared
`DOTBOT_<KEY>` as a fallback (`DOTBOT_BOARD`), and a top-level key is
`DOTBOT_<KEY>` (`DOTBOT_CONN`, `DOTBOT_SWARM_ID`, `DOTBOT_SITE`). A `DOTBOT_*`
variable that nothing reads, such as `DOTBOT_SWARMID`, is named in a warning,
with the close name when there is one.

**Worked example**: which `conn` wins in a project.

| Layer | Value | Wins when |
|---|---|---|
| `--conn simulator` | `simulator` | always |
| `DOTBOT_CONN=/dev/ttyACM0` | a serial gateway | no flag |
| `dotbot.local.toml` | `mqtt://localhost:1883` | no flag or env |
| `dotbot.toml` | unset, by convention | - |
| `~/.dotbot/dotbot.toml` | unset | - |
| site `c405-arena` `[connection]` | `mqtts://argus.paris.inria.fr:8883` | nothing above is set |

`dotbot config show` prints each value with the layer it came from and the
lower layers it hides, so nothing here has to be traced by hand.

## Who writes what

The CLI only writes files git does not track, unless you ask for the project
file:

| Command | Writes |
|---|---|
| `dotbot config set KEY VALUE`, `config unset KEY` | a machine key (below) to `~/.dotbot/dotbot.toml` wherever you are; any other key to `./dotbot.local.toml` in a project, else to `~/.dotbot/dotbot.toml` |
| `dotbot site use NAME` | `site` in the same file as `config set` |
| `dotbot config login HOST` | `[login."HOST"]` in `~/.dotbot/dotbot.toml`, made readable by you alone |
| `dotbot config init` | `site` (and `--swarm-id`, a serial `--conn`) in `~/.dotbot/dotbot.toml` |
| `dotbot config init --project` | `./dotbot.toml`, and `dotbot.local.toml` in `.gitignore` |

The machine keys are `fw.segger_dir`, `fw.artifacts_dir`, `fw.board`,
`device.board`, `device.probe`, and the `run.controller` keys `headless`,
`http_port`, `http_host`, `camera_max_robots`, `camera_detect_share`,
`swarmit_url`, `swarm_serve` and `mrta_url`. `--user` and `--project` pick the file
yourself; `--project` writes the committed file, and says so.

Writes keep the file's comments, and a write that would make the file invalid
is refused before anything is written.

## Examples

A new user after `pip install pydotbot`, who added their lab's site with
`dotbot site add - --use`, set a swarm id and saved a login:

```toml
# ~/.dotbot/dotbot.toml
site     = "lab"
swarm_id = "0042"

[fw]
segger_dir = "/usr/share/segger_embedded_studio_for_arm_7.22"

[device]
probe = "77"

[login."broker.lab.example"]
user     = "me"
password = "s3cret"
```

A project, as the team commits it, and one developer's overlay on it:

```toml
# ./dotbot.toml (committed)
site = "c405-arena"          # a pack in sites/ beside this file

[fw.sources]
dotbot-firmware = "repos/DotBot-firmware"
swarmit         = "repos/swarmit"
mari            = "repos/mari"

[run.controller]
lh2_calibration_max_age_days = 14
```

```toml
# ./dotbot.local.toml (untracked)
site     = "inria-aio-c"
swarm_id = "A001"
# conn = "mqtt://localhost:1883"

[fw.sources]
dotbot-firmware = "repos/wt-DotBot-firmware-lh2-conics"

[run.controller]
lh2_calibration = "3f9a"
```

CI usually has no files at all, and sets what it needs as env vars:

```yaml
env:
  DOTBOT_CONN: simulator
  DOTBOT_SITE: ./tests/sites/virtual-lab      # a pack folder's path
  DOTBOT_FW_SEGGER_DIR: /opt/segger
run: dotbot run simulator --robots 50 --headless
```

## Top-level keys

| Key | Meaning |
|---|---|
| `conn` | The connection: `mqtts://host:port`, a serial path, or `simulator`. Overrides the active site's [connection](#a-sites-connection). |
| `swarm_id` | The swarm id, selecting the MQTT topic namespace. |
| `site` | The active [site](#sites): a pack's name, or a pack folder's path. `--site` or `DOTBOT_SITE` overrides it. |

## Tables

`[fw]`, firmware builds (`dotbot fw`):

| Key | Meaning |
|---|---|
| `board` | Target board, e.g. `dotbot-v3`. |
| `bare` | Default to bare-metal apps instead of sandboxed apps on boards that have a sandbox; `--bare` / `--sandboxed` override it per run. |
| `build_config` | `Debug` or `Release`. |
| `segger_dir` | The SEGGER Embedded Studio install. Also `DOTBOT_FW_SEGGER_DIR`, or `SEGGER_DIR`. |
| `artifacts_dir` | The firmware cache (default `~/.dotbot/artifacts`). Also `DOTBOT_FW_ARTIFACTS_DIR`, or `DOTBOT_ARTIFACTS_DIR`. |

`[fw.sources]`, the source folder `dotbot fw build` reads, one key per source
repository:

| Key | Meaning |
|---|---|
| `dotbot-firmware` | Your `DotBot-firmware` folder, for apps. |
| `swarmit` | Your `swarmit` folder, for `swarmit-sandbox`. |
| `mari` | Your `mari` folder, for `mari-gateway`. |

Each defaults to `repos/<name>` beside the project's `dotbot.toml`, and its env
var is `DOTBOT_FW_SOURCES_<KEY>` (`DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE`).
`dotbot fw build <role|app> --path <folder>` overrides it for one run.

`[device]`, one cabled device (`dotbot device`):

| Key | Meaning |
|---|---|
| `board` | Target board for flashing. |
| `probe` | The J-Link serial-number prefix selecting a probe (`--probe`). |

`[run.controller]`, the controller (`dotbot run controller`, `run simulator`):

| Key | Meaning |
|---|---|
| `headless` | Don't open the web UI in a browser on start (default false; it is still served). |
| `http_port` | The REST/WebSocket port (default 8000). |
| `http_host` | The interface the API binds to (default `127.0.0.1`). `0.0.0.0` exposes it to the network; the API is unauthenticated. |
| `lh2_calibration` | The LH2 calibration to run on: a file path, the exact `--tag` it was collected with, or an id prefix of one of the site's calibrations (see [where calibrations are found](#where-calibrations-are-found)). |
| `lh2_calibration_max_age_days` | Warn at load when the LH2 calibration is older than this many days (default 30, `0` never warns). |
| `stale_after_s` | Seconds without an advertisement before a robot is stale (default 3). See [how long a robot is kept](rest.md#how-long-a-robot-is-kept). |
| `lost_after_s` | Seconds before a robot is lost and left out of `GET /controller/dotbots` (default 10). Longer than `stale_after_s`. |
| `forget_after_s` | Seconds before a robot is forgotten (default 300, `0` never forgets). Longer than `lost_after_s`. |
| `camera_calibration` | The overhead camera registration to draw on the map, in the same forms. Written by `dotbot run calibrate-camera collect`. |
| `camera_detect` | Run the robot detector on a registered camera (default true). False serves the layer as a picture only. |
| `camera_max_robots` | The most robots one camera frame reports. |
| `camera_detect_share` | The share of one CPU core the detector may hold on average. |
| `simulator_area` | Where a simulator places its robots (`--area`): an area name, a `+`-joined composite or `x,y,w,h` in mm. Defaults to the site's field. |
| `simulator_collisions` | Simulated robots block one another at contact (`--collisions/--no-collisions`, default true). False lets them drive through each other. |
| `swarmit_url` | The swarmit server the console's orchestration panel talks to, proxied at `/swarmit/*` (default `http://localhost:8001`). |
| `swarm_serve` | Start a local swarm server at `swarmit_url` beside an MQTT connection, unless one already answers there (default true; `DOTBOT_SWARM_SERVE`). |
| `mrta_url` | The MRTA mode server the console's MRTA toggle talks to, proxied at `/mrta/*`. Unset by default, which hides the control. |

`[login."<broker host>"]`, a broker login (`~/.dotbot/dotbot.toml` only):

| Key | Meaning |
|---|---|
| `user` | The user name sent to that broker. |
| `password` | Its password. |

See [broker logins](#broker-logins).

Unknown keys are rejected, so a typo fails loud. A removed key fails with one
line saying where it went: `[run] conn` and `[swarm]` are the top-level `conn`
and `swarm_id`, `site_dirs` and inline `[sites.*]` tables are
[the two site homes](#site-packs), and `log_level`, `[run.gateway]` and the
`[run.controller]` keys `background_map`, `log_output`, `csv_data_output`,
`gw_address` and `simulator_init_state` are flags only.

## Sites

A **site** is the place you work in and its usual way in. It says where zero
is, how big the floor is, which named rectangles, **areas**, it holds, and
optionally which broker it is reached through. Positions, calibrations and
the console map are in the active site's frame: millimetres, zero at the
top-left corner of the extent, x to the right, y down.

A site lives in its own folder, a **site pack**, named after the site:

```text
lab/
├── site.toml          # anchor, extent_mm, connection, areas
└── calibrations/      # optional: the site's LH2 and camera calibration files
```

```toml
# lab/site.toml
anchor    = "corner of the tiles by the door; x along the window wall"
extent_mm = [5000, 5000]

[connection]
conn = "mqtts://broker.lab.example:8883"

[areas]
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

The active site is, in order: `--site`, `DOTBOT_SITE`, the `site` key of the
files, then `default`. `dotbot site use NAME` writes the key for you.

### Site packs

Packs are found in two homes, with nothing to configure:

| Home | What goes there |
|---|---|
| `sites/` beside the project's `dotbot.toml` | the team's packs, committed with the project |
| `~/.dotbot/sites/` | the packs `dotbot site add` installs, and any of your own; seen from every folder |

When both hold a pack of the same name, the project's wins, with a one-line
notice naming the one it hides. A `site` that is a path (`./elsewhere/hall-b`,
`~/packs/hall-b`, anything with a `/`) names that pack folder directly; its
name is the folder's name, so its calibrations are still kept under
`~/.dotbot/calibrations/hall-b/`. `dotbot site list` lists every site, its
connection and where it was read from. To install or share a pack, see
[`dotbot site`](../cli/site.md).

### A site's connection

A site may name the broker it is usually reached through, so working in it
needs no `conn` of your own:

```toml
[connection]
conn     = "mqtts://broker.lab.example:8883"
swarm_id = "0A1B"        # only if whoever publishes the site owns the network
```

| Key | Meaning |
|---|---|
| `conn` | A broker URL, `mqtt://` or `mqtts://`, or `simulator` for a site that exists only in simulation. A serial path names a port on one machine and is refused, and so is a URL with `user:pass@`. |
| `swarm_id` | The swarm id, when everyone working there shares one network. Leave it out when several people flash gateways at their own ids; each then sets their own. |

A site has one network: all of its gateways share one net id, even at a
thousand robots. A second network in the same room is `--conn` /
`--swarm-id` or your own `conn`, never a copy of the site, since the site's
name keys its calibrations and is stored on the robots.

Your own `conn` and `swarm_id` beat the site's, so a `conn` left in
`~/.dotbot/dotbot.toml` hides every site's broker in every folder. The
one-line banner that `run controller`, `run gateway` and the swarm commands
that act on robots print before connecting names each value's source,
`dotbot site use` warns when one of your files or the environment hides the
site's connection, and `dotbot config unset conn` puts the site's back.

An MQTT `conn` with no swarm id anywhere fails with `site lab names no swarm;
pass --swarm-id, or save one with dotbot config set swarm_id <id>`.

On a site whose connection is `simulator`, `dotbot run controller` and
`dotbot run simulator` do the same thing. `dotbot run simulator` is
`run controller --conn simulator` on whatever site is active, so a real site
can be rehearsed in simulation too.

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

A site has **at most one field**; two is an error naming both. When no area
has the `field` role, the field is the first area that is neither staging nor
corner, else the first area, else the whole extent. Areas keep the order they
are declared in.

### Where calibrations are found

A calibration is always the one you name: a file path, the exact `--tag` it was
collected with, or a prefix of its id, never "the latest". A tag or an id is
looked up in the site's pack `calibrations/` folder first, then in
`~/.dotbot/calibrations/<site>/`, where `collect` writes; the first folder with
a match wins.

LH2 calibration files are schema 3; an older one is refused, and the
[LH2 guide](../guides/lh2-calibration.md#upgrading-from-schema-2) says how to
re-solve it.

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

## Broker logins

A broker login comes from one of two places:

- `[login."<host>"]` in `~/.dotbot/dotbot.toml`, saved with
  `dotbot config login <host>`. Only that host's broker ever gets it, whoever
  chose the broker, so it needs no approval. The file is made readable by you
  alone, and a warning says so when it is not. A `[login]` anywhere else is
  refused, so a password never reaches a committed file.
- `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` in the environment, for CI and
  one-off runs. These go to a broker only when:
  - you named it yourself: a flag, an env var, or one of your config files;
  - it is the broker of a pack you approved at `dotbot site add`, the
    question it asks before adding a pack that names a broker, or the one
    you gave `dotbot config init --conn`;
  - it is the broker of a pack beside your project, or one you named by path;
  - it runs on this machine (`localhost`).

  `dotbot site add` and `dotbot config init` record that broker in the
  pack's `.approved.toml`. If an installed pack's broker later differs, the env's
  login is withheld, and a one-line warning names the
  `dotbot site add --force <pack>` that approves it again.

The env's login wins where it is allowed; elsewhere a saved login for the
host is used. Neither goes over plain `mqtt://` to another host.
`dotbot config show` says which login the broker gets, and why.

`DOTBOT_MQTT_INSECURE=1` skips checking the broker's certificate for one run,
for a bench whose certificate has expired. It is env-only on purpose, so it is
never left on.

## Inspecting the resolved config

| Command | Shows |
|---|---|
| `dotbot config show` | The files in use, where the site, `conn` and `swarm_id` each came from and what they hide, which login the broker gets, `DOTBOT_*` variables nothing reads, and every key the files set, merged. `--json` for scripts. |
| `dotbot config path` | The files in use, one per line. |
| `dotbot site list` | Every site the two homes hold, its connection, and which one is active. |
