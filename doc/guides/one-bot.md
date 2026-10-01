# Drive a single DotBot

Build and flash one DotBot and a gateway, cable them to your computer, and drive
the DotBot from the web UI. This is the smallest real-hardware setup. For the
no-hardware path, use the [simulator](simulator.md) instead.

Flashing needs `nrfjprog` (see the README prerequisites). The commands below
flash the pinned release, fetched on first use; to flash your own build
instead, run `dotbot fw build <app> ...` (needs SEGGER
Embedded Studio) and add `-f local` to each `device flash`.

## 1. Flash the DotBot

The DotBot v3 is an nRF5340, which has two cores - the application core (your
app) and the network core (the radio) - so you flash two images:

```bash
# cable-flash to the DotBot whose J-Link serial starts with 77
dotbot device flash dotbot --bare --probe 77                 # app core
dotbot device flash nrf5340_net -b nrf5340dk-net --probe 77  # network core
```

## 2. Flash the gateway

The gateway is a dev board (e.g. an nRF52840-DK) plugged into your computer; it
bridges the DotBot's radio to USB serial.

```bash
# cable-flash to the DK whose J-Link serial starts with 10
dotbot device flash dotbot_gateway -b nrf52840dk --probe 10
```

## 3. Drive it from the web UI

With the gateway plugged in, point the controller at its serial port and open
the web UI:

```bash
dotbot run controller --conn /dev/ttyACM0  # serial gateway; no swarm-id needed
```

Select the DotBot in the browser and steer it with the joystick. See the
[controller + web UI guide](controller.md) for the full UI tour, and
[`fw`](../cli/fw.md) / [`device`](../cli/device.md) for the firmware commands.

## Next

- Operate many DotBots over the air - the [`swarm`](../cli/swarm.md) reference.
- Add real-world positions - [LH2 calibration](lh2-calibration.md), captured over
  the air once you've provisioned a swarm.
