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

The web console opens in a browser tab automatically. Pass `--headless` to
suppress that (it's still served); browse to
<http://localhost:8000/console/> yourself (<http://localhost:8000/> redirects
there).

| Flag | What it does |
|---|---|
| `-n, --conn` | Connection: serial path, `mqtts://host:port`, or `simulator` |
| `-s, --swarm-id` | Swarm id in hex (required for MQTT, ignored otherwise) |
| `--headless` | Don't open the web UI in a browser (still served) |
| `--controller-http-port` | HTTP/REST port (default `8000`) |
| `--dotbot / --sailbot` | With `--conn simulator`: which robot to simulate |
| `--no-swarm-serve` | Don't start a local swarm server beside an MQTT connection (see below) |

See `dotbot run controller --help` for the full list (logging, CSV export,
background map, simulator init state).

With an MQTT connection the controller also starts a local swarm server
(`dotbot swarm serve --local` on port 8001), which is what shows the console
robots sitting in their bootloader and runs flashing, start and stop. One
already running there is reused, so a `dotbot swarm serve` in another
terminal keeps working, and the one the controller started stops with it.
The banner's `Swarmit server:` line says which happened.

`dotbot run simulator` is shorthand for `dotbot run controller --conn simulator` - try
the UI with no DotBot or gateway.

## Save your settings

Save your connection once instead of repeating flags:

```bash
# a site whose broker is this one, and your swarm id (writes ~/.dotbot/)
dotbot config init --conn mqtts://broker:8883 --swarm-id 1234

# the controller picks it up from any folder
BROWSER=true dotbot run controller --headless

# override the saved connection for one run (a simulator instead)
BROWSER=true dotbot run controller --conn simulator --headless
```

A flag beats a saved value. To keep the browser from opening every time,
`dotbot config set run.controller.headless true`. See the
[configuration reference](../reference/configuration.md) for the three files
and every key.

## The web UI

At <http://localhost:8000/console/> a map shows every DotBot the controller
sees. Select one to control it:

- **Joystick** - a virtual joystick drives the selected DotBot.
- **Waypoints** - set waypoints on the map for the selected DotBots to drive to.
- If you flashed Lighthouse 2 localization, DotBots report their `(x, y)` position
  on the map (see [LH2 calibration](lh2-calibration.md)).
- A DotBot's app reports its position and battery to the controller about
  twice a second. **Reports** says how that is going:

  | Reports | REST `status` | Meaning |
  |---|---|---|
  | Reporting | `0` active | heard within 3 s |
  | Late | `1` stale | silent 3 to 10 s: drawn faded, still sent commands |
  | Silent | `2` lost | silent over 10 s: hidden from the map unless **Silent robots** is ticked in the Layers tab |
  | No reports | absent | only swarmit knows it: in its bootloader, or running an app that does not report |

  A silent robot swarmit still hears stays on the map. The count beside LIVE
  (the console's own connection) in the top bar names the late and silent ones
  (see [how long a robot is kept](../reference/rest.md#how-long-a-robot-is-kept)).
- **List** and **Grid** (top right) show each robot. The list has a column
  per fact: sandbox state, reports and how long since the last one, battery,
  app, bootloader version (and the net core's when it differs), LH2
  calibration, position, heading and area; it sorts by any column, and
  **Columns** hides the ones you do not need. The grid's **Compact** cards show
  state, battery, where the robot is, its app and bootloader, and only what
  needs attention; **Full** cards add the address, reports, version digests,
  calibration and device type. The browser remembers the choice. Heading is
  drawn as on the map, a circle with a line toward where the robot faces,
  empty while it has reported none. **too old** marks a bootloader older than
  this controller's calibrations need (reflash `swarmit-sandbox`), and
  **differs** a robot holding another calibration than the controller serves.
  Hover a row, card or value for the rest.

## Firefox websockets note

If the web UI does not connect under Firefox, the WebSocket stream is likely
being blocked. Open `about:config` (Ctrl + L, then type it), find
`network.http.http2.websockets`, and set it to `false`.

## Next steps

- Flash DotBots and a gateway first - see [device flashing](../cli/device.md).
- Operate the whole fleet over the air - see [swarm](../cli/swarm.md).
