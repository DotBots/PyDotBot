# Motions

This example moves a single DotBot through a predefined motion: either a geometric shape
(via autonomous waypoint navigation) or a speed profile (via direct motor commands).

## Available motions

| Name          | Type       | Description                                      |
|---------------|------------|--------------------------------------------------|
| `square`      | waypoints  | Square path centred in the arena                 |
| `triangle`    | waypoints  | Equilateral triangle centred in the arena        |
| `circle`      | waypoints  | Circular path centred in the arena               |
| `infinity`    | waypoints  | Lemniscate (∞) path centred in the arena         |
| `sawtooth`    | waypoints  | Boustrophedon sawtooth sweep across the arena    |
| `speed_ramp`  | move\_raw  | Sinusoidal ramp from `-MAX_SPEED` to `+MAX_SPEED` |
| `speed_steps` | move\_raw  | Forward/backward motion stepping through discrete speed levels |
| `speed_swing` | move\_raw  | Alternating ±speed with increasing-then-decreasing magnitude |

## How to run (default: simulator)

### 1. Start the controller

```bash
dotbot-controller --config-path config_sample.toml -a dotbot-simulator
```

### 2. Run a motion

From the `PyDotBot/` root in a new terminal:

```bash
python -m dotbot.examples.motions.motions --motion <MOTION_NAME>
```

If `--address` is omitted, the script automatically picks the first available DotBot.

## Options

```
  -a, --address TEXT              DotBot address (hex).
  -m, --motion [square|triangle|circle|infinity|sawtooth|speed_ramp|speed_steps|speed_swing]
                                  Motion to execute.  [required]
  -n, --repeat INTEGER            Number of times to replay the motion.  [default: 1]
  --scale FLOAT                   Shape scale in mm.  [default: 400]
  --arena-size INTEGER            Arena size in mm (square arena).  [default: 2000]
  --num-points INTEGER            Number of waypoints for circle and infinity motions.  [default: 12]
  --waypoint-threshold INTEGER    Proximity threshold in mm to consider a waypoint reached.
                                  Ignored for raw motions.  [default: 100]
  --reverse                       Reverse the waypoint order. Ignored for raw motions.
  --duration FLOAT                Duration in seconds for move_raw motions.
                                  Ignored for waypoint motions.  [default: 10]
  --move-raw-interval FLOAT       Interval in seconds between move_raw commands.
                                  Ignored for waypoint motions.  [default: 0.1]
  --host TEXT                     Controller host.  [default: localhost]
  --port INTEGER                  Controller port.  [default: 8000]
```

## Example commands

```bash
# Run a circle once
python -m dotbot.examples.motions.motions -m circle

# Run the infinity shape 3 times on a specific robot
python -m dotbot.examples.motions.motions -m infinity -n 3 -a 0x1234abcd

# Run a square in reverse waypoint order
python -m dotbot.examples.motions.motions -m square --reverse

# Run a speed ramp for 20 seconds against a remote controller
python -m dotbot.examples.motions.motions -m speed_ramp --host 192.168.1.10 --duration 20

# Run the speed swing motion with a 50 ms command interval
python -m dotbot.examples.motions.motions -m speed_swing --move-raw-interval 0.05
```
