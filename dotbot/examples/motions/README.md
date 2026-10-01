# Motions

This example moves a single DotBot through a predefined motion: either a geometric shape
(via autonomous waypoint navigation) or a speed profile (via direct motor commands).

## Available motions

| Name          | Type       | Description                                      |
|---------------|------------|--------------------------------------------------|
| `square`      | waypoints  | Square path centred in the field                 |
| `triangle`    | waypoints  | Equilateral triangle centred in the field        |
| `circle`      | waypoints  | Circular path centred in the field               |
| `infinity`    | waypoints  | Lemniscate (∞) path centred in the field         |
| `sawtooth`    | waypoints  | Boustrophedon sawtooth sweep across the field    |
| `speed_ramp`  | move\_raw  | Sinusoidal ramp from `-MAX_SPEED` to `+MAX_SPEED` |
| `speed_steps` | move\_raw  | Forward/backward motion stepping through discrete speed levels |
| `speed_swing` | move\_raw  | Alternating ±speed with increasing-then-decreasing magnitude |

## How to run (default: simulator)

### 1. Start the simulator

Give yourself a default site (a 2 x 2 m field), then start the simulator; it
opens the console in your browser:

```bash
dotbot config init
dotbot run simulator
```

### 2. Run a motion

From the `PyDotBot/` root in a new terminal:

```bash
python -m dotbot.examples.motions.motions --motion <MOTION_NAME>
```

If `--address` is omitted, the script automatically picks the first available DotBot.
Shapes are centred in the controller's field; `--area` picks another area.

## Options

```
  -a, --address TEXT              DotBot address (hex).
  -m, --motion [square|triangle|circle|infinity|sawtooth|speed_ramp|speed_steps|speed_swing]
                                  Motion to execute.  [required]
  -n, --repeat INTEGER            Number of times to replay the motion.  [default: 1]
  --scale FLOAT                   Shape scale in mm.  [default: 400]
  --area TEXT                     Area to centre the shapes in: a name, a `+`-joined
                                  composite or x,y,w,h in mm. Defaults to the
                                  controller's field.
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
