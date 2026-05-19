# qrkey demo

A museum / open-house demo: visitors scan a QR code with their phone,
get an encrypted MQTT channel into the testbed, and can drive one of
the DotBots. The PIN encoded in the QR rotates periodically; an
encrypted topic prefix isolates each rotation.

**This is an example, not a core controller feature.** The controller
(`dotbot-controller`) knows nothing about qrkey. The example is a
separate process that consumes the controller's REST/WebSocket API
exactly like any third-party script would.

## Running

Two terminals. In one, the controller (production / testbed service):

```bash
dotbot-controller -a cloud -H argus.paris.inria.fr -s 1234
```

In the other, the demo:

```bash
python -m dotbot.examples.qrkey_demo
```

The demo's FastAPI serves on `http://localhost:8080` by default:

- `GET /pin_code` — current rotating PIN
- `GET /pin_code/qr_code` — the scannable QR image (SVG)
- `WS  /ws` — pin-rotation notifications for the desktop QR display

The QR encoded URL points at a phone-friendly UI (default:
`https://dotbots.github.io/PyDotBot`); set `FRONTEND_BASE_URL=…` to
override (e.g. point at your laptop's LAN IP for local-only testing).

## Architecture

```
┌─────────────┐ encrypted MQTT (AES-GCM, PIN-derived topic)
│   phone     │ ────────────────────────┐
│  (browser)  │                         ▼
└─────────────┘                  ┌──────────────┐
                                 │ MQTT broker  │ (e.g. mosquitto, HiveMQ)
                                 └──────┬───────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │  qrkey_demo (this code)   │
                          │  - decrypts payloads      │
                          │  - validates timestamps   │
                          │  - calls controller REST  │
                          └─────────────┬─────────────┘
                                        │ HTTP/WS
                          ┌─────────────▼─────────────┐
                          │   dotbot-controller       │
                          │   (no qrkey awareness)    │
                          └───────────────────────────┘
```

The controller is **completely agnostic** to the demo. Stop the demo
and the controller is unaffected; if the broker is unreachable, the
demo logs and retries — the controller never blocks on it.

## Configuration

Settings come from env vars (or a `.env` file in the working
directory):

- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USE_SSL`, `MQTT_USERNAME`,
  `MQTT_PASSWORD` — broker connection.
- `MQTT_WS_PORT` — WebSocket port the **phone** uses to reach the
  broker (e.g. 1884 for hivemq).
- `FRONTEND_BASE_URL` — where the QR points the phone (gh-pages by
  default).

PIN rotation defaults to 2h with a 15min grace overlap (vs. upstream
qrkey's 15min/2min). This example overrides those at import time
because the museum/open-house UX assumes "scan QR, walk away with
phone, come back later." See `client.py` for the override site.

## Dependency on `qrkey`

This example is a thin client of the standalone `qrkey` package
(https://github.com/DotBots/qrkey). All crypto, MQTT bridging, PIN
rotation, and the FastAPI mount come from there; this directory only
contains the PyDotBot-specific REST-forwarding subscriber and the
Click CLI. Upgrading qrkey means upgrading its PyPI version in
PyDotBot's `pyproject.toml` — no vendored copy to keep in sync.

`test_crypto.py` pins one regression check: that whichever qrkey
version PyDotBot depends on still derives the same key/topic from a
given PIN as qrkey 0.12.1 did, so phones holding existing QRs keep
connecting. Detailed crypto tests live upstream in the qrkey repo.
