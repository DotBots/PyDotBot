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
- Optional dependency groups: `pip install pydotbot[testbed]` adds
  `swarmit` + `dotbot-provision`; `pip install pydotbot[calibrate]` adds
  `dotbot-lh2-calibration`; `pip install pydotbot[all]` pulls all three.
- `dotbot demo` discoverable launcher; `dotbot demo qr` runs the qrkey
  phone-bridge demo.
- `dotbot fw` mock surface (scaffold/build/flash subcommands; placeholder
  for the firmware-developer workflow).

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

### Deprecated

- `dotbot-controller`, `dotbot-keyboard`, and `dotbot-joystick` console
  scripts remain working as backwards-compat aliases for one deprecation
  cycle. Prefer `dotbot <subcommand>` for new code.
