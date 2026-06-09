# sdk_demo - simple swarm demos

A small set of self-contained demos built on the DotBot Swarm SDK. Each one is
deliberately simple, reads from the *live* fleet (no hardcoded arena), and is
meant to be tested in the simulator first and then run unchanged on the real
testbed.

## Run

Start a controller with a simulated fleet in one terminal:

```bash
dotbot run controller --conn simulator --dotbot --bots 67 --layout random -m 2500x2500 --headless
```

Open the dashboard at http://localhost:8000, then run any demo in another
terminal:

```bash
python -m dotbot.examples.sdk_demo.led_ripple
```

Point a demo at a different controller with `--swarm-url`:

```bash
python -m dotbot.examples.sdk_demo.led_ripple --swarm-url http://192.168.1.50:8000
```

Every demo stops cleanly on Ctrl-C (motors off, LEDs off).

## The demos

LED demos move nothing, so they are collision-free and the safest to run on
real hardware:

| Demo | What it does |
|------|--------------|
| `led_ripple` | a ring of light ripples out from the swarm centre (set `OUTWARD = False` for edge-first) |
| `led_sweep` | a rainbow gradient sweeps across the field, left to right |

Motion demos - test in the simulator first, then run on hardware with small
amplitudes:

| Demo | What it does | Collision risk |
|------|--------------|----------------|
| `wiggle` | every bot rocks side to side in place while a rainbow rolls across the fleet (`--loop` to repeat with a pause) | low (turns in place) |
| `spin` | every bot spins in place, then stops | low (turns in place) |
| `tiny_circle` | each bot traces a small circle around its start | low-medium (small swept disc) |
| `ripple_pulse` | the moving cousin of `led_ripple`: light + a small outward hop ripple out from the centre, then ease home | low-medium (small radial hop, returns home) |
| `march` | the whole fleet translates as a block: right, up, left, back | medium (formation moves; mind the walls) |
| `swarm_rotate` | the whole fleet rotates about its centroid | high (outer bots cross inner paths) |

Each demo has a few constants at the top (speed, radius, step, angle) - tune
those to your arena.

## Before running on the real testbed

1. **Test one bot first.** Drive a single bot's LED and a single bot's motion
   before unleashing the fleet, so you confirm the link end to end.
2. **Lead with the LED demos.** They never move a wheel - zero collision risk,
   and they read beautifully on a projector.
3. **Start small on motion.** Shrink `STEP` / `RADIUS` / `TOTAL_ANGLE` to match
   your real spacing, then grow them. `swarm_rotate` is the riskiest - keep the
   angle small or keep it to the simulator.
4. **Know your stop.** Ctrl-C ends a demo and sends a fleet stop. Keep a hand on
   it.
5. **Mind the downlink budget.** The LED demos update only the bots that change
   each step. `spin` re-sends to the whole fleet on a timer; if it stutters with
   67 real bots, raise `RESEND` or run it on a subset.

## Notes

- All geometry (centre, rings, bearings) is computed from live positions, so the
  demos work the same in the simulator and on the testbed, whatever the arena
  size.
- Motion uses `move_to` / `follow` (the primary waypoint primitives); `spin`
  uses `move_raw` because an in-place turn has no target position.
