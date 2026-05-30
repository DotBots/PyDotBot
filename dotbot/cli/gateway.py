# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot gateway` — host-side Mari gateway bridge.

Runs on whatever computer the gateway firmware is plugged into (a
laptop for a starter setup, a Pi for a permanent install). Bridges UART
HDLC frames to/from an MQTT broker, so a `dotbot controller --conn
mqtts://…` can reach the swarm from anywhere.

Thin re-mount of marilib's `mari-edge`: wraps a `MarilibEdge` with a
serial adapter and (optionally) an MQTT adapter. With no `--mqtt-url`
it runs in **local-stdout mode** — received frames print to stdout, so
a freshly-flashed gateway can be sanity-checked with zero MQTT infra.

Phase 1 is a raw bridge (mari frames + raw mari topics). DotBot-semantic
MQTT topics are a later phase, tracked in the controller-CLI-redesign
plan.
"""

import os
import time

import click


def _run_gateway(port, mqtt_url):  # pragma: no cover - needs a real gateway
    """Construct a MarilibEdge bridge and pump it until interrupted.

    Imports marilib lazily so `dotbot gateway --help` is cheap and the
    command is importable without a serial port present.
    """
    from marilib.communication_adapter import MQTTAdapter, SerialAdapter
    from marilib.marilib_edge import MarilibEdge
    from marilib.model import EdgeEvent
    from marilib.serial_uart import get_default_port

    port = port or get_default_port()
    stdout_mode = mqtt_url is None

    def on_event(event, event_data):
        # In local-stdout mode, surface received data frames so a fresh
        # gateway can be eyeballed without a broker.
        if stdout_mode and event == EdgeEvent.NODE_DATA:
            src = getattr(event_data.header, "source", 0)
            payload = getattr(event_data, "payload", b"")
            click.echo(f"<- {src:016x}: {bytes(payload).hex()}")

    mqtt_interface = None
    if mqtt_url is not None:
        # Broker credentials come from the environment (DOTBOT_MQTT_USER /
        # DOTBOT_MQTT_PASS); they override any user:pass in the URL.
        mqtt_interface = MQTTAdapter.from_url(
            mqtt_url,
            is_edge=True,
            username=os.environ.get("DOTBOT_MQTT_USER"),
            password=os.environ.get("DOTBOT_MQTT_PASS"),
        )

    mari = MarilibEdge(
        on_event,
        serial_interface=SerialAdapter(port),
        mqtt_interface=mqtt_interface,
    )
    where = mqtt_url if mqtt_url else "local-stdout"
    click.echo(f"dotbot gateway: {port} <-> {where}", err=True)
    try:
        while True:
            mari.update()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            mari.close()
        except Exception:  # pylint: disable=broad-except
            pass


@click.command(
    name="gateway",
    help=(
        "Host-side Mari gateway bridge (UART <-> MQTT). Runs wherever the "
        "gateway firmware is plugged in. Without --mqtt-url, prints received "
        "frames to stdout (local debug mode)."
    ),
)
@click.option(
    "-p",
    "--port",
    type=str,
    default=None,
    help="Serial port of the attached gateway firmware. Default: autodetect.",
)
@click.option(
    "-m",
    "--mqtt-url",
    type=str,
    default=None,
    help=(
        "MQTT broker to bridge to (`mqtts://host:port`). Absent → "
        "local-stdout debug mode."
    ),
)
def cmd(port, mqtt_url):
    """Run the gateway bridge."""
    _run_gateway(port, mqtt_url)
