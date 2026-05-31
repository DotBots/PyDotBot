# The `dotbot` CLI

```{toctree}
:hidden:
fw
device
swarm
run
```

One CLI for the whole DotBot workflow: build firmware, flash one board, drive a
fleet over the air, and launch the host-side processes that tie it together —
from one bot to a thousand.

```bash
dotbot --help
```

## The mental model: three nouns + one verb

Everything in `dotbot` lives under four namespaces. Three name a **thing you
manage** at a different scale; one names the **host processes you launch**.

| Namespace | What it is | Reach for it when… |
|---|---|---|
| [`fw`](fw.md) | Firmware **artifacts** — build / fetch / list. No hardware. | You want a `.hex`/`.bin` to flash later, or to see what builds. |
| [`device`](device.md) | **One board** on a cable. Flash an app/role, read its info. | A DotBot or DK is plugged into your USB port right now. |
| [`swarm`](swarm.md) | The **fleet**, over the air. Status, OTA flash, start/stop, monitor. | You're driving many provisioned bots through the gateway. |
| [`run`](run.md) | **Host processes** you start on your computer. | You need the controller, gateway bridge, simulator, demos, or teleop. |

Read it as a sentence: you **`fw`** an artifact, **`device`**-flash it onto one
board, **`swarm`**-flash it across the fleet, and **`run`** the host processes
that talk to them.

```bash
dotbot fw     --help   # firmware artifacts (no hardware)
dotbot device --help   # one cabled board
dotbot swarm  --help   # the fleet, over the air
dotbot run    --help   # host-side processes
```

## Which one do I want?

```text
Do I have hardware?
├── No  ─────────────────────────► fw    (build/fetch artifacts, sim under run)
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
  `fw artifacts --sandbox` builds TrustZone apps (`.bin`) — the payload `swarm`
  flashes over the air.
- **Same word, different object.** `dotbot device flash-gateway` flashes
  *firmware onto a board*; `dotbot run gateway` starts the *host bridge
  process*. They are not the same thing.
- **A DotBot v3 has an on-board programmer.** Normal flashing over USB-C needs
  no external probe — a separate J-Link is only for
  `dotbot device flash-programmer`.

## Next

- [`fw`](fw.md) — build, fetch, and list firmware artifacts.
- [`device`](device.md) — flash and inspect one cabled board.
- [`swarm`](swarm.md) — run experiments across the fleet.
- [`run`](run.md) — launch the controller, gateway bridge, simulator, and demos.

Two end-to-end walkthroughs put these together: [build and flash one
board](device.md), and [operate a swarm over the air](swarm.md).
