# The `dotbot` CLI

```{toctree}
:hidden:
fw
device
swarm
run
```

One CLI for the whole DotBot workflow: build firmware, flash one board, control a
whole swarm, and launch the host-side processes that tie it together -
from one bot to a thousand.

```bash
dotbot --help
```

## The four commands

`dotbot` has four top-level commands - pick by what you're doing right now:

| Command | What it does | Reach for it when… |
|---|---|---|
| [`fw`](fw.md) | Build, fetch, and list firmware files. No hardware needed. | You want a `.hex`/`.bin` to flash later, or to see what builds. |
| [`device`](device.md) | Flash one cabled board and read its info. | A DotBot or DK is plugged into your USB port right now. |
| [`swarm`](swarm.md) | Drive the whole fleet over the air - status, OTA flash, start/stop, monitor. | You're operating many provisioned bots through a gateway. |
| [`run`](run.md) | Start host processes on your computer - controller, gateway bridge, simulator, demos, teleop. | You need the web UI, a gateway bridge, the simulator, or a demo. |

## Which one do I want?

```text
Do I have hardware?
├── No  ─────────────────────────► fw    (build/fetch artifacts, simulator under run)
└── Yes
    ├── One board on a cable ─────► device (flash app/role, read info)
    └── A fleet over the air ─────► swarm  (status, OTA flash, start/stop)

Need a process running on my computer (UI, gateway bridge, demo)? ─► run
```

A few signposts so the namespaces don't blur together:

- **`fw` never touches hardware.** It only produces or lists artifacts in
  `./artifacts/`. Flashing always happens under `device` (cabled) or `swarm`
  (OTA).
- **Bare vs. sandbox artifacts.** `fw` builds bare apps (`.hex`) by default;
  `fw artifacts --sandbox` builds TrustZone apps (`.bin`) - the payload `swarm`
  flashes over the air.
- **Same word, different object.** `dotbot device flash-mari-gateway` flashes
  *firmware onto a board*; `dotbot run gateway` starts the *host bridge
  process*. They are not the same thing.
- **A DotBot v3 has an on-board programmer.** Normal flashing over USB-C needs
  no external probe - a separate J-Link is only for
  `dotbot device flash-programmer`.

## Next

- [`fw`](fw.md) - build, fetch, and list firmware artifacts.
- [`device`](device.md) - flash and inspect one cabled board.
- [`swarm`](swarm.md) - run experiments across the fleet.
- [`run`](run.md) - launch the controller, gateway bridge, simulator, and demos.

Two end-to-end walkthroughs put these together: [build and flash one
board](device.md), and [operate a swarm over the air](swarm.md).
