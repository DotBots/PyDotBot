# Console manual test guide

Start the stack (three terminals, from this checkout's root, venv active).
`PYTHONPATH=.` makes the simulator run from this checkout rather than whichever
one is pip-installed; the vite dev server compiles `src/` directly either way.

```bash
PYTHONPATH=. dotbot run simulator --headless \
  --simulator-init-state dotbot/console-web/dev/simulator_init_state.toml

python dotbot/console-web/dev/fake_swarmit_server.py

npm --prefix dotbot/console-web run start
```

Open http://localhost:5173. Handy URL params: `?sel=1111` (preselect),
`?view=list|grid`, `?rail=testbed|missions`, `?theme=light`.

If the title bar says OFFLINE: the vite proxy targets do not match where the
controller runs. `curl localhost:5173/controller/dotbots` must return bots.

## Checklist

Map + selection
- [ ] Title bar: LIVE (green pulse), bot count; Dark|Light toggle flips theme
- [ ] Bots move smoothly; heading pointer at the circle edge; battery bar above
- [ ] Plain drag pans (clamped); plain click clears selection
- [ ] Shift-drag marquee selects; shift-click toggles one bot
- [ ] Click bot: red rectangle + id chip; hover another bot: chip appears
- [ ] Zoom +/-/recenter; arena keeps margins when rail opens or window resizes
- [ ] Layers panel: Battery Bars / Waypoints / DotBots / Real-scale / Trails toggle live

Footer (bottom strip)
- [ ] Nothing selected: N/1000 + per-state rollup; click a state row selects those bots
- [ ] One bot: LED thumb, short id, device, Drivable pill, state, battery, "x, y mm"
- [ ] Ghost bot (0001/0002): "Not drivable" pill, dock grayed, warning hint
- [ ] Multi: "N selected", per-state mini-rollup, dock drives the group
- [ ] Minimap: square (arena aspect), dots colored by state, drag moves the map view

Control dock
- [ ] Joystick: drag = bot drives, release = stops; knob shows LED color + live heading
- [ ] LED button -> swatch grid -> bot circle + map dot recolor (toast confirms)
- [ ] Alt-click map queues waypoints (dashed diamonds); popover lists "x, y mm" with per-item remove
- [ ] Go sends: bot navigates, diamonds go solid, button morphs to "Stop nav"
- [ ] Deselect and reselect other bots: the Planned mission survives (see rail Missions)

Testbed rail
- [ ] Icon strip -> panel; Testbed tab: Target label follows selection
- [ ] Flash... dialog: pick image, Flash N device(s); bots blink amber, queue tab
      shows per-device % bars, fleet % bar in Testbed tab, footer shows chunk progress
- [ ] After flash: bots in Bootloader (not drivable) -> Start returns them to Running
- [ ] Stop: Stopping -> Bootloader; Reset: Resetting -> Bootloader
- [ ] Console tab: log lines stream (flash/start/stop events), Clear works
- [ ] Missions tab: Planned (Go / discard) and Active (interrupt) rows; click row
      reselects its bots; arrival adds a "Recently completed" line

List / Grid
- [ ] Search by id, state filter, column sort; checkbox multi-select + select-all
- [ ] Selection carries across Map/List/Grid and drives the same footer dock

## Scripted actions (against the running stack)

```bash
# color a bot's LED
curl -X PUT localhost:8000/controller/dotbots/badcafe111111111/0/rgb_led \
  -H 'Content-Type: application/json' -d '{"red":34,"green":197,"blue":94}'

# send a waypoint mission (bot navigates on its own)
curl -X PUT localhost:8000/controller/dotbots/badcafe111111111/0/waypoints \
  -H 'Content-Type: application/json' \
  -d '{"threshold":60,"waypoints":[{"x":400,"y":1600},{"x":1600,"y":400}]}'

# flash two bots (watch rail queue + console)
curl -N -X POST localhost:8001/flash/stream -H 'Content-Type: application/json' \
  -d '{"firmware_b64":"ZmFrZQ==","devices":["badcafe111111111","deadbeef22222222"]}'

# stop / start / reset a subset (or omit devices = whole fleet)
curl -X POST localhost:8001/stop -H 'Content-Type: application/json' \
  -d '{"devices":["badcafe111111111"]}'

# screenshot for the Claude Design re-seed loop
node dotbot/console-web/dev/screenshot.mjs "http://127.0.0.1:5173/?sel=1111" out.png
```
