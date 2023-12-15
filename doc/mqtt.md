# MQTT

For a brief introduction to MQTT, have a look at the
[Eclipse Mosquitto manual page](https://mosquitto.org/man/mqtt-7.html).

When `dotbot-controller` is started with the `--use-mqtt` flag set, it connects
an MQTT broker using the connection settings defined in a `.env` file.

See `.env.example` for the list of possible options.

## Prerequisites

Make sure you already followed the [getting started](getting_started) page and
have a functional setup with `dotbot-controller` running and connected to a
nRF DK gateway.

To interact with the MQTT broker, you will use the
mosquitto-clients command line tools from [Eclipse Mosquitto](https://mosquitto.org/):
- [mosquitto_pub](https://mosquitto.org/man/mosquitto_pub-1.html) to send
  commands to the DotBot
- [mosquitto_sub](https://mosquitto.org/man/mosquitto_sub-1.html) to receive
  notifications and updates about the DotBot from the controller

On a Linux machine (Debian, Ubuntu), you can install them using apt:
```
sudo apt install mosquitto-clients
```

## The basics

It's as easy as running the following command:

```
dotbot-controller --use-mqtt
```

The logs should contain information about the MQTT broker connection and the
topic subscriptions:

```
Welcome to the DotBots controller (version: <version>).
2023-12-14T15:09:54.264648Z [info     ] Lighthouse initialized         [pydotbot] context=dotbot.lighthouse2
2023-12-14T15:09:54.265342Z [info     ] Starting web server            [pydotbot] context=dotbot.controller
2023-12-14T15:09:54.278344Z [info     ] Serial port thread started     [pydotbot] context=dotbot.serial_interface
2023-12-14T15:09:54.437230Z [info     ] Connected                      [pydotbot] context=dotbot.mqtt flags=0 rc=0 receive_maximum=[10] topic_alias_maximum=[5]
2023-12-14T15:09:54.453387Z [info     ] Subscribed to /dotbots/+/+/+/move_raw [pydotbot] context=dotbot.mqtt qos=(0,)
2023-12-14T15:09:54.460119Z [info     ] Subscribed to /dotbots/+/+/+/rgb_led [pydotbot] context=dotbot.mqtt qos=(0,)
```

Now the controller is listening to commands published on the
`/dotbots/+/+/+/move_raw` and `/dotbots/+/+/+/rgb_led` topics.

A command topic can be described as follows: `/dotbots/<swarm-id>/<dotbot-address>/<application>/<command>` where:
- `swarm-id` is a 4 hexadecimal string (2B long) identifier corresponding to a swarm,
  typically all DotBots behind a single gateway
- `dotbot-address` is a 18 hexadecimal string (8B long) unique identifier of a DotBot,
- `application` is the type of application (0: DotBot, 1: SailBot)
- `command` is the type of command (`move_raw` or `rgb_led`)

## Getting information about DotBots in a swarm

Using `mosquitto_sub` you can subscribe to information topics published by the
controller:
- `/dotbots/<swarm-id>/notifications` to receive all notifications from a give swarm
- `/dotbots/<swarm-id>` to receive every seconds the list of available DotBots in the swarm

For example, when one Dotbot appears in the swarm (here swarm-id is `0000`):

```
$ mosquitto_sub -h <broker host> -p <broker port> -u <username> -P <password> -t /dotbots/0000
[]
[]
[{"address": "9903ef26257feb31", "application": 0, "swarm": "0000", "status": 0, "mode": 0, "last_seen": 1702567131.9084547, "waypoints": [], "waypoints_threshold": 40, "position_history": []}]
[{"address": "9903ef26257feb31", "application": 0, "swarm": "0000", "status": 0, "mode": 0, "last_seen": 1702567132.708384, "waypoints": [], "waypoints_threshold": 40, "position_history": []}]
[{"address": "9903ef26257feb31", "application": 0, "swarm": "0000", "status": 0, "mode": 0, "last_seen": 1702567133.5077198, "waypoints": [], "waypoints_threshold": 40, "position_history": []}]
[{"address": "9903ef26257feb31", "application": 0, "swarm": "0000", "status": 0, "mode": 0, "last_seen": 1702567134.3075092, "waypoints": [], "waypoints_threshold": 40, "position_history": []}]
[{"address": "9903ef26257feb31", "application": 0, "swarm": "0000", "status": 0, "mode": 0, "last_seen": 1702567135.9077396, "waypoints": [], "waypoints_threshold": 40, "position_history": []}]
```

We see that there's only one DotBot in the swarm with address `9903ef26257feb31`,
application is 0 (DotBot) and its status is 0 (Alive).

We would also receive notifications, here a "reload" command, when the DotBot appears:

```
$ mosquitto_sub -h <broker host> -p <broker port> -u <username> -P <password> -t /dotbots/0000/notifications
{"cmd": 1}
{"cmd": 1}
```

## Change the color of the RGB LED

Let's change the RGB LED color of the DotBot by send an `rgb_led` command. This
command takes a payload parameter containing a json with the red, green and blue
values to apply:

```
mosquitto_pub -h <broker host> -p <broker port> -u <username> -P <password> -t /dotbots/0000/9903ef26257feb31/0/rgb_led -m '{"red": 255, "green": 0, "blue": 0}'
```

And the RGB LED should turn red.

## Move one DotBot

Let's now try to make the DotBot move forward briefly using the `move_raw`
command:

```
mosquitto_pub -h <broker host> -p <broker port> -u <username> -P <password> -t /dotbots/0000/9903ef26257feb31/0/move_raw -m '{"left_x": 0, "left_y": 80, "right_x": 0, "right_y": 80}'
```

And the DotBot should move forward during 200ms!
