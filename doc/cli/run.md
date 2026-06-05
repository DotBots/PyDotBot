# `dotbot run` - host-side processes

`dotbot run` launches the things that run **on your computer**: the control
plane, the gateway bridge, a simulator, calibration, demos, and teleop
drivers. (`fw` / [`device`](device.md) / [`swarm`](swarm.md) are the things you
*manage*; `run` is the long-lived processes that talk to them.)

```bash
dotbot run --help        # the full list
```

| Subcommand | Launches |
|---|---|
| `controller` | Control plane: REST/WS API + web dashboard. The hub everything else talks to. |
| `gateway` | Host bridge: gateway firmware UART ↔ MQTT broker. |
| `simulator` | Standalone simulator (no hardware). |
| `lh2-calibration` | LH2 calibration on one cabled board (capture / apply); deployed DotBots use `swarm lh2-calibration`. |
| `demo` | Built-in research demos (qrkey phone bridge, …). |
| `keyboard` | Drive a DotBot from the keyboard. |
| `joystick` | Drive a DotBot from a joystick. |

## `controller` - the control plane + web UI

Connect to a swarm and serve the dashboard at `http://localhost:8000/PyDotBot/`.
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
| `--headless` | don't open the dashboard in a browser (it's still served) |
| `--csv-data-output` | record DotBot data to a CSV file |

Full options and the dashboard tour live in
[the controller guide](../guides/controller.md). See `dotbot run controller --help`.

## `gateway` - UART ↔ MQTT bridge

Runs wherever the gateway firmware is plugged in. With `--mqtt-url` it bridges
serial frames to the broker; without it, it just prints what it receives.

```bash
dotbot run gateway -m mqtts://argus.paris.inria.fr:8883 -p /dev/cu.usbmodem1234
dotbot run gateway                # autodetect port, print-only (no broker)
```

> **`run gateway` ≠ `device flash-mari-gateway`.** This is the *host process* that
> bridges a gateway board to MQTT. [`device flash-mari-gateway`](device.md) is the
> *firmware* you flash onto that board, once. Same word, different objects.

## `simulator` - standalone simulator

No hardware, no gateway. Exactly equivalent to `run controller --conn simulator`,
so it shares the controller's flags and serves the same dashboard.

```bash
dotbot run simulator
```

## `lh2-calibration` - capture & apply (cabled)

Lighthouse v2 calibration against a single serial-attached board. `collect`
opens a TUI to capture LH2 counts; `apply` writes the saved calibration out as
a C header. This is the cabled, bench path - for deployed DotBots, capture over
the air with [`swarm lh2-calibration`](swarm.md) instead.

```bash
dotbot run lh2-calibration collect
dotbot run lh2-calibration apply ./lh2_calibration.h
```

See [the cabled LH2 calibration guide](../guides/lh2-calibration-cabled.md). To
capture without a cable, or to push a saved calibration to the fleet over the
air, use [`swarm lh2-calibration`](swarm.md).

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
dotbot run joystick -j 0 -d 1234567890abcdef
```

See `dotbot run keyboard --help` / `dotbot run joystick --help` for the host,
port, and application (`dotbot`/`sailbot`) flags.
