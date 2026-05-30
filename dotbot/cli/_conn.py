# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Parse a `--conn` connection string into a typed result.

`dotbot controller --conn CONNECTION` takes one discriminated
connection string whose *form* selects the kind of connection - the
`git remote` / `docker -H` / MAVSDK `add_any_connection()` pattern:

| value                                  | kind        |
|----------------------------------------|-------------|
| `mqtts://host:port` / `mqtt://host:port` | `mqtt`    |
| `/dev/ttyACM0`, `/dev/tty.usbmodem…`, `COM3` | `serial` |
| `simulator` / `sim`                    | `simulator` |

Keeping this a pure function (no Click, no I/O) so it's exhaustively
unit-testable without hardware.
"""

from dataclasses import dataclass
from typing import Optional

from marilib.communication_adapter import parse_mqtt_url


@dataclass(frozen=True)
class ConnectionSpec:
    """Result of parsing a `--conn` value.

    `kind` is one of "mqtt" | "serial" | "simulator". The other fields
    are populated per kind:
      - mqtt:      host, port, use_tls
      - serial:    serial_port
      - simulator: (no extra fields; robot type is a separate flag)
    """

    kind: str
    host: Optional[str] = None
    port: Optional[int] = None
    use_tls: bool = False
    serial_port: Optional[str] = None


class ConnError(ValueError):
    """Raised when a `--conn` value can't be parsed."""


# Accepted spellings for the simulator (documented: `simulator`).
_SIMULATOR_VALUES = {"simulator", "sim"}


def parse_connection(value: str) -> ConnectionSpec:
    """Parse a `--conn` string. Raises ConnError on a malformed value."""
    if not value:
        raise ConnError("empty connection string")

    lowered = value.strip().lower()

    # Simulator — a bare keyword.
    if lowered in _SIMULATOR_VALUES:
        return ConnectionSpec(kind="simulator")

    # MQTT — discriminated by the mqtt:// / mqtts:// scheme. Delegate the
    # url → parts mapping to marilib's parse_mqtt_url, the single source of
    # truth shared with swarmit (so the default-port logic can't drift).
    if lowered.startswith(("mqtt://", "mqtts://")):
        host, port, use_tls, _user, _pass = parse_mqtt_url(value)
        if not host:
            raise ConnError(f"no host in MQTT connection string: {value!r}")
        return ConnectionSpec(kind="mqtt", host=host, port=port, use_tls=use_tls)

    # Anything else that has a `scheme://` we don't recognize is an error,
    # rather than being silently treated as a device path.
    if "://" in value:
        raise ConnError(
            f"unrecognized connection scheme in {value!r} "
            "(expected mqtt:// or mqtts://, a device path, or 'simulator')"
        )

    # Otherwise: treat as a serial device path (`/dev/ttyACM0`, `COM3`, …).
    # Plain path (no `serial://` scheme) so shell tab-completion works.
    return ConnectionSpec(kind="serial", serial_port=value)


def needs_swarm_id(parsed: ConnectionSpec) -> bool:
    """True if this connection requires `--swarm-id`.

    Only MQTT does: the broker carries traffic for many swarms, and the
    swarm id selects the topic namespace. A serial gateway already
    belongs to one swarm; a simulator has none.
    """
    return parsed.kind == "mqtt"
