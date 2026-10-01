# `dotbot config` - inspect and change the config

`dotbot` reads up to three TOML files so commands don't repeat shared
settings: `~/.dotbot/dotbot.toml` (you, on this machine), a project's
`./dotbot.toml` (committed) and `./dotbot.local.toml` beside it (you, in that
project). `config` shows what the CLI resolved and where each value came
from, and changes one key at a time in a file git does not track. The file
format, every key and the precedence rule are in the
[configuration reference](../reference/configuration.md).

## Which command do I want?

| Goal | Command |
|---|---|
| Start: a site with a field, selected | `dotbot config init` |
| Start a project others will clone | `dotbot config init --project` |
| Save a setting | `dotbot config set KEY VALUE` |
| Go back to the layer below | `dotbot config unset KEY` |
| Save the login for a broker | `dotbot config login HOST` |
| See where the site, conn and swarm id came from | `dotbot config show` |
| List the files in use | `dotbot config path` |

## `init`

Writes a site pack with a field and selects it, so the simulator, calibration
and the examples have a floor to work on from the first run:

```bash
dotbot config init                                             # a 2 x 2 m field in site "default"
dotbot config init --field 1.5m --site lab                     # a 1.5 x 1.5 m field in site "lab"
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234  # the site's broker, your swarm
dotbot config init --project                                   # ./dotbot.toml and ./sites/default/
```

By default it writes `~/.dotbot/sites/<site>/site.toml` and sets `site` in
`~/.dotbot/dotbot.toml`, keeping everything else in that file. The pack:

```toml
# Zero is the top-left corner of the extent, x right, y down, millimetres.
anchor = "top-left corner of a 5 x 5 m floor; the field starts 1.5 m in from each wall"
extent_mm = [5000, 5000]

[areas]
field   = { x = 1500, y = 1500, w = 2000, h = 2000 }
staging = { x = 1500, y = 3500, w = 2000, h = 600 }
```

The **field** is where experiments happen and what a calibration covers; the
**staging** strip along its bottom edge is where robots park. Once you have
measured a real room, edit `site.toml`; the
[configuration reference](../reference/configuration.md#sites) has every key.

`--project` starts a project in the current folder instead: `./dotbot.toml`
naming the site, the pack in `./sites/<site>/`, and, in a git repository that
does not already ignore it, `dotbot.local.toml` added to `.gitignore`. Your
own `--swarm-id` or serial `--conn` then go to `./dotbot.local.toml`.
`dotbot.example.toml` in the repository is exactly the `dotbot.toml` that
`init --project` writes.

| Flag | Meaning |
|---|---|
| `--field` | The field's size (default `2m`): one value for a square, `WxH` for a rectangle. A bare number is mm, and `1500mm`, `1.5m` and `2x3m` also work; decimals only with `m`. From 100 mm to 100 m. Above 5 m on a side it warns that one LH2 station rarely covers that well. |
| `--site` | The site's name (default `default`); its calibrations are kept under `~/.dotbot/calibrations/<site>/`. |
| `--conn` | A broker URL becomes the site's `[connection]`; a serial path or `simulator` is your own `conn`, since it belongs to this machine. |
| `--swarm-id` | Your own `swarm_id`. |
| `--project` | Start a project in the current folder, as above. |
| `-f`, `--force` | Overwrite an existing `./dotbot.toml` or site pack. Without it an existing pack is kept. |

## `set` / `unset`

`set` saves one key; `unset` removes it, so the layer below applies again.
KEY is spelled as in TOML:

```bash
dotbot config set swarm_id 1200
dotbot config set conn mqtt://localhost:1883
dotbot config unset conn                                   # back to the site's broker
dotbot config set fw.segger_dir "/usr/share/segger_embedded_studio_for_arm_7.22"
dotbot config set fw.sources.dotbot-firmware repos/wt-DotBot-firmware-x
dotbot config set run.controller.lh2_calibration 3f9a
```

Each write prints the file it changed. A key true of this machine
(`fw.segger_dir`, `device.probe`, the boards, the camera limits, the service
URLs) goes to `~/.dotbot/dotbot.toml` wherever you run it. Any other key goes
to `./dotbot.local.toml` when a project's `dotbot.toml` is in use, else to
`~/.dotbot/dotbot.toml`. The full routing table is in the
[configuration reference](../reference/configuration.md#who-writes-what).

| Flag | Meaning |
|---|---|
| `--user` | Write `~/.dotbot/dotbot.toml`. |
| `--project` | Write the project's `dotbot.toml`, which is committed; the write says so. |

VALUE is typed by the key: `true`/`false`, a whole number, or text. A
relative path is read from where you are and written as the file will read
it. Comments in the file are kept, and a value the schema refuses is refused
before anything is written. `set` warns when a closer layer (your overlay, an
env var) still hides what it wrote. A password is refused, since it would stay
in your shell history: use `login`.

## `login`

Asks for the user name and password the broker at HOST takes, and saves them
in `~/.dotbot/dotbot.toml` as `[login."HOST"]`, making the file readable by
you alone. Only that host's broker ever gets them.

```bash
dotbot config login argus.paris.inria.fr
dotbot config login mqtts://broker.lab.example:8883     # a URL works too
```

CI and one-off runs can set `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` instead;
[broker logins](../reference/configuration.md#broker-logins) has when each one
is sent.

## `show` / `path`

`show` prints the files in use, then one line per value with the layer it came
from and, under it, any lower layer it hides; then which login the broker
gets; then any `DOTBOT_*` variable nothing reads; then every key the files set,
merged, with passwords masked:

```text
$ dotbot config show
files:     ~/.dotbot/dotbot.toml (user)  dotbot.toml (project)  dotbot.local.toml (local)
site:      inria-aio-c  from dotbot.local.toml  project pack sites/inria-aio-c
           hides dotbot.toml site = "c405-arena"
conn:      mqtt://localhost:1883  from dotbot.local.toml
           hides site inria-aio-c conn = "mqtts://argus.paris.inria.fr:8883"
swarm_id:  A001  from dotbot.local.toml
login:     localhost: none
unknown:   DOTBOT_SWARMID (did you mean DOTBOT_SWARM_ID?): nothing reads it
```

The login line names the reason: `your [login] for <host>`, `you named it
(<where>)`, `approved at site add`, a pack beside your project, or `it runs on
this machine`; a withheld login shows the warning instead.

`--json` prints the same as JSON, for scripts. `path` prints the files in use,
one per line with its kind (`user`, `project`, `local`).

```bash
dotbot config show
dotbot config show --json
dotbot config path
```

## See also

- [Configuration reference](../reference/configuration.md) - the three files, every key, a site's connection, precedence.
- [`dotbot site`](site.md) - add a site pack, switch sites, list and show them, export one to share.
- [`dotbot fw`](fw.md) - reads `[fw]` (`segger_dir`, `[fw.sources]`) from these same files.
