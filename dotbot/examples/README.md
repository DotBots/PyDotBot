# DotBot Examples

This directory contains example scenarios for DotBots.
Examples can run against either real robots or the simulator, using the same controller APIs.
The simulator setup is documented as the default path because it is the most common way to reproduce experiments.
Each scenario has its own folder with dedicated instructions, initial states, and run commands.

## Available scenarios

- `minimum_naming_game/`: naming game examples (with and without motion)
- `work_and_charge/`: work/charge alternation scenario
- `charging_station/`: queue-and-charge scenario
- `labyrinth/`: two-robot labyrinth navigation
- `motions/`: move a single DotBot through predefined shapes or speed profiles
- `simulator_fleet/`: up to 1000 simulated robots on a 20 x 30 m site

We also provide a stop.py helper script to halt the simulator (without needing to stop robots via SwarmIT).

## Common usage pattern (default: simulator)

1. Pick a scenario and read its local `README.md`.
2. Start the simulator, passing the scenario's init state:

```bash
dotbot run simulator --simulator-init-state <path/to/init_state.toml>
```

The examples that place robots by area (`charging_station/`, `motions/`, the
naming game with motion) read the controller's site. `dotbot config init`
writes one with a field and a staging area.

3. Run the selected example using its documented command.
