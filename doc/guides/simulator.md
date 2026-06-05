# Try it in the simulator

The simulator runs the **full controller and web UI with no hardware** - no
DotBot, no gateway, no radio. It's the fastest way to see DotBot work, and
because it exposes the exact same REST/WebSocket API as the real controller, code
you write against the simulator runs unchanged against real DotBots.

## Start it

```bash
dotbot run simulator
```

This opens the web UI at <http://localhost:8000/PyDotBot/> driving a simulated
swarm. `dotbot run simulator` is shorthand for
`dotbot run controller --conn simulator`, so everything in the
[controller + web UI guide](controller.md) applies. Drive the DotBots from the
joystick and watch them on the map.

## Drive one DotBot in a circle

The simplest demo - it grabs the first DotBot the controller sees and drives it
in a circle. With the simulator running, in a second terminal:

```bash
dotbot run demo circle
```

## Drive it from your own code

That demo is ~15 lines talking to the controller's REST API over
[`requests`](https://pypi.org/project/requests/) (bundled with pydotbot) - here
is the whole thing, a template for your own scripts:

```python
import requests, time

BASE = "http://localhost:8000"
bot = requests.get(f"{BASE}/controller/dotbots").json()[0]["address"]

# roll in a circle for ~5 s - left_y and right_y are the two wheel speeds
for _ in range(50):
    requests.put(f"{BASE}/controller/dotbots/{bot}/0/move_raw",
                 json={"left_x": 0, "left_y": 60, "right_x": 0, "right_y": 30})
    time.sleep(0.1)
requests.put(f"{BASE}/controller/dotbots/{bot}/0/move_raw",
             json={"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0})
```

The full surface - every endpoint, the live WebSocket stream, and CSV data
logging - is in the [REST / WebSocket reference](../reference/rest.md) (or the
[MQTT bridge](../reference/mqtt.md)). A higher-level Python SDK is planned; today
you talk to the controller over REST/WebSocket/MQTT.

## More examples

```bash
dotbot run demo --list   # what's available
dotbot run demo qr       # phone-as-joystick over QrKey
```

Richer multi-DotBot scenarios - work-and-charge, charging-station, labyrinth, the
naming game, motion shapes - live in `dotbot/examples/`, each with its own
README and a simulator init state. They drive the controller over the same
REST/WebSocket API shown above, so they run against the simulator or real
hardware unchanged.
