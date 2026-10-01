# REST API

`dotbot run controller` exposes a FastAPI REST server for reading DotBot state
and sending commands. The React web UI and the [MQTT](mqtt.md) bridge use the
same controller; REST is the simplest way to script the swarm from your own
code.

## Where it lives

Start a controller (see [`dotbot run`](../cli/run.md)):

```bash
dotbot run controller --conn /dev/ttyACM0          # serial gateway
dotbot run controller --conn mqtts://broker:8883 --swarm-id 1234   # over MQTT
```

The server listens on **port 8000** by default (`--controller-http-port` to
change it). Interactive OpenAPI docs - schemas, payloads, and a "try it out"
button - are served by the running app at:

```
http://localhost:8000/api
```

```{image} ../_static/images/pydotbot-ui-openapi.png
:alt: OpenAPI UI
:width: 700px
:align: center
```

That page is the authoritative, version-matched reference. The table below is a
quick map; treat `/api` as the source of truth.

## Endpoints

All paths are under `http://localhost:8000`. `{address}` is the 8-byte hex
DotBot id; `{application}` is `0` (DotBot) or `1` (SailBot).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/controller/dotbots` | List the DotBots heard from; lost ones only with `?include_lost=true` (see [how long a robot is kept](#how-long-a-robot-is-kept)) |
| `GET` | `/controller/dotbots/{address}` | One DotBot's state |
| `GET` | `/controller/map_size` | Controller map size |
| `GET` | `/controller/background_map` | Background map image (base64) |
| `PUT` | `/controller/dotbots/{address}/{application}/move_raw` | Drive the motors |
| `PUT` | `/controller/dotbots/{address}/{application}/wheel_velocity` | Set each wheel's speed: `left_mm_s` / `right_mm_s`, in mm/s, within ±700. Only the sandbox `dotbot` firmware app acts on it (other apps ignore it), and it stops the wheels about 500 ms after the last command, so resend faster than 2 Hz |
| `PUT` | `/controller/dotbots/{address}/{application}/rgb_led` | Set the RGB LED |
| `PUT` | `/controller/dotbots/{address}/{application}/waypoints` | Set navigation waypoints |
| `PUT` | `/controller/dotbots/waypoints` | Set several DotBots' waypoints at once, one batch per address |
| `DELETE` | `/controller/dotbots/waypoints` | Stop the DotBots named by `?address=`, or all of them |
| `DELETE` | `/controller/dotbots/{address}/positions` | Clear the trail |
| `GET` | `/controller/robot_models` | Each robot model's body, axle at the origin, facing 0 degrees |
| `GET` | `/controller/cameras` | Registered overhead cameras currently serving a layer |
| `GET` | `/controller/cameras/{area}/stream` | That area's camera, warped into its raster, as `multipart/x-mixed-replace` JPEG |

Two WebSocket endpoints: `/controller/ws/stream` pushes the fleet's state (a
snapshot, then merge-patch deltas, each answered with `{"ack": seq}`), and
`/controller/ws/dotbots` takes `move_raw` / `rgb_led` / `waypoints` commands as
JSON.

## How long a robot is kept

A DotBot advertises about twice a second. Its `status` says how long ago the
controller last heard from it, and `last_seen` says exactly when (Unix
seconds):

| `status` | Silent for | `GET /controller/dotbots` | Commands |
|---|---|---|---|
| `0` active | under 3 s | listed | accepted |
| `1` stale | 3 to 10 s | listed | accepted, sent in case it hears them |
| `2` lost | 10 s to 5 min | listed only with `?include_lost=true` or `?status=2` | accepted |
| forgotten | over 5 min | gone | `404`, as for an address never seen |

A robot that advertises again is active at once. A forgotten one comes back
as a new robot: its trail and the commands the controller was still resending
to it are gone, and anything set on it from here, such as an LED colour, has
to be set again.

`GET /controller/dotbots/{address}` still answers for a lost robot. The stream
carries every robot the controller holds, lost ones included, with each
`status` change as a patch; a forgotten robot arrives as `null` in a delta
(`{"robots": {"<address>": null}}`), which in RFC 7396 removes it. Only
`GET /controller/dotbots?include_lost=true`, with no other filter, carries the
`X-Controller-Seq` / `X-Controller-Run` headers a stream client can resume from,
since only that list matches what the stream holds.

The thresholds are `[run.controller] stale_after_s`, `lost_after_s` and
`forget_after_s` in the [configuration](configuration.md) (`forget_after_s = 0`
never forgets).

## Quick examples

Install [requests](https://pypi.org/project/requests/): `pip install requests`.

**List DotBots** - `address` identifies a bot; `status` is `0` active, `1`
stale, `2` lost (lost ones are left out unless you add `?include_lost=true`).

```py
import requests
print(requests.get("http://localhost:8000/controller/dotbots").json())
```

**Set the RGB LED** (`red`/`green`/`blue`, 0–255):

```py
import requests
addr = "9903EF26257FEB31"  # uppercase; the address is matched case-sensitively
requests.put(
    f"http://localhost:8000/controller/dotbots/{addr}/0/rgb_led",
    json={"red": 255, "green": 0, "blue": 0},
)
```

**Drive the motors** - only `left_y` / `right_y` are used; values in `[-100,
100]`, and absolute values below ~50 won't overcome friction.

```py
import requests
addr = "9903EF26257FEB31"
requests.put(
    f"http://localhost:8000/controller/dotbots/{addr}/0/move_raw",
    json={"left_x": 0, "left_y": 60, "right_x": 0, "right_y": 60},
)
```

```{admonition} Motors stop after 200 ms
:class: info
The firmware halts the motors if no `move_raw` arrives within 200 ms. To keep a
DotBot moving, send commands in a loop with a delay under 200 ms.
```
