# MQTT

Talk to the swarm from any language that speaks MQTT — no Python, no SDK. This
is the low-magic integration path: subscribe to bot state, publish commands, on
standard topics. For Python, the [REST API](rest.md) is usually simpler.

## How it works

The MQTT surface is provided by the **qrkey bridge**, a small process that runs
next to the [controller](../guides/controller.md) and mirrors its state onto an
MQTT broker:

```bash
dotbot run controller            # one terminal — drives the gateway
dotbot run demo qr -w            # another terminal — the qrkey MQTT bridge
```

The bridge connects to a broker (a public HiveMQ instance by default) and:

- **publishes** notifications (state changes, position updates) for consumers to read;
- **subscribes** to command topics, forwarding what it receives to the controller.

So an external consumer subscribes to notifications and publishes commands — it
never talks to the controller directly.

## Topic vocabulary

Every topic is rooted at `/pydotbot/<secret-topic>`, where `<secret-topic>` is a
base64 string derived from the current PIN code (see [Secured brokers](#secured-brokers)).

| Topic (under `/pydotbot/<secret-topic>`) | Direction | Purpose |
|---|---|---|
| `/command/<swarm-id>/<address>/<app>/<cmd>` | you publish | drive a bot (`move_raw`, `rgb_led`, `waypoints`, `clear_position_history`) |
| `/notify` | you subscribe | controller state changes + position updates |
| `/request` / `/reply/<id>` | request/reply | one-shot queries (e.g. list of bots, map size) |

Command-topic fields:

- `<swarm-id>` — 4-hex swarm identifier (bots behind one gateway), e.g. `0000`.
- `<address>` — 16-hex DotBot address, e.g. `9903ef26257feb31`.
- `<app>` — application type: `0` = DotBot, `1` = SailBot.
- `<cmd>` — the command name (last segment).

Get a bot's address and the swarm id from the controller's
[REST API](rest.md) (`GET /controller/dotbots`).

## Send commands

Payloads are JSON. Drive a bot forward and turn its LED red:

```bash
# move_raw — left_y / right_y drive the wheels, values in [-100, 100]
mosquitto_pub -h <broker> \
  -t '/pydotbot/<secret-topic>/command/0000/9903ef26257feb31/0/move_raw' \
  -m '{"left_x": 0, "left_y": 80, "right_x": 0, "right_y": 80}'

# rgb_led — 0..255 per channel
mosquitto_pub -h <broker> \
  -t '/pydotbot/<secret-topic>/command/0000/9903ef26257feb31/0/rgb_led' \
  -m '{"red": 255, "green": 0, "blue": 0}'
```

## Read state

```bash
mosquitto_sub -h <broker> -t '/pydotbot/<secret-topic>/notify' | jq
```

Notifications carry a `cmd` field: `RELOAD` (refetch all bots), `UPDATE`
(per-bot state delta, incl. LH2 position), `PIN_CODE_UPDATE` (the secret topic
and key are about to rotate — see below).

## Secured brokers

Topics and payloads are not in the clear. The secret topic and a symmetric
AES-GCM key are both derived from a rotating 8-digit PIN code; the PIN refreshes
periodically (with a grace window), so the topic and key change over time, and
all payloads are encrypted. A consumer therefore needs to derive the topic/key
from the current PIN and decrypt — the bare `mosquitto_pub/sub` calls above are
the shape of the integration, not a drop-in for a live secured broker.

The PIN and the full key-derivation + encryption scheme are
[qrkey](https://github.com/DotBots/qrkey)'s job. Use it (or a port of its
derivation) rather than reimplementing the crypto. A complete working consumer —
deriving the topic/key, encrypting commands, decrypting notifications, and
rotating on `PIN_CODE_UPDATE` — ships as the `qrkey_demo` example
(`dotbot run demo qr`); read its source as the reference implementation.

For a fully language-neutral bridge that publishes plain dotbot-semantic topics
(`pydotbot/<addr>/position`, `.../cmd/move_raw`) with no per-message crypto, see
the [Python SDK](../sdk/index.md) roadmap — that bridge is planned, not yet shipped.

## See also

- [REST API](rest.md) — the controller surface the bridge mirrors.
- [`dotbot run`](../cli/run.md) — `run controller` and `run demo qr`.
- [Controller guide](../guides/controller.md) — what the controller does.
