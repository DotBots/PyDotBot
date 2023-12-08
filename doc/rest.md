# REST

While connected to a DotBot gateway, the `dotbot-controller`
application provides a REST server to send commands to and receive information
from connected DotBots.

The REST API is documented in the running `dotbot-controller` application itself
at [http://localhost:8000/api](http://localhost:8000/api). This page also allows
you to play with the API directly from the browser.

```{image} _static/images/pydotbot-ui-openapi.png
:alt: Open API UI
:class: bg-primary
:width: 700px
:align: center
```

## Prerequisites

Make sure you already followed the [getting started](getting_started) page and
have a functional setup with `dotbot-controller` running and connected to a
nRF DK gateway.

To interact with the REST API, you will use the Python
[requests](https://pypi.org/project/requests/) package. You can install it on
your computer using pip:

```
pip install -U requests
```

## The basics

First, let's start by fetching the information about available DotBots using
the following script:

```py
import json
import requests

get_endpoint = "controller/dotbots"

print(
    json.dumps(
        requests.get(
            f"http://localhost:8000/{get_endpoint}"
        ).json()
    )
)
```

If a DotBot is connected, this script should give an output similar to:
```json
[
  {
    "address": "9903ef26257feb31",
    "application": 0,
    "swarm": "0000",
    "status": 2,
    "mode": 0,
    "last_seen": 1701244665.8099585,
    "waypoints": [],
    "waypoints_threshold": 40,
    "position_history": []
  }
]
```

This is a list of all DotBots connected to the `dotbot-controller`. In the
example above, there is only one DotBot connected.
The 8-byte `address` uniquely identifies a DotBot in the controller. The
`status` indicates whether the DotBot is `Alive` (value=0, the DotBot has been
seen within the last 5 seconds), `Lost` (value=1, the DotBot hasn't been seen
within the last 5 sec) or `Dead` (value=2, the DotBot hasn't been seen for more
than 60 sec).

If the DotBot `address` is already known by the controller, e.g. it identifies
one of the DotBots returned a the previous request, use the
`controller/dotbots/<address>` to fetch information about that particular
DotBot (for example `controller/dotbots/9903ef26257feb31`).

## Change the color of the RGB LED

Use the `controller/dotbots/{address}/{application}/rgb_led` endpoint to change
the RGB LED color on the DotBot. The `address` parameter in the URL can be
retrieved from the list of available DotBots that we got in the previous
section. The `application` parameter is 0 (DotBot) in our case.

It's important to note that this request, according to the API is a PUT request
and requires a payload:

```
{
  "red": 0,
  "green": 0,
  "blue": 0
}
```

Here is an example Python script to send a "RGB LED" request to one DotBot:

```py
import requests

ADDRESS = "DOTBOT_ADDRESS_HERE"  # edit this line with the DotBot address you want to control
RGB_LED_VALUE = {
    "red": 255,
    "green": 0,
    "blue": 0,
}

requests.put(
    f"http://localhost:8000/controller/dotbots/{ADDRESS}/0/rgb_led",
    json=RGB_LED_VALUE,
)
```

Play with the red/green/blue values to change the DotBot RGB LED.

## Move one DotBot

Use the `controller/dotbots/{address}/{application}/move_raw` endpoint to move a
DotBot.

This request, according to the API is also a PUT request and requires a payload:

```
{
  "left_x": 0,
  "left_y": 0,
  "right_x": 0,
  "right_y": 0
}
```

To control the DotBot motors, only `left_y` and `right_y` values are useful,
`left_x` and `right_x` being ignored by the firmware running on the DotBots.

```{admonition} Note 1
:class: info
left_{x,y} and right_{x,y} values must be within the range **[-100, 100]**
and it's important to know that absolute values below 50 won't move the motors
(because of limited power in electronic circuit and internal friction of the motors).
```

```{admonition} Note 2
:class: info
The firmware running on the DotBot stops automatically the motors if
no move command is received after 200ms. To move the DotBot continuously,
several commands must be sent with a delay below 200ms between them.
```

Here is an example Python script to send a "move raw" request to one DotBot:

```py
import requests

ADDRESS = "DOTBOT_ADDRESS_HERE"  # edit this line with the DotBot address you want to control
MOVE_RAW_VALUE = {
    "left_x": 0,
    "left_y": 60,
    "right_x": 0,
    "right_y": 60
}

requests.put(
    f"http://localhost:8000/controller/dotbots/{ADDRESS}/0/move_raw",
    json=MOVE_RAW_VALUE,
)
```

Adapt the script above to:

- move a DotBot forward during 10 seconds (use the sleep function from the
  Python `time` module for example)
- rotate a DotBot during 20 seconds
