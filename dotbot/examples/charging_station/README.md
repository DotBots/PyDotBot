# Charging Station

This demo runs a charging-station scenario:
robots first form a queue, then move through charging and parking phases.
It works with real robots or with the simulator via the same controller API.
The simulator setup below is the default path for reproducibility.

## How to run (default: simulator)

The example reads its layout from the controller's site, which needs a
**field** and a **staging** area: robots queue on the border between the two,
charge one at a time at the site's first `charger` object (else at a point on
staging's far edge), then park along the field's opposite edge. It refuses a
site without a staging area. The site `dotbot config init` writes has both; a
charger is added in `site.toml`, or with the Object tool of `dotbot site edit`:

```toml
[objects.pad-a]
kind = "charger"
x = 3200
y = 3900
```

### 1. Start the simulator

In an empty folder:

```bash
dotbot config init                  # a site with a 2 x 2 m field and a staging strip
dotbot run simulator --robots 10
```

To start from fixed positions instead, pass
`--simulator-init-state dotbot/examples/charging_station/charging_station_init_state.toml`
in place of `--robots 10`.

### 2. Run the charging-station scenario

In a new terminal:

```bash
python -m dotbot.examples.charging_station.charging_station
```

It talks to the controller on `localhost:8000`; `DOTBOT_CONTROLLER_URL` and
`DOTBOT_CONTROLLER_PORT` point it elsewhere.
