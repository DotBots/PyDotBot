# Run the controller + web UI

The controller is the host-side control plane: it talks to your gateway (or a
simulator), exposes a REST + WebSocket API, and serves a web UI to drive your
robots.

## Start it

Point the controller at a connection and open the web UI:

```bash
# serial gateway plugged into your computer (no swarm-id needed)
dotbot run controller --conn /dev/ttyACM0 -w

# a swarm over MQTT (swarm-id required — the broker carries many swarms)
dotbot run controller --conn mqtts://argus.paris.inria.fr:8883 --swarm-id 1234 -w

# no hardware at all — pure software simulator
dotbot run controller --conn simulator -w
```

`--conn` takes one string: a serial device path (`/dev/ttyACM0`, `COM3` on
Windows), an MQTT broker (`mqtts://host:port`), or `simulator`.

`-w` / `--webbrowser` opens a tab automatically. Otherwise browse to
<http://localhost:8000/PyDotBot> yourself.

| Flag | What it does |
|---|---|
| `-n, --conn` | Connection: serial path, `mqtts://host:port`, or `simulator` |
| `-s, --swarm-id` | Swarm id in hex (required for MQTT, ignored otherwise) |
| `-w, --webbrowser` | Open the web UI automatically |
| `--controller-http-port` | HTTP/REST port (default `8000`) |
| `--config-path` | Path to a `.toml` config file |
| `--dotbot / --sailbot` | With `--conn simulator`: which robot to simulate |

See `dotbot run controller --help` for the full list (logging, CSV export, map
size, background map, simulator init state).

`dotbot run simulator` is shorthand for `dotbot run controller --conn simulator` — try
the UI with no robot or gateway.

## Use a config file

Keep your connection settings in a TOML file instead of repeating flags:

```bash
# use settings from the config file
dotbot run controller --config-path swarm-config.toml

# use the config file but override the connection (run a simulator instead)
dotbot run controller --config-path swarm-config.toml --conn simulator
```

CLI flags override config-file values when both are given.

## The web UI

At <http://localhost:8000/PyDotBot> the page lists every DotBot the controller
sees. Select one to control it:

- **Joystick** — a virtual joystick drives the selected bot.
- **RGB LED** — pick a color and the bot's LED follows.
- If you flashed Lighthouse 2 localization, bots report their `(x, y)` position
  on the map (see [LH2 calibration](lh2-calibration.md)).

## Firefox websockets note

If the web UI does not connect under Firefox, the WebSocket stream is likely
being blocked. Open `about:config` (Ctrl + L, then type it), find
`network.http.http2.websockets`, and set it to `false`.

## Next steps

- Flash robots and a gateway first — see [device flashing](../cli/device.md).
- Operate the whole fleet over the air — see [swarm](../cli/swarm.md).
