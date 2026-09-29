# A simulated fleet in a large hall

A 20 x 30 m site with room for up to 1000 simulated DotBots.

`site.toml` defines the site `sim-hall`: its extent and three areas, a
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

From this folder, pick a fleet size:

```bash
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 10 --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 50 --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 100 --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 200 --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 500 --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 1000 --controller-http-port 8100 --headless
```

Then open <http://localhost:8100/console/>. Drop `BROWSER=true` and
`--headless` to have the controller open it in your browser.

To move robots, change their headings or mix in Mari robots, write the fleet
to a file, edit it, and run from it:

```bash
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --robots 500 --write-init-state fleet.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site sim-hall --simulator-init-state fleet.toml --controller-http-port 8100 --headless
```

`-c site.toml` makes this file the whole config, so no other `dotbot.toml`
applies. The console frames the whole site, where the robots are dots at
their true size; zoom in to see each one's body. Waypoints outside the site
are refused.
