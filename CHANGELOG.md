# Changelog

All notable changes to PyDotBot are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `dotbot config init --conn <broker>` on a site whose pack already exists
  writes the broker into that pack's `[connection]` instead of dropping it.
- The package declares the Python 3.11 it needs (`requires-python`), and the
  README says so next to `pip install`.
- Releases publish the wheel to PyPI, not only the sdist.
- `dotbot swarm serve` starts from a plain `pip install pydotbot`: PyDotBot
  depends on `swarmit[dashboard]`, whose PyJWT and SQLAlchemy the server needs.

### Changed

- `dotbot run controller` with an MQTT connection starts a local swarm server
  (`dotbot swarm serve --local`) and stops it on exit, so the console shows
  robots in their bootloader without a second terminal. One already answering
  at `swarmit_url` is reused. `--no-swarm-serve` or `[run.controller]
  swarm_serve = false` turns it off.

## [0.32.0] - 2026-10-01

Upgrading from 0.31.0? Read [Upgrading from 0.31.0](#upgrading-from-0310) first:
the config file, site definitions, LH2 calibration files and the robots'
sandbox firmware all change.

### Added

- `dotbot guide` prints a getting-started page for people and AI coding agents,
  and `dotbot --help` points at it; `guide --install` writes an agent skill
  that points coding agents at it.
- The config is up to three layered TOML files, merged key by key, the closest
  to you winning: `./dotbot.local.toml` (you, in a project; untracked) over
  `./dotbot.toml` (the project) over `~/.dotbot/dotbot.toml` (you, on this
  machine). A flag or a `DOTBOT_*` variable beats all three for one run.
  `-c FILE` takes `<stem>.local.toml` beside it as its overlay.
- `dotbot config set KEY VALUE` and `config unset KEY` change one key in a file
  git does not track: a machine key (`fw.segger_dir`, `device.probe`, ...) in
  `~/.dotbot/dotbot.toml`, any other in `./dotbot.local.toml` in a project,
  else in the user file. `--user` / `--project` pick the file.
- `dotbot config login HOST` saves a broker login as `[login."HOST"]` in
  `~/.dotbot/dotbot.toml`, readable by you alone; only that host's broker ever
  gets it.
- `config init --project` starts a project: `./dotbot.toml`, its site in
  `./sites/`, and `dotbot.local.toml` in `.gitignore`.
- A site carries its usual way in: a `[connection]` table (`conn`, a broker
  URL, and optionally `swarm_id`) in its pack's `site.toml`, the lowest layer
  for `conn` and `swarm_id`; a site that exists only in simulation takes
  `conn = "simulator"`.
- `dotbot site use`, `site list` and `site show`, and `site add --use`; `site
  add` shows a pack's broker and asks before adding it (`--yes` to skip).
- `site` may name a pack folder by its path.
- `[fw] artifacts_dir`, and `DOTBOT_FW_SEGGER_DIR` beside `SEGGER_DIR`.
- `[run.controller] headless`, `http_port` and `http_host` are read; they were
  accepted and ignored.
- A `DOTBOT_*` variable nothing reads is named in a warning, with the close
  name when there is one.
- `run controller`, `run gateway` and the swarm commands that act on robots
  print one line naming the site, conn and swarm id and where each came from.
- `dotbot run simulator --robots N` generates a fleet of N robots 200 mm
  apart, centred in the site's `field` area; `--write-init-state FILE` saves
  it as an init-state file to edit and reuse with `--simulator-init-state`.
- Site areas take a role: `field` (where experiments happen and what a
  calibration covers), `staging` (where robots park) or `corner`. The
  simulator, `swarm calibrate-lh2 collect`, the camera and the console default
  to the field. `dotbot config init` writes a site with a field and a staging
  strip (`--field` sizes it).
- `swarm calibrate-lh2 collect --over AREA` and `--square MM` choose the
  calibration points; the console draws the calibrated span and hatches the
  extrapolated rest of the site.
- `dotbot site add` and `site export` share a site as a pack folder, zip or
  git repository.
- `swarm calibrate-lh2 collect --spin` (experimental) calibrates with no
  marks on the floor, from robots spinning in place with the `calibrate-spin`
  app, and `dotbot site init NAME --from-calibration ID` writes a site around
  those robots. `dotbot swarm -d`, `-n` and `-s` reach `calibrate-lh2`, so
  `push` can go to named robots only.
- `fw build` and `fw fetch` take the same role and app names, `fw list` shows
  where each set came from, and every flash command picks a set with `-f`.
- `PUT /controller/dotbots/waypoints` and `DELETE /controller/dotbots/waypoints`
  set or clear many robots' waypoints in one request; `GET
  /controller/robot_models` serves each robot model's body.
- The simulator runs the firmware's control code, compiled to WebAssembly, and
  the controller, simulator and console keep up with 1000 robots.
- `[run.controller] stale_after_s`, `lost_after_s` and `forget_after_s`
  (default 3, 10 and 300 s; `0` never forgets) set when a silent robot turns
  stale, lost and forgotten. The console fades a stale robot and hides a lost
  one; **Lost robots** in the Layers tab shows them.

### Changed

- **Breaking:** LH2 calibrations are solved on the true pinhole camera point
  of each station. Calibration files are schema 3, so every calibration id
  changes, and a schema 2 file is refused. Robots need the matching swarmit
  sandbox (0.11.0 or newer); `swarm calibrate-lh2 push` refuses robots on older
  firmware and names them for a cable reflash.
- **Breaking:** the user config is `~/.dotbot/dotbot.toml`, the same name as a
  project's. A `~/.dotbot/config.toml` with no `dotbot.toml` beside it is
  refused with the rename to make.
- **Breaking:** site packs live in two homes, `sites/` beside the project's
  `dotbot.toml` and `~/.dotbot/sites/`; the project's wins a clash.
- **Breaking:** `dotbot config init` writes the site pack to `~/.dotbot/sites/`
  and selects it in `~/.dotbot/dotbot.toml`, keeping the rest of that file;
  `--global` is gone. A broker `--conn` becomes the site's `[connection]`.
- **Breaking:** `dotbot site use` writes `./dotbot.local.toml` in a project,
  never the committed `dotbot.toml` unless given `--project`.
- **Breaking:** `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` go to a broker only
  when you named it yourself (flag, env, one of your files), approved it at
  `dotbot site add`, it comes from a pack beside your project or one named by
  path, or it is local; never over plain `mqtt://` to another host. `site add`
  records the approved broker, and a pack whose broker later differs gets no
  env login until it is approved again.
- `dotbot config show` prints the files in use, where the site, `conn` and
  `swarm_id` each came from and what they hide, and which login the broker
  gets (`--json` for scripts); `config path` lists the files. The list of
  sites moved to `dotbot site list`.
- **Breaking:** `/controller/ws/status` is replaced by `/controller/ws/stream`
  (`hello`, `snapshot`, `delta`, `event` frames; a client faster than 1 Hz
  acks them). `position_history` is `trail`, `?trail=N` returns the newest N
  points (default 0) and `max_positions` is gone. `pose` is `{x, y,
  heading_deg, heading_source}`. Waypoints of the wrong kind for the robot are
  refused with 422. `dotbot run demo qr` publishes stream frames on
  `/notify`.
- **Breaking:** the "arena" defaults are gone: a site whose experiment area is
  called `arena` renames it `field` or gives it `role = "field"`. Two fields in
  one site is an error. The controller refuses a calibration made in another
  site. The `motions` example takes `--area` instead of `--arena-size`, the
  charging example needs a staging area, and the simulator example's site is
  `virtual-lab`.
- **Breaking:** firmware commands use role and app names. `fw artifacts` is
  folded into `fw build`; `fw build -a` is `--part`, `--repo` / `--checkout` is
  `--path`; `fw fetch -S`, `-f local` and `--local-root` are gone.
  `device flash-mari-gateway`, `flash-swarmit-sandbox` and `flash-programmer`
  are `device flash mari-gateway`, `swarmit-sandbox` and `programmer`;
  `swarm flash rc-car` is `swarm flash remote-control`. Apps are sandboxed by
  default (`--bare` / `--sandboxed`, `[fw].bare` replaces `[fw].sandbox`), and
  `device flash <app>` never builds. `[fw].firmware_repo` is `[fw.sources]
  dotbot-firmware` (`DOTBOT_FW_SOURCES_DOTBOT_FIRMWARE`).
- `swarm calibrate-lh2 push` refuses a named robot that is in its app, which
  would drop the calibration; a push to the whole fleet leaves such robots out
  and lists them.
- **Breaking:** a robot the controller stops hearing is stale, then lost,
  then forgotten (dropped, so its routes answer 404 and it comes back as a new
  robot). `DotBotStatus.INACTIVE` is `DotBotStatus.STALE`, still `1`. `GET
  /controller/dotbots` leaves lost robots out unless given
  `?include_lost=true`, `status=` or `address=`, and sends the resume headers
  only with `?include_lost=true`. A forgotten robot arrives on the stream as
  `null` in a delta, and `hello.protocol` is 2.
- `dotbot fw fetch` pulls DotBot-firmware 1.25.0 (with `calibrate-spin`) and
  the installed swarmit's release, now at least 0.11.0.
- `dotbot fw fetch` takes a release name, `swarmit` or `dotbot-firmware`, as
  well as a role or an app: `dotbot fw fetch dotbot-firmware -f 1.25.0`.
- LH2 channel 14 uses the 901000 rotor period. A site calibrated on channel
  14 recalibrates once.

### Removed

- **Breaking:** `dotbot deployment`, the root `--deployment` flag,
  `DOTBOT_DEPLOYMENT` and the `[deployment.*]` / `default_deployment` config
  keys. A config that still has them fails to load and says where the keys
  went: a site's `[connection]` and `dotbot site use`.
- **Breaking:** inline `[sites.<name>]` tables and `site_dirs`; a site is a
  pack. The `[run]` / `[swarm]` copies of `conn` and `swarm_id` (the top-level
  keys remain), and the keys nothing read: `log_level`, `[swarm] devices`,
  `[run.gateway]`, and the `[run.controller]` keys `background_map`,
  `log_output`, `csv_data_output`, `gw_address` and `simulator_init_state`
  (their flags remain). Each fails to load with one line saying where it went.
- **Breaking:** `dotbot run controller --config-path`, the flat legacy TOML.
  `dotbot swarm -c`, swarmit's own file, stays.
- **The classic web UI** (`dotbot/frontend/`, served at `/PyDotBot`). The
  console at `/console` is the only browser UI; `/PyDotBot` now answers 404,
  so update bookmarks. Its classic-only views go with it: the REST demo page,
  the SailBot map and the qrkey phone page. The phone page is retired pending
  a qrkey mode in the console: `dotbot run demo qr` still relays the
  controller stream to MQTT and shows the QR, but no phone page reads what it
  relays yet.
- `config_sample.toml`, replaced by `dotbot.example.toml`, which is what
  `config init --project` writes.

### Upgrading from 0.31.0

1. Rename `~/.dotbot/config.toml` to `~/.dotbot/dotbot.toml`. Move each inline
   `[sites.<name>]` table into `~/.dotbot/sites/<name>/site.toml` (or `sites/`
   beside a project's `dotbot.toml`), drop `site_dirs`, and put a deployment's
   broker in its site's `[connection]`. `[fw].firmware_repo` becomes
   `[fw.sources] dotbot-firmware`. Each removed key fails to load with a line
   saying where it went; `dotbot config show` checks the result.
2. Re-solve every LH2 calibration as schema 3 from its stored samples (no new
   capture), as in the LH2 calibration guide, or collect a new one.
3. Reflash every robot by cable with the swarmit 0.11.0 sandbox, both cores and
   the calibration at once: `dotbot device flash swarmit-sandbox
   --lh2-calibration <schema 3 file>`. Never flash the new bootloader alone
   over an old network core.
4. Over the air, flash the sandbox apps again (`dotbot swarm flash ...`), then
   check positions.
5. Move clients of `/controller/ws/status` to `/controller/ws/stream`.
6. Scripts that need lost robots from `GET /controller/dotbots` pass
   `?include_lost=true`; replace `DotBotStatus.INACTIVE` with
   `DotBotStatus.STALE`; stream clients accept a `null` robot in a delta.

## 0.31.0 and earlier

Changes up to 0.31.0 were not split by release.

### Added

- Unified `dotbot` CLI dispatcher that mounts every workflow (controller,
  simulator, testbed ops, calibration, demos, keyboard/joystick) under one
  command. Subcommand modules are loaded lazily so `dotbot --help` stays
  cheap.
- `dotbot run demo` discoverable launcher; `dotbot run demo qr` runs the
  qrkey phone-bridge demo.
- `dotbot fw` mock surface (scaffold/build/flash subcommands; placeholder
  for the firmware-developer workflow).
- **Vendored `dotbot-provision`** into `dotbot/provision/`. All five
  subcommands available as `dotbot testbed provision <fetch|flash|
  flash-hex|read-config|flash-bringup>`.
- **Vendored `dotbot-lh2-calibration` (Python side)** into
  `dotbot/calibration/`. Surfaced as `dotbot run calibrate-lh2` with
  two subcommands:
  - `collect` — runs the Textual TUI (default — bare
    `dotbot run calibrate-lh2` invokes this for muscle memory)
  - `apply <path>` — write the saved calibration as a C header to
    `<path>` (replaces the previous `dotbot-calibration-exporter`;
    today the only consumer is the swarmit secure bootloader which
    `#include`s the file at compile time)
  The C firmware in the `dotbot-lh2-calibration` repo is unchanged.
  Future OTA / swarm-wide counterparts (`collect` over MQTT,
  `apply` as OTA push) will live under `dotbot swarm
  calibrate-lh2`.
- Calibration records are now saved as timestamped, schema-versioned
  TOML files (`~/.dotbot/calibration-<UTC timestamp>.toml`) carrying
  metadata (number of LH stations, calibration distance, creation
  time) alongside the homography bytes (hex-encoded under
  `[calibration].data_hex`). The legacy `~/.dotbot/calibration.out`
  binary is still written as a back-compat byproduct so external
  consumers (swarmit OTA, `dotbot testbed provision flash`) keep
  working unchanged; once they learn to read TOML the legacy write
  will be dropped. `load_calibration()` prefers the newest TOML and
  falls back to `calibration.out` if no TOML files exist.
- `dotbot testbed provision flash --calibration <path>` accepts a
  `.toml` calibration file in addition to the legacy binary format
  (the file extension drives the parsing path).
- Optional dependency groups (revised):
  - `pip install dotbot[testbed]` adds `swarmit` (still external)
  - `pip install dotbot[provision]` adds `intelhex` (provision runtime)
  - `pip install dotbot[calibrate]` adds `opencv-python` + `textual`
  - `pip install dotbot[all]` pulls all three

### Changed

- **Breaking - the controller binds loopback by default.** `dotbot run
  controller` served the REST/WebSocket API on `0.0.0.0`, putting an
  unauthenticated API on every interface; the new `/swarmit/*` proxy would
  republish the swarmit server the same way. It now binds `127.0.0.1`. To reach
  it from another machine pass `--controller-http-host 0.0.0.0`, set
  `[run.controller] http_host`, or `DOTBOT_RUN_CONTROLLER_HTTP_HOST`; binding
  beyond loopback logs a warning.
- **`dotbot run controller` now opens the unified web console** at `/console`,
  and `/` redirects there. If the console is not built, the controller serves
  the API and says so rather than opening a dead tab.
- **Device addresses are rendered uppercase everywhere**, through a single
  `dotbot.addr_to_hex()` helper, and are matched case-sensitively. The address
  is the join key between the control plane and swarmit, which already
  uppercased it, so the two now agree; `DOTBOT_ADDRESS_DEFAULT` and
  `GATEWAY_ADDRESS_DEFAULT` were already written this way. Consequences:
  a lowercase address in a REST path or MQTT topic now reaches no DotBot,
  and a `--csv-data-output` file spanning the upgrade holds both cases for
  the same robot (re-normalise with `df.address.str.upper()` before grouping).
  `-d/--dotbot-address` on `dotbot run joystick` / `keyboard` accepts either
  case and normalises.
- **Breaking — CLI reorganized into four object-namespaces.** The top
  level is now exactly `fw` (firmware artifacts), `device` (one cabled
  device), `swarm` (the fleet), and `run` (host-side processes). The flat
  process verbs moved under `run`: `dotbot controller` → `dotbot run
  controller`, and likewise `gateway` / `simulator` / `demo` / `keyboard` /
  `joystick`; `dotbot calibrate-lh2` → `dotbot run calibrate-lh2`. The
  Makefile escape hatch moved from `dotbot make` to `dotbot fw make`.
  `run` subcommands are still loaded lazily, so `dotbot run --help` stays
  cheap.
- The qrkey integration moved from `dotbot/qrkey.py` to
  `dotbot/examples/qrkey_demo/`. The demo is now a separate process that
  consumes the controller's REST API — the controller stays agnostic to
  qrkey.
- `dotbot/examples/qrkey_demo/` is a thin client of the upstream `qrkey`
  package (now pinned `>= 0.12.2`); none of its code is vendored.
- Frontend polls qrkey count every 1 s for faster Show QR button
  feedback.

### Removed

- `dotbot-qrkey` console script — use `python -m dotbot.examples.qrkey_demo`
  or `dotbot run demo qr` instead.
- `dotbot-edge-gateway` console script — the referenced module
  `dotbot.edge_gateway_app` never existed; the entry was silently broken.
- `pin_code` tox env — referenced `dotbot/pin_code_ui/` which never
  existed.
- `dotbot-provision` and `dotbot-lh2-calibration` PyPI dependencies
  (folded into the `dotbot` package). The standalone PyPI packages are
  scheduled for deprecation releases that point users at `pip install
  dotbot[provision]` / `pip install dotbot[calibrate]`.
- `dotbot-controller`, `dotbot-keyboard`, and `dotbot-joystick` console
  scripts — removed outright (no longer aliased). Use `dotbot run
  controller` / `dotbot run keyboard` / `dotbot run joystick`.

### Deprecated

- The standalone `dotbot-provision` and `dotbot-lh2-calibration` PyPI
  packages will issue `DeprecationWarning` on their next release and
  point users at `pip install dotbot[provision]` /
  `pip install dotbot[calibrate]`. Their console scripts
  (`dotbot-provision`, `dotbot-calibration`,
  `dotbot-calibration-exporter`) are not re-exported by `dotbot`
  because they never shipped from this package; use the unified
  subcommands instead.
