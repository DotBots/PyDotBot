# Swarm SDK examples

Small, self-contained examples built on the DotBot Swarm SDK
(`from dotbot.sdk import Swarm`). Each is a few lines and produces a clear visual
on the dashboard - good for a first look at the SDK and for demos.

## Run

Start a simulator (it opens the web dashboard at <http://localhost:8000>):

```bash
dotbot run simulator
```

Then run any example against it (watch the bots move and change colour on the
dashboard):

```bash
python dotbot/examples/sdk/square.py
python dotbot/examples/sdk/circle_formation.py
# point at a remote controller instead of localhost:
python dotbot/examples/sdk/square.py --swarm-url http://HOST:8000
```

## The examples

Single bot:

- `square.py` - one bot walks a square.
- `shuttle.py` - one bot shuttles between two points, changing colour each leg.

Whole swarm:

- `square_formation.py` - the fleet forms a square, one bot per corner.
- `circle_formation.py` - the fleet spreads out evenly onto a circle.
- `rainbow.py` - a rolling colour show across the fleet (no motion).
- `pulse.py` - the fleet "breathes", expanding and contracting on a ring.

`tour.py` is a short guided tour that combines several SDK features (fleet
colour, live events, concurrent moves).
