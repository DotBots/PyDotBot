# `dotbot run` - host-side processes

`dotbot run` launches the things that run **on your computer**: the control
plane, the gateway bridge, a simulator, LH2 and camera calibration, demos,
and teleop drivers. (`fw` / [`device`](device.md) / [`swarm`](swarm.md) are the things you
*manage*; `run` is the long-lived processes that talk to them.)

```bash
dotbot run --help        # the full list
```

| Subcommand | Launches |
|---|---|
| `controller` | Control plane: REST/WS API + web console. The hub everything else talks to. |
| `gateway` | Host bridge: gateway firmware UART ↔ MQTT broker. |
| `simulator` | Standalone simulator (no hardware). |
| `calibrate-lh2` | **Deprecated.** Cabled LH2 calibration on one board (capture / apply). Use [`swarm calibrate-lh2`](swarm.md) instead. |
| `calibrate-camera` | Register an overhead camera against four printed ArUco sheets (sheets / collect). |
| `demo` | Built-in research demos (qrkey phone bridge, …). |
| `keyboard` | Drive a DotBot from the keyboard. |
| `joystick` | Drive a DotBot from a joystick. |

## `controller` - the control plane + web console

Connect to a swarm and serve the console at `http://localhost:8000/console/`.
The console is one map-first UI for driving the fleet and, when a swarmit server
is reachable, orchestrating the testbed. `http://localhost:8000/` redirects
to it.
`--conn` is one discriminated string: `mqtts://host:port`, a serial path, or
`simulator`.

```bash
dotbot run controller --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234
dotbot run controller --conn /dev/ttyACM0
```

| Flag | Meaning |
|---|---|
| `-n/--conn` | `mqtts://host:port`, serial path, or `simulator` |
| `-s/--swarm-id` | hex swarm id - **required for MQTT**, ignored for serial/simulator |
| `--controller-http-host` | interface the API binds to (default `127.0.0.1`, loopback). Pass `0.0.0.0` to reach it from another machine - the API is unauthenticated and `/swarmit/*` reaches the swarmit server through it, so only on a network you trust. |
| `--headless` | don't open the console in a browser (it's still served) |
| `--csv-data-output` | record DotBot data to a CSV file. A registered camera also writes `<name>-camera.csv` beside it, with a `<name>-camera.toml` sidecar saying what the columns mean. |
| `--site` | the site the session works in: its frame, its areas and where its calibrations are looked up. Also `site` in dotbot.toml, or `DOTBOT_SITE`. |
| `--lh2-calibration` | lighthouse calibration the controller runs on: a file path, a `--tag` or an id prefix. Refused when it was made in another site. Also `[run.controller] lh2_calibration`; `[run.controller] lh2_calibration_max_age_days` (default 30) warns when it is older. |
| `--camera-calibration` | overhead camera to draw on the map: a file path, or an id prefix of one under `~/.dotbot/calibrations/<site>/`. Register one with `run calibrate-camera collect`. Also `[run.controller] camera_calibration` in dotbot.toml. |
| `--camera-detect` / `--no-camera-detect` | run the robot detector on that camera's frames (default on). Off serves the layer as a picture only: nothing detected, drawn, pushed or logged. Also `[run.controller] camera_detect` in dotbot.toml. |
| `--swarmit-url` | swarmit server behind the console's orchestration panel (default `http://localhost:8001`, matching `swarmit serve`). Also `[run.controller] swarmit_url` in dotbot.toml, or `DOTBOT_SWARMIT_URL`. |
| `--mrta-url` | MRTA mode server (dotbot-logistics) behind the console's MRTA toggle, proxied at `/mrta/*`. Unset by default - the console shows no MRTA control at all until this is set (typically `http://localhost:8002`, dotbot-logistics' own default port). Also `[run.controller] mrta_url` in dotbot.toml, or `DOTBOT_MRTA_URL`. |

Full options and the dashboard tour live in
[the controller guide](../guides/controller.md). See `dotbot run controller --help`.

## `gateway` - UART ↔ MQTT bridge

Runs wherever the gateway firmware is plugged in. With `--mqtt-url` it bridges
serial frames to the broker; without it, it just prints what it receives.

```bash
dotbot run gateway -m mqtts://argus.paris.inria.fr:8883 -p /dev/cu.usbmodem1234
dotbot run gateway                # autodetect port, print-only (no broker)
```

> **`run gateway` ≠ `device flash mari-gateway`.** This is the *host process* that
> bridges a gateway board to MQTT. [`device flash mari-gateway`](device.md) is the
> *firmware* you flash onto that board, once. Same word, different objects.

## `simulator` - standalone simulator

No hardware, no gateway. Exactly equivalent to `run controller --conn simulator`,
so it shares the controller's flags and serves the same console.

```bash
dotbot run simulator
dotbot run simulator --robots 500                  # a generated fleet
dotbot run simulator --robots 150 --area field+staging
dotbot run simulator --robots 500 --write-init-state fleet.toml
dotbot run simulator --simulator-init-state fleet.toml
```

`--robots N` places N robots 200 mm apart, all facing up, in a grid shaped
like and centred in `--area`, and refuses a count that does not fit: an area
holds one robot per 200 mm square. `--area` takes a name from the site's
areas, `x,y,w,h` in mm or a `+`-joined composite, and defaults to the site's
[field](../reference/configuration.md#area-roles) (a 2 x 2 m square when the
site declares nothing); it also places the robots a `--simulator-init-state`
file gives no position.
`[run.controller] simulator_area` sets it from the config.
`--write-init-state` saves that fleet as a file to edit and reuse with
`--simulator-init-state`.

## `calibrate-lh2` - capture & apply (cabled, deprecated)

> **Deprecated.** Use [`swarm calibrate-lh2`](swarm.md), which calibrates
> over the air with no cable and no firmware swap. This path stays for a
> single board on the bench, before a swarm exists.

Lighthouse v2 calibration against a single serial-attached board. `collect`
opens a TUI to capture LH2 counts; `apply` writes the saved calibration out as
a C header. This is the cabled, bench path - for deployed DotBots, capture over
the air with [`swarm calibrate-lh2`](swarm.md) instead.

```bash
dotbot run calibrate-lh2 collect
dotbot run calibrate-lh2 apply ./lh2_calibration.h
```

See [the cabled LH2 calibration guide](../guides/lh2-calibration-cabled.md). To
capture without a cable, or to push a saved calibration to the fleet over the
air, use [`swarm calibrate-lh2`](swarm.md).

## `calibrate-camera` - register an overhead camera

An overhead camera is registered against four printed ArUco sheets, one taped
inside each corner of the area it covers. `sheets` renders the pages; `collect`
finds the camera that sees them, reads them back and solves the homography from
image pixels into the site's frame. Both run on your own machine and nothing
here reaches a robot, which is why this sits under `run` beside
`calibrate-lh2`.

```bash
dotbot run calibrate-camera sheets --out ./sheets     # print these at 100 %
dotbot run calibrate-camera collect --area dev-corner
```

| Flag (`collect`) | Meaning |
|---|---|
| `--area` | the one area this camera covers; the four sheet positions come from its corners |
| `--site` | the site the area belongs to, and the directory the registration is saved under |
| `--camera` | skip the search: an OpenCV index, or a path (a `/dev/v4l/by-id/` symlink, or a recorded frame) |
| `--reads` | frames averaged; only a frame carrying all four markers counts |
| `--lens` | the lens mode the camera is set to, recorded in the file |

`collect` prints the id of what it wrote. Pass it to the controller to draw the
camera on the console map:

```bash
dotbot run controller --camera-calibration <id> --headless
```

Needs the calibration extra: `pip install pydotbot[calibrate]`.

## `demo` - built-in demos

```bash
dotbot run demo --list      # what's available
dotbot run demo qr          # qrkey phone bridge
```

## `keyboard` / `joystick` - teleop

Drive a DotBot live through a running controller (start one with
`run controller` first). Both default to `localhost:8000`; pass `-d` to target a
specific DotBot by hex address.

```bash
dotbot run keyboard
dotbot run joystick -j 0 -d 1234567890ABCDEF
```

See `dotbot run keyboard --help` / `dotbot run joystick --help` for the host,
port, and application (`dotbot`/`sailbot`) flags.
