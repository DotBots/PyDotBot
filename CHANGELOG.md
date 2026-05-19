# Changelog

All notable changes to PyDotBot are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Unified `dotbot` CLI dispatcher that mounts every workflow (controller,
  sim, testbed ops, calibration, demos, keyboard/joystick) under one
  command. Subcommand modules are loaded lazily so `dotbot --help` stays
  cheap.
- `dotbot demo` discoverable launcher; `dotbot demo qr` runs the qrkey
  phone-bridge demo.
- `dotbot fw` mock surface (scaffold/build/flash subcommands; placeholder
  for the firmware-developer workflow).
- **Vendored `dotbot-provision`** into `dotbot/provision/`. All five
  subcommands available as `dotbot testbed provision <fetch|flash|
  flash-hex|read-config|flash-bringup>`.
- **Vendored `dotbot-lh2-calibration` (Python side)** into
  `dotbot/calibration/`. New unified `dotbot calibrate` subgroup runs
  the Textual TUI by default; `dotbot calibrate export PATH` writes the
  C header for the swarmit bootloader bake-in. (The C firmware in the
  `dotbot-lh2-calibration` repo is unchanged.)
- Optional dependency groups (revised):
  - `pip install dotbot[testbed]` adds `swarmit` (still external)
  - `pip install dotbot[provision]` adds `intelhex` (provision runtime)
  - `pip install dotbot[calibrate]` adds `opencv-python` + `textual`
  - `pip install dotbot[all]` pulls all three

### Changed

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
  or `dotbot demo qr` instead.
- `dotbot-edge-gateway` console script — the referenced module
  `dotbot.edge_gateway_app` never existed; the entry was silently broken.
- `pin_code` tox env — referenced `dotbot/pin_code_ui/` which never
  existed.
- `dotbot-provision` and `dotbot-lh2-calibration` PyPI dependencies
  (folded into the `dotbot` package). The standalone PyPI packages are
  scheduled for deprecation releases that point users at `pip install
  dotbot[provision]` / `pip install dotbot[calibrate]`.

### Deprecated

- `dotbot-controller`, `dotbot-keyboard`, and `dotbot-joystick` console
  scripts remain working as backwards-compat aliases for one deprecation
  cycle. Prefer `dotbot <subcommand>` for new code.
- The standalone `dotbot-provision` and `dotbot-lh2-calibration` PyPI
  packages will issue `DeprecationWarning` on their next release and
  point users at `pip install dotbot[provision]` /
  `pip install dotbot[calibrate]`. Their console scripts
  (`dotbot-provision`, `dotbot-calibration`,
  `dotbot-calibration-exporter`) are not re-exported by `dotbot`
  because they never shipped from this package; use the unified
  subcommands instead.
