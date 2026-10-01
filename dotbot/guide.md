# DotBot guide

DotBots are small wheeled robots. A controller process reaches them, real or
simulated, and serves a REST API. For people and AI agents alike: `--help` on
any command is the truth for its flags; this page says what help cannot.

## Agents: read this first

Ask the user one question before anything else: **the simulator, or real
robots?** The simulator needs no hardware and is the default.

Safe to run at any time:
- `dotbot --help`, `dotbot <group> --help`, `dotbot guide`
- `dotbot run simulator --headless`, and any command against a simulator
- every `GET` on the API

Ask the user first, every time:
- `dotbot device flash ...` and `dotbot swarm flash ...` (writes firmware)
- `dotbot run controller` on real hardware, and any move of a real robot
- `dotbot swarm start`, `dotbot swarm stop`, `dotbot swarm reset`

Rules:
- On real robots, use only the addresses the user names, never ones you
  picked from a list or a scan.
- Stop everything: `curl -X DELETE localhost:8000/controller/dotbots/waypoints`
  stops every known robot where it stands. Direct drive stops by itself.
- Near people, keep `max_speed` at 300 mm/s or less. It caps waypoint
  driving only; `move_raw` is not limited by it.
- Always pass `--headless` and prefix `BROWSER=true`; never open a browser.
- Read the pose back from `GET /controller/dotbots` before saying a robot moved.
- Show the user every command you ran (a CLI line or a curl) to run themselves.

## 1. Start the simulator

```bash
BROWSER=true dotbot run simulator --headless
```

It stays in the foreground (run it in the background or a second terminal)
and serves five simulated DotBots on http://localhost:8000. `--robots 20`
starts 20; `--controller-http-port 8080` moves it off port 8000. List them:

```bash
curl -s localhost:8000/controller/dotbots
```

Each robot has an `address` (16 hex digits, e.g. `B0B0F00D33333333`) and a
`pose`: `x` and `y` in millimetres, `heading_deg` in degrees. `pose` is the
midpoint of the wheel axle, which is the point waypoints steer. `lh2_position`
is the Lighthouse photodiode, 53.5 mm ahead of the axle on a DotBot v3. Until
a robot has driven, `heading_source` is `none`: its heading and axle are
placeholders, so trust only `lh2_position`. A person can watch at
http://localhost:8000/console/ (the web console).

## 2. Move one robot

Use waypoints: the robot drives there on its own. Positions are mm in the site
frame (`GET /controller/site` gives its size, when it has one).

```bash
ADDR=B0B0F00D33333333
curl -X PUT localhost:8000/controller/dotbots/$ADDR/0/waypoints \
  -H 'content-type: application/json' \
  -d '{"threshold": 50, "waypoints": [{"x": 1200, "y": 500}]}'
```

The `0` in the path is `{application}`, the robot kind: 0 for a DotBot, 1 for
a SailBot. `threshold` is how close, in mm, counts as reached. While it drives,
`mode` is 1 (AUTO); on arrival `mode` returns to 0 and `waypoints_status` is 2.
Several robots at once: `PUT /controller/dotbots/waypoints` with
`{"threshold": 50, "dotbots": {"<address>": [{"x": 400, "y": 400}]}}`.

LED colour and cruise speed:

```bash
curl -X PUT localhost:8000/controller/dotbots/$ADDR/0/rgb_led \
  -H 'content-type: application/json' -d '{"red": 0, "green": 255, "blue": 0}'
curl -X PUT localhost:8000/controller/dotbots/$ADDR/0/max_speed \
  -H 'content-type: application/json' -d '{"max_speed_mm_s": 200}'
```

Stop one robot, or all of them without `?address=`:
`curl -X DELETE "localhost:8000/controller/dotbots/waypoints?address=$ADDR"`

`move_raw` drives the wheels directly (`left_y`, `right_y`: -100 to 100; a
robot at rest needs about 50 to start), but the robot stops about half a
second after the last command: a single curl moves it a short way and it
stops. Resend it every 0.1 s, as `dotbot run demo circle` does, or use
waypoints.

## 3. The live API

Ask the API, then read this for what it will not say. `/openapi.json` is the
full schema; Swagger is at http://localhost:8000/api (not `/docs`). Not in it:
units are mm and mm/s, `move_raw` stops about 0.5 s after the last command,
and `status` is 0 active, 1 stale (silent 3 s), 2 lost (silent 10 s, left out
of `GET /controller/dotbots` unless `?include_lost=true`); after 5 minutes of
silence a robot is forgotten (404). To watch instead of polling: the
WebSocket `/controller/ws/stream`.

## 4. Real hardware

Every step changes hardware: ask the user first. It needs a gateway board (an
nRF5340-DK), DotBot v3 robots and an MQTT broker.

```bash
dotbot config init --conn mqtts://broker.example:8883 --swarm-id 1234
dotbot fw fetch                                  # the pinned firmware releases
dotbot device flash mari-gateway --probe 10      # the gateway board
dotbot device flash swarmit-sandbox --probe 77   # each DotBot, one at a time
dotbot run gateway -p /dev/ttyACM0               # bridge the gateway to MQTT
dotbot swarm status                              # which robots have joined
dotbot swarm flash remote-control -ys            # the app the controller drives
BROWSER=true dotbot run controller --headless    # the same API as the simulator
```

`dotbot config show` prints the config in effect. `dotbot swarm stop` returns
every robot to its bootloader. Broker, swarm id and port are the user's: ask.

## 5. Examples

Packaged scenarios, each run against a controller or simulator on port 8000:

```bash
dotbot run demo --list                                # the built-in demos
dotbot run demo circle                                # drive one robot in a circle
python -m dotbot.examples.motions.motions -m square   # also circle, infinity, ...
```

The other scenarios need more setup: charging_station needs a site with a
field and a staging area (`dotbot config init` writes one), and labyrinth,
work_and_charge and minimum_naming_game each need their own
`dotbot run simulator --simulator-init-state <file>`. See the README beside
each in the installed `dotbot/examples/`.

## 6. When it does not work

- A robot moved briefly and stopped: that is `move_raw` ending about 0.5 s
  after the last command. Resend it faster, or use waypoints.
- No robots listed, or connection refused: no controller or simulator is
  running on that port.
- A 422 on waypoints: a point is outside the site (`GET /controller/site`),
  or the body is malformed; the response's `detail` says which.

## 7. Where next

Documentation: https://pydotbot.readthedocs.io. Every group has its own help:
`dotbot run --help`, `dotbot swarm --help`. `dotbot guide --install` installs
an agent skill that points coding agents at this guide.
