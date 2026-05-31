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
change it). Interactive OpenAPI docs — schemas, payloads, and a "try it out"
button — are served by the running app at:

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
| `GET` | `/controller/dotbots` | List connected DotBots |
| `GET` | `/controller/dotbots/{address}` | One DotBot's state |
| `GET` | `/controller/map_size` | Controller map size |
| `GET` | `/controller/background_map` | Background map image (base64) |
| `PUT` | `/controller/dotbots/{address}/{application}/move_raw` | Drive the motors |
| `PUT` | `/controller/dotbots/{address}/{application}/rgb_led` | Set the RGB LED |
| `PUT` | `/controller/dotbots/{address}/{application}/waypoints` | Set navigation waypoints |
| `DELETE` | `/controller/dotbots/{address}/positions` | Clear position history |

Two WebSocket endpoints push live updates: `/controller/ws/status` (state
stream) and `/controller/ws/dotbots` (send `move_raw` / `rgb_led` / `waypoints`
as JSON).

## Quick examples

Install [requests](https://pypi.org/project/requests/): `pip install requests`.

**List DotBots** — `address` identifies a bot; `status` is `0` active, `1`
inactive, `2` lost.

```py
import requests
print(requests.get("http://localhost:8000/controller/dotbots").json())
```

**Set the RGB LED** (`red`/`green`/`blue`, 0–255):

```py
import requests
addr = "9903ef26257feb31"   # from the list above
requests.put(
    f"http://localhost:8000/controller/dotbots/{addr}/0/rgb_led",
    json={"red": 255, "green": 0, "blue": 0},
)
```

**Drive the motors** — only `left_y` / `right_y` are used; values in `[-100,
100]`, and absolute values below ~50 won't overcome friction.

```py
import requests
addr = "9903ef26257feb31"
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
