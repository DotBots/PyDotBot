# Python SDK (preview)

```{admonition} Planned — not yet available
:class: warning

The Python **Swarm SDK** described on this page is a **design preview**, not
shipped code. None of the snippets below run today — they show the API we
intend to build. The imports (`from dotbot import Swarm`) and every method
(`Swarm.connect`, `Swarm.run`, `bot.move_to`, ...) are **aspirational**.

To script the swarm **today**, use the CLI: start a controller with
[`dotbot run controller`](../cli/run.md), then drive bots over its
[REST](../reference/rest.md) / [WebSocket](../reference/rest.md) surface
(or the [MQTT bridge](../reference/mqtt.md)).
```

## What it will be

The SDK will be a thin Python wrapper over a running controller's REST/WS
surface, so you write swarm logic in Python instead of hand-rolling HTTP and
asyncio. You start a controller once (`dotbot run controller`), then a script
connects to it and commands bots. The same script targets real hardware, the
simulator, or a remote testbed — the backend is chosen at run time, not in the
code.

## Intended API

All three snippets are **aspirational** — they will not run until the SDK ships.

**Connect and drive one bot** — connect to a local controller, grab a bot, set
its color, move it:

```python
from dotbot import Swarm

async with Swarm.connect() as swarm:        # defaults to http://localhost:8000
    bot = next(iter(swarm))
    bot.set_color(red=255)
    await bot.move_to(500, 500)
```

**Run an algorithm** — `Swarm.run()` handles argv parsing and `asyncio.run()`,
so a student writes only the algorithm body:

```python
from dotbot import Swarm

async def algorithm(swarm):
    for bot in swarm:
        bot.set_color(red=255)

if __name__ == "__main__":
    Swarm.run(algorithm)
```

**Switch backends without editing code** — the same script runs against the
local default, the simulator, or a remote class testbed, picked by a CLI flag:

```bash
python my_assignment.py                                   # local controller
python my_assignment.py --sim                             # simulator
python my_assignment.py --swarm-url http://classroom:8000 # shared testbed
```

## Until then

- Launch the control plane: [`dotbot run`](../cli/run.md).
- Talk to it directly: [REST / WebSocket reference](../reference/rest.md) and
  the [MQTT bridge](../reference/mqtt.md).
- New to the platform? Start at the [getting-started quickstarts](../index.md).
