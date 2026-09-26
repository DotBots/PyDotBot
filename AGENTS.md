# PyDotBot

## Purpose

Python control plane for DotBots. Serial / cloud / edge adapters talk to a DotBot gateway (often via Mari → marilib); a FastAPI REST + WebSocket server exposes state; a React web console (`dotbot/console-web/`, served at `/console`) is the one browser UI: map, joystick, waypoints and swarmit orchestration. Ships a unified `dotbot` CLI whose top level is four object-namespaces: `fw` (firmware artifacts: build/fetch/list/make), `device` (one cabled device: flash/info), `swarm` (the fleet over the air), and `run` (host-side processes you launch — `dotbot run controller`, `run gateway`, `run simulator`, `run calibrate-lh2`, `run demo`, `run keyboard`, `run joystick`), plus DotBot/SailBot simulators. The `dotbot` dispatcher is the only console script — there are no per-command `dotbot-*` binaries.

This is the most active repo in the ecosystem (187 commits in last 90 days as of 2026-05-05).

## Tech stack

- **Backend**: Python ≥3.7, FastAPI + uvicorn, click, gmqtt + qrkey for MQTT, pyserial, structlog, pygame, pynput, numpy
- **Frontend**: React 18 + TypeScript, Vite, vitest + @testing-library (`dotbot/console-web/`)
- **Build**: `hatchling` (PEP 517) with custom sdist hook that builds and bundles the console; `tox` for orchestration; `pre-commit`; `ruff` / `isort` / `black`
- **Package**: pip (PyPI as `pydotbot`); npm for the console

## Entry points

- `dotbot/cli/main.py` — unified `dotbot` Click group (lazy subcommand loader)
- `dotbot/controller_app.py` — `dotbot run controller` subcommand backend; wires adapters and settings
- `dotbot/controller.py:1` — 737-line `Controller` class; central object
- `dotbot/console-web/src/App.tsx` — console UI root

## Controller surface (REST + WebSocket)

`dotbot/server.py` exposes robot state **two ways, and both are in use** - they
are not layered alternatives, and consumers pick one.

- **Pushed** - `/controller/ws/status`, server to client. Every advertisement
  carrying a new position sets `notification_cmd = UPDATE` in
  `dotbot/controller.py`, which fires `notify_clients()` and sends a
  `DotBotNotificationModel` to every connected socket. Its `data` is the full
  `DotBotModel`, so `lh2_position`, `mode`, `status` and battery all ride along.
  A `RELOAD` goes out when a robot appears or its status changes. This is what
  keeps the React UI live without polling.
- **Polled** - `GET /controller/dotbots`. What the Python examples use when they
  batch waypoints and wait for "done".

A second WebSocket runs the *other* way: **`/controller/ws/dotbots` is command
ingress**, accepting RGB LED, `move_raw` and waypoint messages. One socket is
state egress, the other is command ingress; do not describe "the WebSocket" as
though there were one.

**Arrival is inferred here, not reported by the robot.** The firmware advertises
state every 500 ms and never announces "done"; the controller sees `mode` flip
`AUTO` -> `MANUAL`, and that is the arrival signal. Anything waiting on a
waypoint batch is watching that field, whether it polls or subscribes.

## Build / run / test

```bash
pip install pydotbot                         # or `pip install -e .`
dotbot --help                    # unified dispatcher: fw / device / swarm / run
dotbot fw --help                 # firmware artifacts: build / fetch / list / make
dotbot device --help             # one cabled device: flash an app/role, read info
dotbot swarm --help              # the fleet over the air (swarmit; in the base install)
dotbot run --help                # host-side processes (controller, gateway, simulator, ...)
dotbot run controller --help     # start the controller
dotbot run calibrate-lh2 --help  # LH2 calibration (optional: pip install pydotbot[calibrate])
dotbot run demo --list           # built-in research demos

# Tests / lint / build
tox                                          # envs: tests, check, cli, web=console npm run lint, doc

# Console
cd dotbot/console-web && npm install
npm start                                    # dev
npm run build
npm test                                     # vitest, run in CI with lint, typecheck, build
```

### Scenario tests

`dotbot/tests/test_scenarios.py` drives the real controller through its REST
API against simulated robots, end to end: waypoint batches, headings, the
no-heading start, FAILED / HOLD / RECOVER, max speed, pre-emption and stop, a
ten-robot choreography, and the pre-fix (0, 0) guard. They are marked
`scenario` and deselected by default, so `pytest` and `tox` skip them:

```bash
pytest -m scenario --no-cov        # about a second; add -k to pick one
```

They run on a stepped clock (`DotBotSimulatorCommunicationInterface.step()`,
harness in `dotbot/tests/scenario_harness.py`): fixed seeds, no sleeps, no
browser, no network port. They validate the simulator and the controller
together, **not hardware**: the simulator runs a Python port of the firmware
steering, so a green run says nothing about a real robot.

CI: `.github/workflows/continuous-integration.yml` — `tox` on Linux/macOS/Windows (Py 3.11/3.12, Node 18/20). Also a CMake build of `utils/control_loop` against `DotBots/DotBot-libs`.

## Cross-repo dependencies

- **`qrkey`** — `pyproject.toml`; `dotbot/examples/qrkey_demo/`
- **`marilib`** — `pyproject.toml:48` (`marilib-pkg`); imported in `dotbot/adapter.py` (MarilibCloud, MarilibEdge, MQTT/Serial adapters, MariFrame). **Tight coupling.**
- **`PyDotBot-utils`** — `pyproject.toml`
- **`DotBot-libs`** — checked out in CI to build `utils/control_loop` C library
- **`DotBot-firmware`** — referenced only in README (flashing instructions); no code dep
- **`swarmit`** — sibling package, a core dependency (`pyproject.toml`);
  imported lazily inside `dotbot/cli/swarm.py`, which bridges the unified
  config's `conn`/`swarm_id` into swarmit's flags at the mount boundary.
- **`dotbot-provision`** — vendored into `dotbot/provision/` (Phase 2,
  2026-05). Standalone PyPI package scheduled for deprecation.
- **`dotbot-lh2-calibration` (Python)** — vendored into
  `dotbot/calibration/` (Phase 2, 2026-05). The C firmware stays in
  its own repo.

## State of repo (snapshot 2026-05-05)

- Last commit on `main`: 2026-04-29
- Total commits on `main`: 1050
- Commits in last 90 days: 187 (very hot)
- Branches:
  - `132-new-lh2-driver-not-compatible-with-dotbot-controller-2` — last 2024-03-12, 38 behind / 561 ahead. Stale LH2 work.
  - `141-add-support-for-the-lh2-mini-mote` — last 2024-09-11, 391 ahead / 0 behind. Abandoned LH2-mini.
  - `main-old` (2021), `other-os-compatibility` (2021), `gh-pages`
- TODO/FIXME/XXX/HACK: 6 (mostly in `dotbot/examples/`)

## Hot spots and known gaps

- **Heavy coupling to `marilib`**: `adapter.py` is essentially a wrapper over `MarilibEdge`/`MarilibCloud`. Strong consolidation candidate (or, at minimum, a clear layering boundary to clean up).
- **Two stale LH2-driver branches** (`#132`, `#141`) hundreds of commits ahead of main — likely the "outdated remote-control API / LH2 driver mismatch" tech debt referenced in project docs. Never merged.
- **`dotbot/examples/`** (`charging_station`, `work_and_charge`, `minimum_naming_game`, `labyrinth`, `motions`) is a research-experiment dumping ground shipped inside the package; most TODOs live here. Good candidate to extract or prune.
- **`tox.ini` references `dotbot/pin_code_ui`** (env `pin_code`) but that directory does not exist — dead config.
- **`.env` file is committed** (only `.env.example` should be) — audit for secrets.
- Maintainer (`aabadie`) is leaving summer 2026 — onboarding ergonomics matter here.

## Branch policy

- Default: `main`
- Stale branches `132-*`, `141-*`, `main-old`, `other-os-compatibility` are candidates for deletion (or revival via PR if salvageable).
- New work: feature branches off `main`, PRs even for solo work.

## Agent-task ideas

- **Audit `.env` for secrets** and replace with `.env.example`. Add `.env` to `.gitignore`.
- **Remove dead `pin_code` tox env** and the missing `dotbot/pin_code_ui` reference.
- **Investigate stale LH2 branches** (`#132`, `#141`): are they worth rebasing or are they superseded?
- **Extract `dotbot/examples/`** to a separate `pydotbot-examples` package, or move into a `research/` subdir excluded from the wheel.
- **Decompose `controller.py`** (737-line class) into smaller modules — the monolith makes onboarding harder.
- **Migrate `dotbot/protocol.py`** (the outdated remote-control mirror) to a shared package; coordinate with `DotBot-libs/drv/protocol.h`.
- **Add type hints + mypy** to the backend (currently typed inconsistently).

## Don't

- **Don't push to `main` without a PR** — this is the hottest repo and traceability matters.
- **Don't break the FastAPI REST/WebSocket contract** without bumping the major version — external scripts and the console depend on the surface.
- **Don't refactor `dotbot/adapter.py`** in isolation; coordinate with `marilib` and `qrkey`.
- **Don't bump `marilib-pkg` or `qrkey`** without verifying the adapter still works end-to-end.
