# Getting started

This document will help guide you through the setup of PyDotBot connected to
a DotBot gateway and a DotBot robot.

## Prerequisites

Make sure you have access to an nRF DK board (nRF52833DK, nRF52840DK or
nRF5340DK) and to a DotBot (v1 or v2).

Follow the instructions in the
[DotBot firmware getting started page][dotbot-firmware-getting-started].

## Install PyDotBot

Use pip to install the latest version of PyDotBot from [pypi][pydotbot-pypi]:

```
pip install pydotbot -U
```

## Setup the gateway

The gateway is an nRF DK used to bridge the UART communication between PyDotBot
running on a computer and the BLE radio used to communicate wirelessly with the
DotBot(s).

1. Connect the nRF DK gateway to your computer

2. Identify the TTY port it is connected to. On Linux, it should be `/dev/ttyACM0`.
  On Windows, check the device manager, it should be `COM1`, `COM2`, `COM3`, etc.
  If using an nRF5340DK, you might see 2 TTY port, use the one with the lowest
  id.

3. From a terminal window (or powershell on Windows), run `dotbot-controller`
  with the TTY port you identified above:

```
dotbot-controller --port <tty port>
```

At this point, if the DotBot is powered on with fully charged batteries, you
should see an output in the logs that looks something like:

```
Welcome to the DotBots controller (version: 0.xx).
2023-11-29T07:55:11.725907Z [info     ] Lighthouse initialized         [pydotbot] context=dotbot.lighthouse2
2023-11-29T07:55:11.726746Z [info     ] Starting web server            [pydotbot] context=dotbot.server
2023-11-29T07:55:11.739085Z [info     ] Serial port thread started     [pydotbot] context=dotbot.serial_interface
2023-11-29T07:55:12.197714Z [info     ] New dotbot                     [pydotbot] application=DotBot context=dotbot.controller msg_id=90350129 payload_type=ADVERTISEMENT source=9903ef26257feb31
```

## Control your DotBot

1. In a browser, open [http://localhost:8000/PyDotBot](http://localhost:8000/PyDotBot)
and you should have one item corresponding to your DotBot.

2. Select it by clicking on the DotBot item:

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
  - by clicking on the joystick and dragging it in the direction that you want
    the DotBot to move
  - by using the color selector in the UI

5. In a separate command window, launch `dotbot-keyboard`:
```
Welcome to the DotBots keyboard interface (version: 0.16).
2023-12-08T10:07:32.597536Z [info     ] Controller initialized         [pydotbot] context=dotbot.keyboard
```

6. Check that you can control the DotBot using your keyboard:
  - control it using the arrow keys
  - change the RGB LED color by pressing "r", "g", "b", "y", "w", "n" keys
```{admonition} Note
:class: info
You might have to set the mouse focus on a separate application to have the keyboard
key events correctly taken into account. This is a limitation of the `pynput`
library used to track the keyboard events.
```

[dotbot-firmware-getting-started]: https://dotbot-firmware.readthedocs.io/en/latest/getting_started.html
[pydotbot-pypi]: https://pypi.org/project/pydotbot/
