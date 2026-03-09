# Charging Station

This demo runs a charging-station scenario:
robots first form a queue, then move through charging and parking phases.
It works with real robots or with the simulator via the same controller API.
The simulator setup below is the default path for reproducibility.

## How to run (default: simulator)

### 1. Specify the initial state

Set `simulator_init_state_path` in `config_sample.toml` to:

```toml
simulator_init_state_path = "dotbot/examples/charging_station/charging_station_init_state.toml"
```

### 2. Start the controller in simulator mode

```bash
python -m dotbot.controller_app --config-path config_sample.toml -a dotbot-simulator
```

### 3. Run the charging-station scenario

From the `PyDotBot/` root in a new terminal:

```bash
python -m dotbot.examples.charging_station.charging_station
```
