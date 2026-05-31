# Know your DotBot v3

A quick tour of the hardware you'll plug things into. This is orientation only -
for the PCB, schematics, and CAD see the
[DotBot-hardware repo](https://github.com/DotBots/DotBot-hardware).

Three pieces make up a working setup:

- **The DotBot v3** - the robot. An nRF5340-based wheeled bot.
- **The gateway** - an nRF5340-DK that bridges your computer to the swarm over the air.
- **A Lighthouse 2 base station** - for indoor localization (optional, per-experiment).

## DotBot v3 - the robot

The robot has two connectors you'll use:

| Connector | What it's for |
|---|---|
| **USB-C (J2)** | Flash and program the bot. Also powers it while plugged in. |
| **Barrel jack (J4)** | Charges the on-board supercapacitor (the bot's "battery"). |

**USB-C (J2) - flashing.** The DotBot v3 has an **on-board programmer** behind
the USB-C port: a J-Link-OB / DAPLink debug chip plus an SWD mux that routes the
debug lines to the nRF5340. **You do not need a separate J-Link** for normal
flashing - just a USB-C cable. Plug it in and flash:

```bash
# cabled flash of one bot (board defaults to dotbot-v3)
dotbot device flash dotbot -s 77
```

A standalone J-Link is only needed to re-flash the on-board programmer's *own*
firmware (`dotbot device flash-programmer`) - a rare, one-time bring-up step.
See [device](../cli/device.md) for the full flashing workflow.

**Barrel jack (J4) - charging.** The barrel jack feeds the BQ24640 charger,
which tops up the on-board supercapacitor (a ~240 F stack at 3.0 V max). The
supercap is what runs the bot when it's untethered; expect short, fast charges
rather than a slow battery cycle.

```{note}
The bot is powered whenever USB-C is connected, so you can flash and bench-test
without charging first. For free-roaming, charge via the barrel jack.
```

## Gateway - nRF5340-DK

The gateway is a stock **Nordic nRF5340-DK** with its own on-board J-Link (over
the DK's micro-USB port). It runs the Mari gateway firmware and bridges your
host to the swarm radio.

```bash
# flash the gateway role onto a DK (writes the network id + both cores)
dotbot device flash-gateway -n 0100 -f 0.8.0rc1 -s 10

# then run the host-side UART<->MQTT bridge
dotbot run gateway
```

Geovane's serial-prefix convention: DotBot v3 boards start `77`, nRF5340-DKs
start `10` (the `-s` prefix selects which probe to talk to). See
[swarm](../cli/swarm.md) for driving the fleet once the gateway is up.

## Lighthouse 2 base station

For position tracking, the testbed uses **Valve Lighthouse 2** base stations.
Each DotBot v3 carries an LH2 sensor shield (a TS4231 light-to-digital receiver
with a photodiode) that decodes the base station's sweeping IR beams into a
position. One base station illuminates the arena; the bots compute where they
are from what they see.

Once the optical setup is in place, calibrate it before relying on the
coordinates - see [LH2 calibration](../guides/lh2-calibration.md).

## Next steps

- [device](../cli/device.md) - flash an app or role onto one cabled board.
- [swarm](../cli/swarm.md) - control the whole fleet over the air.
- [DotBot-hardware](https://github.com/DotBots/DotBot-hardware) - schematics, BOM, and CAD.
