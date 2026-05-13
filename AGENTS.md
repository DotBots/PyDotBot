# PyDotBot

## Purpose

Python control plane for DotBots. Serial / cloud / edge adapters talk to a DotBot gateway (often via Mari → marilib); a FastAPI REST + WebSocket server exposes state; a React web UI provides joystick/map/lighthouse-position visualization. Also ships CLI tools (`dotbot-controller`, `dotbot-edge-gateway`, `dotbot-keyboard`, `dotbot-joystick`, `dotbot-qrkey`) and DotBot/SailBot simulators.

This is the most active repo in the ecosystem (187 commits in last 90 days as of 2026-05-05).

## Tech stack

- **Backend**: Python ≥3.7, FastAPI + uvicorn, click, gmqtt + qrkey for MQTT, pyserial, structlog, pygame, pynput, numpy
- **Frontend**: React 18 + TypeScript, Vite, Bootstrap 5, react-leaflet, MQTT.js, vitest + @testing-library
- **Build**: `hatchling` (PEP 517) with custom sdist hook that bundles the frontend; `tox` for orchestration; `pre-commit`; `ruff` / `isort` / `black`
- **Package**: pip (PyPI as `pydotbot`); npm for frontend

## Entry points

- `dotbot/controller_app.py` — main CLI (`dotbot-controller`); wires adapters and settings
- `dotbot/controller.py:1` — 737-line `Controller` class; central object
- `dotbot/frontend/src/App.tsx` — React UI root

## Build / run / test

```bash
pip install pydotbot                         # or `pip install -e .`
dotbot-controller --help
# Other entry points: dotbot-edge-gateway, dotbot-keyboard, dotbot-joystick, dotbot-qrkey

# Tests / lint / build
tox                                          # envs: tests, check, cli, web=npm run lint, doc

# Frontend
cd dotbot/frontend && npm install
npm start                                    # dev
npm run build
npm test                                     # vitest — NOT currently run in CI
```

CI: `.github/workflows/continuous-integration.yml` — `tox` on Linux/macOS/Windows (Py 3.11/3.12, Node 18/20). Also a CMake build of `utils/control_loop` against `DotBots/DotBot-libs`.

## Cross-repo dependencies

- **`qrkey`** — `pyproject.toml:42`; `dotbot/qrkey.py`; frontend `package.json` (`qrkey ^0.12.0`)
- **`marilib`** — `pyproject.toml:48` (`marilib-pkg`); imported in `dotbot/adapter.py` (MarilibCloud, MarilibEdge, MQTT/Serial adapters, MariFrame). **Tight coupling.**
- **`PyDotBot-utils`** — `pyproject.toml:49`; used by `utils/hooks/sdist.py:build_frontend`
- **`DotBot-libs`** — checked out in CI to build `utils/control_loop` C library
- **`DotBot-firmware`** — referenced only in README (flashing instructions); no code dep
- No references to: `swarmit`, `dotbot-lh2-calibration`, `dotbot-provision`

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
- **Frontend has parallel `*.test.tsx` files** for every component, but CI only runs `npm run lint` (not `vitest`) — frontend tests are written but not executed.
- Maintainer (`aabadie`) is leaving summer 2026 — onboarding ergonomics matter here.

## Branch policy

- Default: `main`
- Stale branches `132-*`, `141-*`, `main-old`, `other-os-compatibility` are candidates for deletion (or revival via PR if salvageable).
- New work: feature branches off `main`, PRs even for solo work.

## Agent-task ideas

- **Wire vitest into CI** (the tests already exist; the wiring is missing).
- **Audit `.env` for secrets** and replace with `.env.example`. Add `.env` to `.gitignore`.
- **Remove dead `pin_code` tox env** and the missing `dotbot/pin_code_ui` reference.
- **Investigate stale LH2 branches** (`#132`, `#141`): are they worth rebasing or are they superseded?
- **Extract `dotbot/examples/`** to a separate `pydotbot-examples` package, or move into a `research/` subdir excluded from the wheel.
- **Decompose `controller.py`** (737-line class) into smaller modules — the monolith makes onboarding harder.
- **Migrate `dotbot/protocol.py`** (the outdated remote-control mirror) to a shared package; coordinate with `DotBot-libs/drv/protocol.h`.
- **Add type hints + mypy** to the backend (currently typed inconsistently).

## Don't

- **Don't push to `main` without a PR** — this is the hottest repo and traceability matters.
- **Don't break the FastAPI REST/WebSocket contract** without bumping the major version — external scripts and the React UI depend on the surface.
- **Don't refactor `dotbot/adapter.py`** in isolation; coordinate with `marilib` and `qrkey`.
- **Don't bump `marilib-pkg` or `qrkey`** without verifying the adapter still works end-to-end.
