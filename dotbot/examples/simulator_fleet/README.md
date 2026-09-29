# A simulated fleet in a virtual lab

A 20 x 30 m site with room for up to 1000 simulated DotBots.

`dotbot.toml` defines the site `virtual-lab`: its extent and three areas, a
`staging` strip along the north wall, the 16 x 16 m `field` and a `charging`
strip along the south wall, which `role = "staging"` makes a second staging
area.

`--robots N` starts N robots in a near-square block centred on the field,
200 mm apart centre to centre, the top half of the rows facing the staging
strip and the bottom half the charging strip. The largest here, 1000 robots
in 32 rows of up to 32, spans 6.2 x 6.2 m. At 200 mm a v3 robot has about
105 mm of floor to the next one across and between rows facing the same way,
and 47 mm tail to tail where the two halves meet.

## Run

From this folder, pick a fleet size. `dotbot` reads the `dotbot.toml` in the
current folder by itself, so no `-c` is needed:

```bash
BROWSER=true dotbot run simulator --robots 10 --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --robots 50 --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --robots 100 --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --robots 200 --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --robots 500 --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --robots 1000 --controller-http-port 8100 --headless
```

Then open <http://localhost:8100/console/>. Drop `BROWSER=true` and
`--headless` to have the controller open it in your browser.

To move robots, change their headings or mix in Mari robots, write the fleet
to a file, edit it, and run from it:

```bash
BROWSER=true dotbot run simulator --robots 500 --write-init-state fleet.toml --controller-http-port 8100 --headless
BROWSER=true dotbot run simulator --simulator-init-state fleet.toml --controller-http-port 8100 --headless
```

From another folder, pass the file with
`-c dotbot/examples/simulator_fleet/dotbot.toml`. Either way it is the whole
config, and your `~/.dotbot/config.toml` does not apply. The console frames
the whole site, where the robots are dots at their true size; zoom in to see
each one's body. Waypoints outside the site are refused.
