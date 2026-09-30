# Set up a bench

Bring up a small swarm on a desk: one gateway, a few DotBots, all flashed from
your computer over USB. This is the page to follow with boards straight from the
factory. Once the bench is up, the [`swarm`](../cli/swarm.md) reference takes
over.

## What you need

| Item | Notes |
|---|---|
| An **nRF5340-DK** | Becomes the gateway. |
| One or more **DotBot v3** | Each has an on-board programmer on its USB-C port, so no external J-Link is needed. |
| **USB data cables** | One micro-USB for the DK, one USB-C per DotBot you flash. |
| **nRF Command Line Tools** (`nrfjprog`) and the SEGGER J-Link software | On your `PATH`. `dotbot device` stops early with an install hint when `nrfjprog` is missing. |
| `pydotbot` | `pip install pydotbot`. |
| A swarm id | A 16-bit hex value, e.g. `0100`, that both boards share. |
| Optional: Lighthouse 2 base stations | Only for positions, see [LH2 localization](lh2-calibration.md). |

```{note}
Never run `nrfjprog` or `dotbot device` under `sudo`. One sudo run leaves
`/tmp/boost_interprocess/` owned by root and every later call fails with
*Operation not permitted*. Fix it with `sudo rm -rf /tmp/boost_interprocess`.
```

## 1. Flash the gateway

Plug the DK in, switch it on, and flash the Mari gateway firmware:

```bash
dotbot device flash mari-gateway --swarm-id 0100 --probe 10
```

`--probe 10` picks the DK by its J-Link serial prefix; you can omit it when only
one board is plugged in.

## 2. Flash each DotBot

Plug one DotBot in over USB-C and flash the SwarmIT sandbox host:

```bash
dotbot device flash swarmit-sandbox --swarm-id 0100 --probe 77
```

Repeat for each DotBot. Unplug each board before plugging in the next one, or pass
the full serial number to `--probe`.

### Factory-fresh boards and APPROTECT

A new nRF5340 ships with its **access port protection** (APPROTECT) on:
`nrfjprog` can neither read nor program it until the chip is *recovered*, which
erases it completely. Both commands above do that for you: they recover and erase
both cores, flash them, then write the UICR registers that keep the debug port
open, so the board stays flashable after a power cycle.

Nothing else recovers on its own, since a recover erases the chip. Flashing an
app or a file with `dotbot device flash`, and `dotbot device info`, stop with
the message *access port is protected (APPROTECT)* and say what to run. To
unlock a board for other firmware, recover both cores by hand and flash again.
Without `--coprocessor`, `nrfjprog --recover` only reaches the application core:

```bash
nrfjprog -f NRF53 --recover --coprocessor CP_NETWORK
nrfjprog -f NRF53 --recover
```

`dotbot device info` also says whether a board will stay open:

```text
debug:     open (APPROTECT disabled in UICR)
```

`locks at the next power cycle` instead means the board was flashed some other
way. Re-run the role flash from step 1 or 2 to fix it.

```{note}
Leaving the debug port open is deliberate for a research bench, where boards
get re-flashed all the time. A deployment that has to lock the firmware down
needs a different flash flow.
```

## 3. Start the bridge and check the swarm

Start the host bridge on the gateway's serial port, then look for the DotBots:

```bash
dotbot run gateway -p /dev/ttyACM0 -m mqtts://<broker>:8883
dotbot swarm status
```

A freshly flashed DotBot should be listed within about 20 seconds. From here,
[`swarm`](../cli/swarm.md) covers flashing and starting apps.

## Reconnecting after a power-off

A DotBot that was switched off comes back in the SwarmIT bootloader, not
running its app. Once `dotbot swarm status` lists it again, start the app:

```bash
dotbot swarm start
```

## Desk traps

- **The DK's power switch.** The nRF5340-DK has an nRF power switch (SW8).
  With it off, the board's programmer still enumerates over USB but the nRF5340
  is unpowered, so flashing fails.
- **Charge-only USB cables.** Some cables carry power but no data. The board
  lights up and `nrfjprog --ids` lists nothing. Swap the cable before debugging
  anything else.
- **A flat supercapacitor.** A DotBot v3 runs on a 3.0 V supercapacitor.
  `dotbot swarm status` shows its reading as critical below 1.5 V, and the
  robot browns out at 0.6 V. Charge it first.
- **Base-station power.** Lighthouse 2 base stations need their own power
  supply. With them off, DotBots run but report no position.

## Time budget

| Step | Roughly |
|---|---|
| Role flash of one board (recover, both cores, config) | 1-2 minutes |
| Recover on a slow J-Link | several minutes; each of its three steps gives up after 10 |
| A DotBot joining after its flash | 15-20 seconds |
| A DotBot joining after a power-on | 15-20 seconds, then `swarm start` |
