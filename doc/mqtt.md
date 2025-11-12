# MQTT

For a brief introduction to MQTT, have a look at
[HiveMQ MQTT Essentials](https://www.hivemq.com/mqtt/).

At startup the controller automatically connects by default to
[https://broker.hivemq.com](https://broker.hivemq.com), a fully open MQTT broker.
If you want to use a different broker, see `.env.example` for the list of
possible MQTT options.

Then it subscribes to commands messages published to the
`/dotbots/2SzQsZWfOV8OXrWQtEEdIA==/0000/+/+/move_raw` and
`/dotbots/2SzQsZWfOV8OXrWQtEEdIA==/0000/+/+/rgb_led` topics, among others. These
topics are used to control the motors and on-board RGB LED.

They can be described as follows:
`/dotbots/<secret topic>/<swarm-id>/<dotbot-address>/<application>/<command>`
where:
- `secret topic` is a base64 encoded topic, derived from a random 8 digits
  pin code using [HKDF](https://en.wikipedia.org/wiki/HKDF),
- `swarm-id` is a 4 hexadecimal string (2B long) identifier corresponding to a swarm,
  typically all DotBots behind a single gateway
- `dotbot-address` is a 18 hexadecimal string (8B long) unique identifier of a DotBot,
- `application` is the type of application (0: DotBot, 1: SailBot)
- `command` is the type of command (`move_raw` or `rgb_led`)

Since all messages are exchanged unauthentified via a public broker, all payloads
exchanged between MQTT clients and the controller are encrypted using
the standard [JSON Web Encryption protocol](https://datatracker.ietf.org/doc/html/rfc7516).
The symmetric keys used to encrypt the payload are also derived from a random 8 digits
pin code using [HKDF](https://en.wikipedia.org/wiki/HKDF).
All topics used by one controller and its PyDotBot clients use the same
`/dotbots/<secret topic>` base topic to make sure multiple controller running
at the same time won't interfere.

One last thing about the 8 digit pin code: it rotates every 15 minutes (with a
grace period of 2 minutes) to ensure it cannot reused later and to make brut
force attacks harder. This means that every 15 minutes, the encryption key and
base topic changes for a given controller. All clients are notified of this
change and recomputes (or rederive) their key/topic accordingly.

## Prerequisites

Make sure you already followed the [getting started](getting_started) page and
have a functional setup with `dotbot-controller` running and connected to a
nRF DK gateway.

To interact with the MQTT broker, you will use a Python script that require
several packages:
- [paho-mqtt](https://pypi.org/project/paho-mqtt) to connect and publish
  messages to the MQTT broker,
- [requests](https://pypi.org/project/requests/) to directly fetch dotbots and
  the pin code from the controller REST api,
- [cryptography](https://pypi.org/project/cryptography/) to derive the secret
  topic and encryption key using HKDF,
- [joserfc](https://pypi.org/project/joserfc/) to encrypt the payload using JSON Web Encryption standard.

Install all the Python dependencies using pip:
```
pip install cryptography joserfc paho-mqtt requests
```

## The basics

Running the controller is as easy as running the following command:

```
dotbot-controller
```

The logs should contain information about the MQTT broker connection and the
topic subscriptions:

```
Welcome to the DotBots controller (version: 0.17).
2024-01-11T13:42:02.738414Z [info     ] Lighthouse initialized         [pydotbot] context=dotbot.lighthouse2
2024-01-11T13:42:02.740025Z [info     ] Starting web server            [pydotbot] context=dotbot.controller
2024-01-11T13:42:02.752914Z [info     ] Serial port thread started     [pydotbot] context=dotbot.serial_interface
2024-01-11T13:42:02.949352Z [info     ] Connected                      [pydotbot] context=dotbot.mqtt flags=0 rc=0 receive_maximum=[10] topic_alias_maximum=[5]
2024-01-11T13:42:03.128297Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/command/0000/+/+/move_raw [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.128606Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/command/0000/+/+/rgb_led [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.128790Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/command/0000/+/+/waypoints [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.128940Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/command/0000/+/+/clear_position_history [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.129056Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/lh2/add [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.129159Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/lh2/start [pydotbot] context=dotbot.mqtt qos=(0,)
2024-01-11T13:42:03.129280Z [info     ] Subscribed to /dotbots/2SzQsZWfOV8OXrWQtEEdIA==/request [pydotbot] context=dotbot.mqtt qos=(0,)
```

In the output above you can see that the _secret topic_ is `2SzQsZWfOV8OXrWQtEEdIA==`.

Let's start by fetching available dotbots and the pin code using our own Python script:

```py
import requests

dotbots = requests.get('http://localhost:8000/controller/dotbots').json()

if not dotbots:
    print("No DotBot found!, exiting")
    sys.exit(0)

dotbot = dotbots[0]

if dotbot["status"] != 0:
    print("DotBot is not alive!, exiting")
    sys.exit(0)

dotbot_addr = dotbot["address"]
print(f"DotBot address: {dotbot_addr}")

pin_data = requests.get('http://localhost:8080/pin_code').json()
pin = str(pin_data["pin"]).encode()
print(f"Pin code: {pin.decode()}")
```

If you have a running DotBot, at this point you should have an output like this (with different address/pin values):
```
DotBot address: 9903ef26257feb31
Pin code: 30206157
```

Know let's derive the secret topic and symmetric key using HKDF (extend the
previous script with the following content):

```py
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from dotbot_utils.protocol import PROTOCOL_VERSION

version = PROTOCOL_VERSION

# derive topic and key
kdf_topic = HKDF(
    algorithm=hashes.SHA256(),
    length=16,
    salt=b"",
    info=f"secret_topic_{version}".encode()
)
topic = base64.urlsafe_b64encode(kdf_topic.derive(pin)).decode()
print(f"Secret topic: {topic}")

kdf_key = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=b"",
    info=f"secret_key_{version}".encode()
)
key = kdf_key.derive(pin)
print(f"Encryption AES key: {key.hex()}")
```

To ensure consistent values on both ends the salt parameter is left empty and
the info field contains a string built from the PyDotBot protocol version. This
ensures different PyDotBot protocol versions cannot be used together.

At this point, when you run the script, you should have an output like:
```
DotBot address: 9903ef26257feb31
Pin code: 30206157
Secret topic: 2RIP5S_xgDvu6wGJVZH6tw==
Encryption AES key: ecddf00497b30b57d965310a46b0502e06ebe89374e4167f15fc06a44e9a06bf
```

We are now ready to add the MQTT client code to our script which is based on paho-mqtt:

```py
import paho.mqtt.client as mqtt

# Connect to the MQTT broker
client = mqtt.Client(protocol=mqtt.MQTTv5)
client.tls_set_context(context=None)
client.connect("broker.hivemq.com", 8883, 60)
```

## Change the color of the RGB LED

Let's change the RGB LED color of the DotBot by sending an `rgb_led` command.
This command takes a payload parameter containing a json with the red, green and blue
values to apply.
But first the payload has to be encrypted using JWE. This can be done by
extenting our script as follows:

```py
import json
from joserfc import jwe

# Encryption using AESGCM
rgb_led = json.dumps({"red": 255, "green": 0, "blue": 0})
protected = {'alg': 'dir', 'enc': 'A256GCM'}
rgb_led_payload = jwe.encrypt_compact(protected, rgb_led, key)
print(f"RGB LED Payload: {rgb_led_payload}")

client.publish(f"/dotbots/{topic}/command/0000/{dotbot_addr}/0/rgb_led", rgb_led_payload)
```

And the RGB LED should turn red.

## Move one DotBot

Let's now try to make the DotBot move forward briefly using the `move_raw`
command:

```py
move = json.dumps({"left_x": 0, "left_y": 80, "right_x": 0, "right_y": 80})
move_payload = jwe.encrypt_compact(protected, move, key)
print(f"Move Payload: {move_payload}")
client.publish(f"/dotbots/{topic}/command/0000/{dotbot_addr}/0/move_raw", move_payload, qos=1)
```

And the DotBot should move forward during 200ms!
