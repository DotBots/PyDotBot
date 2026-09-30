# Changelog

All notable changes to PyDotBot are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A site may carry its usual way in: a `[connection]` table (`conn`, a broker
  URL, and optionally `swarm_id`) in a pack's `site.toml` or an inline
  `[sites.<name>.connection]`. It is the lowest config layer for `conn` and
  `swarm_id`; a `virtual = true` site may take `conn = "simulator"`.
- `dotbot site use`, `site list` and `site show`, and `site add --use`; `site
  add` shows a pack's broker and asks before adding it (`--yes` to skip).
- `run controller`, `run gateway` and the swarm commands that act on robots
  print one line naming the site, conn and swarm id and where each came from.
- `dotbot run simulator --robots N` generates a fleet of N robots 200 mm
  apart, centred in the site's `field` area; `--write-init-state FILE` saves
  it as an init-state file to edit and reuse with `--simulator-init-state`.
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

- **Breaking:** the user config is `~/.dotbot/dotbot.toml`, the same name as a
  project's. A `~/.dotbot/config.toml` with no `dotbot.toml` beside it is
  refused with the rename to make.
- **Breaking:** `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` go to a broker only
  when `DOTBOT_MQTT_HOST` names it, you named the broker yourself (flag, env,
  your file, an inline site table in it included) or it is local, and never over plain `mqtt://` to another host.
- `dotbot config show` prints where the site, `conn` and `swarm_id` each came
  from and what they hide, and where the credentials go (`--json` for
  scripts); the list of sites moved to `dotbot site list`.
- `dotbot config init --conn` writes a broker into the site it creates.
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

- **Breaking:** `dotbot deployment`, the root `--deployment` flag,
  `DOTBOT_DEPLOYMENT` and the `[deployment.*]` / `default_deployment` config
  keys. A config that still has them fails to load and says where the keys
  went: a site's `[connection]` and `dotbot site use`.
- **The classic web UI** (`dotbot/frontend/`, served at `/PyDotBot`). The
  console at `/console` is the only browser UI; `/PyDotBot` now answers 404,
  so update bookmarks. Its classic-only views go with it: the REST demo page,
  the SailBot map and the qrkey phone page. The phone page is retired pending
  a qrkey mode in the console: `dotbot run demo qr` still relays the
  controller stream to MQTT and shows the QR, but no phone page reads what it
  relays yet.
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
