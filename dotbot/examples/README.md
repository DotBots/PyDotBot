# DotBot Simulator Experiments

This directory contains **experimental control scripts** for the DotBot simulator.
The goal is to prototype, test, and iterate on the testbed without needing to deploy anything,
with the same API that will run on a real testbed. **without touching the controller internals**.

All interaction with the simulator is done **via HTTP**, exactly like a real deployment.

---

## 1. Start the simulator

First, start the DotBot controller in **simulator mode** with the correct configuration:

```bash
dotbot-controller \
  --config-path config_sample.toml \
  -p dotbot-simulator \
  -a dotbot-simulator
```

## 2. Run the experiments

For example, if you want to run the charging station proof-of-concept

```bash
python3 dotbot/examples/charging_station.py
```
