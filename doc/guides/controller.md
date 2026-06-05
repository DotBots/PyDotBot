# Run the controller + web UI

The controller is the host-side control plane: it talks to your gateway (or a
simulator), exposes a REST + WebSocket API, and serves a web UI to drive your
DotBots.

## Start it

Point the controller at a connection and open the web UI:

```bash
# serial gateway plugged into your computer (no swarm-id needed)
dotbot run controller --conn /dev/ttyACM0

# a swarm over MQTT (swarm-id required - the broker carries many swarms)
dotbot run controller --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234

# no hardware at all - pure software simulator
dotbot run controller --conn simulator
```

`--conn` takes one string: a serial device path (`/dev/ttyACM0`, `COM3` on
Windows), an MQTT broker (`mqtts://host:port`), or `simulator`.

The dashboard opens in a browser tab automatically. Pass `--headless` to
suppress that (it's still served); browse to
<http://localhost:8000/PyDotBot> yourself.

| Flag | What it does |
|---|---|
| `-n, --conn` | Connection: serial path, `mqtts://host:port`, or `simulator` |
| `-s, --swarm-id` | Swarm id in hex (required for MQTT, ignored otherwise) |
| `--headless` | Don't open the web UI in a browser (still served) |
| `--controller-http-port` | HTTP/REST port (default `8000`) |
| `--config-path` | Path to a `.toml` config file |
| `--dotbot / --sailbot` | With `--conn simulator`: which robot to simulate |

See `dotbot run controller --help` for the full list (logging, CSV export, map
size, background map, simulator init state).

`dotbot run simulator` is shorthand for `dotbot run controller --conn simulator` - try
the UI with no DotBot or gateway.

## Use a config file

Save your connection once instead of repeating flags:

```bash
# save where to connect (writes ./dotbot.toml)
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234

# the controller picks it up automatically when run from here
dotbot run controller

# override the saved connection for one run (a simulator instead)
dotbot run controller --conn simulator
```

CLI flags override config-file values when both are given. See the
[configuration reference](../reference/configuration.md) for how the file is
discovered and the full schema.

## The web UI

At <http://localhost:8000/PyDotBot> the page lists every DotBot the controller
sees. Select one to control it:

- **Joystick** - a virtual joystick drives the selected DotBot.
- **RGB LED** - pick a color and the DotBot's LED follows.
- If you flashed Lighthouse 2 localization, DotBots report their `(x, y)` position
  on the map (see [LH2 calibration](lh2-calibration.md)).

## Firefox websockets note

If the web UI does not connect under Firefox, the WebSocket stream is likely
being blocked. Open `about:config` (Ctrl + L, then type it), find
`network.http.http2.websockets`, and set it to `false`.

## Next steps

- Flash DotBots and a gateway first - see [device flashing](../cli/device.md).
- Operate the whole fleet over the air - see [swarm](../cli/swarm.md).
