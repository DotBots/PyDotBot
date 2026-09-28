# A simulated fleet in the AIO hall

A 20 x 30 m site with room for up to 1000 simulated DotBots, and ready-made
fleets of 10 to 1000 robots to fill it.

- `site.toml` defines the site `inria-aio-c`: its extent and four areas, the
  2 x 2 m `arena`, a `staging` strip along the north wall, the main 16 x 16 m
  `field` and a `charging` strip along the south wall.
- `init-<N>.toml` starts N robots in a near-square block centred on the
  field, 200 mm apart centre to centre, the top half of the rows facing the
  staging strip and the bottom half the charging strip. The largest, 1000
  robots in 32 rows of up to 32, spans 6.2 x 6.2 m.
- `gen_init_state.py --n N` writes `init-N.toml` for any other count.

At 200 mm a v3 robot has about 105 mm of floor to the next one across and
between rows facing the same way, and 47 mm tail to tail where the two
halves meet.

## Run

From this folder, pick a fleet size:

```bash
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-10.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-50.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-100.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-200.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-500.toml --controller-http-port 8100 --headless
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c --simulator-init-state init-1000.toml --controller-http-port 8100 --headless
```

Then open <http://localhost:8100/console/>. Drop `BROWSER=true` and
`--headless` to have the controller open it in your browser.

`-c site.toml` makes this file the whole config, so no other `dotbot.toml`
applies. The console frames the whole site, where the robots are dots at
their true size; zoom in to see each one's body. Waypoints outside the site
are refused.
