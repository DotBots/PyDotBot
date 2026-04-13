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
| `speed_ramp`  | move\_raw  | Forward motion with a sinusoidal speed envelope  |
| `speed_steps` | move\_raw  | Forward/backward motion stepping through discrete speed levels |

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
  -m, --motion [square|triangle|circle|infinity|sawtooth|speed_ramp|speed_steps]
                                  Motion to execute.  [required]
  -n, --repeat INTEGER            Number of times to replay the motion.  [default: 1]
  --scale FLOAT                   Shape scale in mm.  [default: 400]
  --arena-size INTEGER            Arena size in mm (square arena).  [default: 2000]
  --waypoint-threshold INTEGER    Proximity threshold in mm to consider a waypoint reached.
                                  Ignored for raw motions.  [default: 100]
  --host TEXT                     Controller host.  [default: localhost]
  --port INTEGER                  Controller port.  [default: 8000]
```

## Example commands

```bash
# Run a circle once
python -m dotbot.examples.motions.motions -m circle

# Run the infinity shape 3 times on a specific robot
python -m dotbot.examples.motions.motions -m infinity -n 3 -a 0x1234abcd

# Run a speed ramp with a custom scale against a remote controller
python -m dotbot.examples.motions.motions -m speed_ramp --host 192.168.1.10 --scale 300
```
