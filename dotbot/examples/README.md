# DotBot Examples

This directory contains example scenarios for DotBots.
Examples can run against either real robots or the simulator, using the same controller APIs.
The simulator setup is documented as the default path because it is the most common way to reproduce experiments.
Each scenario has its own folder with dedicated instructions, initial states, and run commands.

## Available scenarios

- `minimum_naming_game/`: naming game examples (with and without motion)
- `work_and_charge/`: work/charge alternation scenario
- `charging_station/`: queue-and-charge scenario
- `motions/`: move a single DotBot through predefined shapes or speed profiles

We also provide a stop.py helper script to halt the simulator (without needing to stop robots via SwarmIT).

## Common usage pattern (default: simulator)

1. Pick a scenario and read its local `README.md`.
2. Set `simulator_init_state_path` in `config_sample.toml` as described by that scenario.
3. Start the controller in simulator mode:

```bash
python -m dotbot.controller_app --config-path config_sample.toml -a dotbot-simulator
```

4. Run the selected example using its documented command.
