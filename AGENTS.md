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

- **Pushed** - `/controller/ws/stream`, server to client (`dotbot/stream.py`).
  A `hello`, a `snapshot` of the fleet in parts of 100 robots, then `delta`
  frames whose per-robot patches are RFC 7396 merge patches over the REST
  object (plus `trail_append` / `trail_reset`), and `event` frames
  (`robot_models`, `calibration_session`, `camera_detection`). The client answers each frame
  with `{"ack": seq}`; one that never acks is served at 1 Hz, which keeps
  `websocat` usable. Query: `hz` (1-20, default 10), `trail` (points per
  robot, default 0), `since` + `run` to resume. Each client holds a cursor
  into the controller's per-field revisions, not a message queue, so a slow
  client gets fewer, larger frames; no ack for 15 s closes it. The console
  runs on this.
- **Polled** - `GET /controller/dotbots`. What the Python examples use when they
  batch waypoints and wait for "done". `?trail=N` adds the newest N trail
  points (default none). On the unfiltered list, `X-Controller-Seq` /
  `X-Controller-Run` name the state the body reflects, so a stream client can
  resume from it; a single robot or a filtered list carries neither.

**A robot's `pose` is four numbers, not its body**: `x`, `y` (the axle
midpoint, to 0.1 mm), `heading_deg` and `heading_source`. The body is the
same for every robot of one `model`, so it is sent once: the `robot_models`
event (with every snapshot) and `GET /controller/robot_models` give each
model's shape with its axle at the origin facing 0 degrees, and a client
draws a robot by turning that shape by `heading_deg`, `(x cos - y sin,
x sin + y cos)`, then adding the axle. That is what keeps a moving robot's
patch near 160 bytes. For a human with curl, `?body=1` on
`GET /controller/dotbots[/{address}]` adds each robot's expanded `body`.
`/controller/device_poses` is separate: a headingless body per swarmit
device type, photodiode at the origin, for robots only swarmit has located.

Trails live in `dotbot/trail.py` as per-robot arrays (seq, x, y), not
models; models and JSON values are built only when a trail is read.

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
dotbot run simulator --robots 500 # a generated fleet; see dotbot/examples/simulator_fleet/
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
pytest -m scenario --no-cov        # a few seconds; add -k to pick one
```

They run on a stepped clock (`DotBotSimulatorCommunicationInterface.step()`,
harness in `dotbot/tests/scenario_harness.py`): fixed seeds, no sleeps, no
browser, no network port. They validate the simulator and the controller
together, **not hardware**: the simulator runs the firmware's control core
(`dotbot/sim/`, DotBot-libs `drv/dotbot_control` built to WebAssembly) on a
modelled body, so a green run says nothing about a real robot's motors or
lighthouse.

### Backend benchmark

`utils/perf/bench_controller.py` starts a real headless controller per fleet
size (`-n`, default 1 10 50 100 200) and measures its CPU, RSS, event-loop
lag, stream rate, bandwidth and update age at K acking clients, snapshot
size, and REST latency and size of
`GET /controller/dotbots` and `PUT .../waypoints`. Mode `sim` runs the
simulator in the controller, as `dotbot run simulator` does, and mode `mari`
the same with every robot joined to the simulated Mari network, advertising
at its firmware's joined rate; mode `synth` feeds 2 Hz advertisements per
robot through a gateway adapter, so the controller is measured without the
simulator. Linux only; about 20 s a run.
The synthetic advertisements are built in a separate feeder process, so the
controller's process only parses them; `--feeder thread` builds them inside
it, where they contend with the event loop for the GIL.

```bash
python utils/perf/bench_controller.py --out perf.json            # full sweep
python utils/perf/bench_controller.py -n 10 100 --clients 1 --modes synth
python utils/perf/bench_controller.py --modes synth --trail 1000  # full trails
```

`--trail` starts each robot with that many points of trail, the steady state
of a fleet that has driven for a while. `--stall` adds a stream client that
acks once then stops reading, and `--slow` one that takes 20 ms per frame.

It records figures and applies no thresholds; each run is one flat JSON
record, so a CI trend or a limit can be keyed on its fields.

CI: `.github/workflows/continuous-integration.yml` — `tox` on Linux/macOS/Windows (Py 3.11/3.12, Node 18/20).

## Cross-repo dependencies

- **`qrkey`** — `pyproject.toml`; `dotbot/examples/qrkey_demo/`
- **`marilib`** — `pyproject.toml:48` (`marilib-pkg`); imported in `dotbot/adapter.py` (MarilibCloud, MarilibEdge, MQTT/Serial adapters, MariFrame). **Tight coupling.**
- **`PyDotBot-utils`** — `pyproject.toml`
- **`DotBot-libs`** — `dotbot/sim/dotbot_control.wasm` is its `drv/dotbot_control` built with `make wasm`, pinned by commit and sha256 in `dotbot/sim/dotbot_control.json`
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
