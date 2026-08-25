# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot run gateway` — host-side Mari gateway bridge.

Runs on whatever computer the gateway firmware is plugged into (a
laptop for a starter setup, a Pi for a permanent install). Bridges UART
HDLC frames to/from an MQTT broker, so a `dotbot run controller --conn
mqtts://…` can reach the swarm from anywhere.

Thin re-mount of marilib's `mari-edge`: wraps a `MarilibEdge` with a
serial adapter and (optionally) an MQTT adapter. Without `--mqtt-url`
it just prints received frames (handy to sanity-check a freshly-flashed
gateway with zero MQTT infra); with `--mqtt-url` it bridges to the
broker. Frame printing is on by default in both modes (`--no-print` to
silence). Metrics probing is off (`metrics_probe_period=0`), so the
print-only mode is passive — it doesn't inject traffic onto the link.

Phase 1 is a raw bridge (mari frames + raw mari topics). DotBot-semantic
MQTT topics are a later phase, tracked in the controller-CLI-redesign
plan.
"""

import os
import time

import click

from dotbot import addr_to_hex
from dotbot.cli._cfg import from_config
from dotbot.cli._conn import parse_connection


def _run_gateway(port, mqtt_url, do_print):  # pragma: no cover - needs a gateway
    """Construct a MarilibEdge bridge and pump it until interrupted.

    Imports marilib lazily so `dotbot run gateway --help` is cheap and the
    command is importable without a serial port present.
    """
    from marilib.communication_adapter import MQTTAdapter, SerialAdapter
    from marilib.marilib_edge import MarilibEdge
    from marilib.model import EdgeEvent
    from marilib.serial_uart import get_default_port

    port = port or get_default_port()

    def on_event(event, event_data):
        if do_print and event == EdgeEvent.NODE_DATA:
            click.echo(
                f"<- {addr_to_hex(event_data.header.source)}: {event_data.payload.hex()}"
            )

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

    # metrics_probe_period=0 → MarilibEdge starts no metrics thread, so a
    # print-only run stays passive (no probe traffic on the serial link).
    mari = MarilibEdge(
        on_event,
        serial_interface=SerialAdapter(port),
        mqtt_interface=mqtt_interface,
        metrics_probe_period=0,
    )
    where = mqtt_url if mqtt_url else "(no broker — print only)"
    click.echo(f"dotbot run gateway: {port} <-> {where}", err=True)
    try:
        while True:
            mari.update()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        mari.close()


@click.command(
    name="gateway",
    help=(
        "Host-side Mari gateway bridge (UART <-> MQTT). Runs wherever the "
        "gateway firmware is plugged in. With --mqtt-url it bridges to the "
        "broker; without it, it just prints received frames. Printing is on "
        "by default (--no-print to silence)."
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
    help="MQTT broker to bridge to (`mqtts://host:port`). Absent → print-only.",
)
@click.option(
    "--print/--no-print",
    "do_print",
    default=True,
    help="Print received frames to stdout (default: on).",
)
@click.pass_context
def cmd(ctx, port, mqtt_url, do_print):
    """Run the gateway bridge."""
    if mqtt_url is None:
        # No --mqtt-url on the command line: fall back to the selected
        # deployment's (or config's) connection, but only when it names an
        # MQTT broker - a serial/simulator conn is not a broker to bridge to,
        # so we leave mqtt_url None and keep the print-only behavior.
        conn = from_config(ctx, "mqtt_url", "conn", "run")
        if conn and parse_connection(conn).kind == "mqtt":
            mqtt_url = conn
    _run_gateway(port, mqtt_url, do_print)
