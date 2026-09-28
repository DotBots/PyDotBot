# 500 simulated robots in the AIO hall

A 20 x 30 m site with room for 500 simulated DotBots, and the robots to fill it.

- `site.toml` defines the site `inria-aio-c`: its extent and four areas, the
  2 x 2 m `arena`, a `staging` strip along the north wall, the main `field`
  and a `charging` strip along the south wall.
- `init.toml` starts 500 robots in a 25 x 20 grid over the field, 640 mm
  apart across and 800 mm down, the top ten rows facing the staging strip and
  the bottom ten the charging strip. `gen_init_state.py` writes it.

## Run

From this folder:

```bash
BROWSER=true dotbot -c site.toml run simulator --site inria-aio-c \
    --simulator-init-state init.toml --controller-http-port 8100 --headless
```

Then open <http://localhost:8100/console/>. Drop `BROWSER=true` and
`--headless` to have the controller open it in your browser.

`-c site.toml` makes this file the whole config, so no other `dotbot.toml`
applies. The console frames the whole site; zoom in to tell robots apart.
Waypoints outside the site are refused.
