# Getting started

This document will guide through setting up PyDotBot connected to a DotBot
gateway and a DotBot robot.

## Prerequisites

Make sure you have access to an nRF DK board (nrf52833dk, nrf52840dk or
nrf5340dk) and to a DotBot (v1 or v2).

Follow the instructions of the
[DotBot firmware getting started page][dotbot-firmware-getting-started].

## Install PyDotBot

Use pip to install the latest version of PyDotBot from [pypi][pydotbot-pypi]:

```
pip install pydotbot -U
```

## Setup the gateway

The gateway is used to bridge the UART communication between PyDotBot running on
a computer and the BLE radio used to communicate wirelessly with the DotBot(s).

1. Connect the nRF DK gateway to your computer

2. Identify the TTY port it is connected to. On Linux, it should be `/dev/ttyACM0`.
  On Windows, check the device manager, it should be `COM1`, `COM2`, `COM3`, etc

3. From a terminal, run `dotbot-controller` with the TTY port you identified
  above:

```
dotbot-contoller --port <tty port>
```

At this point, if the DotBot is powered on with fully charged batteries, you
should see it poping up in the logs, with a similar output:

```
Welcome to the DotBots controller (version: 0.xx).
2023-11-29T07:55:11.725907Z [info     ] Lighthouse initialized         [pydotbot] context=dotbot.lighthouse2
2023-11-29T07:55:11.726325Z [info     ] Controller initialized         [pydotbot] context=dotbot.keyboard
2023-11-29T07:55:11.726746Z [info     ] Starting web server            [pydotbot] context=dotbot.server
2023-11-29T07:55:11.739085Z [info     ] Serial port thread started     [pydotbot] context=dotbot.serial_interface
2023-11-29T07:55:12.197714Z [info     ] New dotbot                     [pydotbot] application=DotBot context=dotbot.controller msg_id=90350129 payload_type=ADVERTISEMENT source=9903ef26257feb31
```

## Control your DotBot

1. Open [http://localhost:8000/dotbots](http://localhost:8000/dotbots) and you
should have one item corresponding to your DotBot.

2. Activate it by clicking on the DotBot item:

```{image} _static/images/pydotbot-ui-activate.png
:alt: Single DotBot item not active
:class: bg-primary
:width: 400px
:align: center
```

3. The item should now be expanded: a joystick and a color picker widgets are
  visible:

```{image} _static/images/pydotbot-ui-active.png
:alt: Single active DotBot item, with widgets
:class: bg-primary
:width: 400px
:align: center
```

4. Check that you can control the DotBot:
  - Move it using the virtual joystick in the UI
  - Move it using the arrow keys of your keyboard
  - Change RGB LED color by pressing "b", "g" or "b" or by using the color picker
    in the UI


[dotbot-firmware-getting-started]: https://dotbot-firmware.readthedocs.io/en/latest/getting_started.html
[pydotbot-pypi]: https://pypi.org/project/pydotbot/