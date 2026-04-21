# Charging Station

This demo runs a charging-station scenario:
robots first form a queue, then move through charging and parking phases.
It works with real robots or with the simulator via the same controller API.
The simulator setup below is the default path for reproducibility.

## How to run (default: simulator)

### 1. Start the controller in simulator mode

```bash
dotbot-controller -a dotbot-simulator \
    --background-map dotbot/examples/charging_station/charging_station-2000x2000.png
```

Use `--simulator-init-state dotbot/examples/charging_station/charging_station_init_state.toml` to test with 10 robots.
The default map size should also be changed with `--map-size=4000x2000` and the
background map used above doesn't work anymore in that case.

### 2. Run the charging-station scenario

From the `PyDotBot/` root in a new terminal:

```bash
python -m dotbot.examples.charging_station.charging_station
```
