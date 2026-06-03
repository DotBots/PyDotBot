```{toctree}
:hidden:
:maxdepth: 2
CLI <cli/index>
Python SDK <sdk/index>
Hardware <hardware/index>
Guides <guides/index>
Reference <reference/index>
```

```{admonition} Where do you want to start?
:class: tip

New here? DotBots are small wheeled robots you drive from your browser or your
own code - one bot, or a swarm of hundreds. Pick a starting point:

- **Try it with no hardware** - the simulator runs the full web UI with no bot
  or gateway needed: `dotbot run simulator -w`. Then explore the
  [web-UI guide](guides/controller.md).
- **Get one bot moving** - build and cable-flash a single DotBot and gateway,
  then drive it from the browser. See the [one-bot guide](guides/one-bot.md).
- **Run a swarm experiment** - provision and command many bots over the air.
  The swarm quickstart below is the main path; then see [`swarm`](cli/swarm.md)
  and [LH2 localization](guides/lh2-calibration.md).
- **Script it / collect data** - drive the swarm from your own code today over
  [REST / WebSocket](reference/rest.md) or [MQTT](reference/mqtt.md), and log
  runs with `dotbot run controller --csv-data-output`. (A higher-level
  [Python SDK](sdk/index.md) is planned.)
- **Extend the platform** - every command and flag is in the
  [CLI reference](cli/index.md); the firmware flows live under [`fw`](cli/fw.md)
  and [`device`](cli/device.md).
- **Before flashing hardware** - the simulator and driving an existing swarm
  need only Python; building and cable-flashing firmware also need SES and the
  nRF Command Line Tools (`nrfjprog`). See **Prerequisites** below before you start.
```

```{include} ../README.md
:relative-images:
```
