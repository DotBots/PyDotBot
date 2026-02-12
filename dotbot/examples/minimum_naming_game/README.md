# Minimum Naming Game

This demo runs the minimum naming game in the DotBot simulator, where the robots use local communication to converge on a single word.

This demo includes two variants: a static setup without motion and a dynamic setup with motion.

## Install Python packages (pip)

Install the Python packages required to run this demo.

```bash
pip install pyyaml scipy
```

## How to run

1. Specify the initial state of the DotBots by replacing the file path for ```simulator_init_state_path``` in [config_sample.toml](config_sample.toml).

**Static setup** (without motion) using init_state.toml:

```toml
simulator_init_state_path = "dotbot/examples/minimum_naming_game/init_state.toml"
```

**Dynamic setup** (with motion) using init_state_with_motion.toml:

```toml
simulator_init_state_path = "dotbot/examples/minimum_naming_game/init_state_with_motion.toml"
```

2. Start the controller in simulator mode:

```bash
python -m dotbot.controller_app --config-path config_sample.toml -p dotbot-simulator -a dotbot-simulator --log-level error
```

3. Run the minimum naming game scenario:

Open a new terminal and run the minimum naming game scenario.

**Static setup** (without motion):

```bash
python -m dotbot.examples.minimum_naming_game.minimum_naming_game
```

**Dynamic setup** (with motion) :

```bash
python -m dotbot.examples.minimum_naming_game.minimum_naming_game_with_motion
```