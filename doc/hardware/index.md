# Know your DotBot v3

A quick tour of the hardware you'll plug things into. This is orientation only -
for the PCB, schematics, and CAD see the
[DotBot-hardware repo](https://github.com/DotBots/DotBot-hardware).

Three pieces make up a working setup:

- **The DotBot v3** - the robot. An nRF5340-based wheeled bot.
- **The gateway** - an nRF5340-DK that bridges your computer to the swarm over the air.
- **A Lighthouse 2 base station** - for indoor localization (optional, per-experiment).

## Cables and connectors

What to have on hand (the two USB cables are the ones you'll reach for most):

| Cable / connector | For |
|---|---|
| **USB-C to USB-A (or USB-C)** | Flash and power the DotBot v3 (its USB-C port, J2). |
| **micro-USB to USB-A (or USB-C)** | The nRF5340-DK gateway's on-board J-Link. |
| **Barrel-jack charger** (2.5 mm, 6-18 V) | Charges the DotBot v3 supercap (J4); free-roaming only. |

## DotBot v3

### Components
| Component | Reference | Function |
|---|---|---|
| **VDD booster** | U8 | Boosts the supercap voltage to a stable 3.6 V system rail. |
| **ON/OFF switch** | SW3 | Turns the DotBot on or off. |
| **Reset button** | SW1 | Resets the nRF5340. |
| **User button** | SW2 | General-purpose button. |
| **MCU: nRF5340** | U1 | The brain of the DotBot. |
| **Over-voltage protection** | U4 (ADCMP350) | Disconnects the input if the charging voltage is too high. |
| **Vmotor switch** | U10 + Q10–Q12 | Gates the motors power. | 
| **Vbumper booster** | U9 (TPS61022) + L2 | Boosts the bumper rail to 3.66 V. |
| **Motor drivers** | U5, U6 (BDR6120H) | H-bridges converting MCU logic signals into motor current. |
| **Wheels** | — | Two driven wheels, one per motor (left and right). |
| **Bumper rails** | V_Bumper± | Contact rings at the front and rear, carrying the charging rail. |
| **DotBot ID** |  —  |DotBot ID. |
| **Lighthouse receiver** | D17 (BPW34S) + U12 (TS4231) | Detects the IR sweeps from the base stations and outputs them as digital signals. |
| **Supercap charger** | U13 (BQ24640) + L3 |Charges the supercapacitor. |
| **USB-C port** | J2 | Connects to the DAPLink probe, data only, no charging. |
| **Add-on headers** | J16, J17 | Expose UART, I²C and SPI for expansion boards. |
| **SWD mux** | U7 (TS3A27518E) | Routes the debug lines from the on-board programmer to the nRF5340. |
| **Debug probe** | U2 (STM32F103) | Runs DAPLink; programs and debugs the nRF5340 over USB. |
| **Motors** | M1, M2 (N20) | Drive the left and right wheels; each carries a quadrature encoder. |
| **Status LEDs** | D19, D23, D24 + D18 | Indicate the robot's mode: bootloader, running, programming. |
| **Supercapacitors** | J11 / J12  | Main energy storage. |
| **Coin cell** | BT1 (CR2032, 3 V) | Enables the motors to be powered. |
| **Supercap terminals** | J11 (V_Cap+), J12 (V_Cap−) | Connect the supercapacitors to the board. |
| **Passive front wheel** | — | Ball caster: used for support. |
| **Bumper connectors** | J7, J8, J14 (front) / J9, J10, J15 (rear) |  Connect the front and rear bumpers to the board. |
| **Barrel jack** | J4 | Charges the supercapacitors. |
<p align="center">
  <img width="988" height="649" alt="image" src="https://github.com/user-attachments/assets/c2b05eac-a0ff-4369-bcc2-7ad947905142" /><br>
  <b>Figure 1: DotBot front</b>
</p>
<p align="center">
  <img width="1052" height="732" alt="image" src="https://github.com/user-attachments/assets/058f5a1c-5d77-4452-b8b0-d15a50b4189b" /><br>
  <b>Figure 2: DotBot back</b>
</p>

### Connectors
The DotBot has two connectors you'll use:

| Connector | What it's for |
|---|---|
| **USB-C (J2)** | Flash and program the DotBot. |
| **Barrel jack (J4)** | Charges the on-board supercapacitor (the DotBot's "battery"). |

**USB-C (J2) - flashing.** The DotBot v3 has an **on-board programmer** behind
the USB-C port: a J-Link-OB / DAPLink debug chip plus an SWD mux that routes the
debug lines to the nRF5340. **You do not need a separate J-Link** for normal
flashing - just a USB-C cable. Plug it in and flash:

```bash
# cabled flash of one DotBot (board defaults to dotbot-v3)
dotbot device flash dotbot --probe 77
```

A standalone J-Link is only needed to re-flash the on-board programmer's *own*
firmware (`dotbot device flash-programmer`) - a rare, one-time bring-up step.
See [device](../cli/device.md) for the full flashing workflow.

**Barrel jack (J4) - charging.** The barrel jack feeds the BQ24640 charger,
which tops up the on-board supercapacitor (a ~240 F stack at 3.0 V max). The
supercap is what runs the DotBot when it's untethered; expect short, fast charges
rather than a slow battery cycle.

```{note}
The DotBot is powered whenever USB-C is connected, so you can flash and bench-test
without charging first. For free-roaming, charge via the barrel jack.
```

## Gateway - nRF5340-DK

The gateway is a stock **Nordic nRF5340-DK** with its own on-board J-Link (over
the DK's micro-USB port). It runs the Mari gateway firmware and bridges your
host to the swarm radio.

```bash
# flash the gateway role onto a DK (writes the network id + both cores)
dotbot device flash-mari-gateway --swarm-id 0100 -f 0.8.0rc1 --probe 10

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
position. One base station illuminates the arena; the DotBots compute where they
are from what they see.

Once the optical setup is in place, calibrate it before relying on the
coordinates - see [LH2 calibration](../guides/lh2-calibration.md).

## Next steps

- [device](../cli/device.md) - flash an app or role onto one cabled board.
- [swarm](../cli/swarm.md) - control the whole fleet over the air.
- [DotBot-hardware](https://github.com/DotBots/DotBot-hardware) - schematics, BOM, and CAD.
