# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Which broker gets the credentials, and one whose certificate does not validate.

`DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` go to a broker only when
`DOTBOT_MQTT_HOST` names it, the person named the broker themselves (a flag,
the env, their own config file) or it runs on this machine: never to one a
shared site pack chose on its own, and never over plain `mqtt://` to another
host.

`DOTBOT_MQTT_INSECURE=1` makes every TLS broker connection this process
opens skip certificate verification. It is the same env-only channel the
broker credentials arrive on, and it exists for a bench whose broker
certificate has expired or is self-signed.

The connection is still encrypted, but the broker is no longer
authenticated, so credentials and traffic are exposed to anything that can
intercept the route. Set it for a bench session, not in a config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotbot.logger import LOGGER

INSECURE_ENV = "DOTBOT_MQTT_INSECURE"
USER_ENV = "DOTBOT_MQTT_USER"
PASS_ENV = "DOTBOT_MQTT_PASS"
HOST_ENV = "DOTBOT_MQTT_HOST"
_TRUE = {"1", "true", "yes", "on"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class Credentials:
    """The broker login to send, or why it is withheld.

    `username` / `password` are None when there is nothing to send;
    `withheld` is the warning to print when the environment has a login this
    broker does not get.
    """

    username: str | None = None
    password: str | None = None
    withheld: str | None = None


def broker_credentials(
    conn: str | None,
    user_set: bool,
    origin: str = "",
    environ: Mapping[str, str] = os.environ,
) -> Credentials:
    """Whether the env's broker login goes to the broker `conn` names.

    `user_set` is True when the person named the broker (flag, env, their own
    file); `origin` names where it came from otherwise, e.g. `site c405-arena`.
    """
    user, password = environ.get(USER_ENV), environ.get(PASS_ENV)
    if user is None and password is None:
        return Credentials()
    if not conn or not conn.strip().lower().startswith(("mqtt://", "mqtts://")):
        return Credentials()
    from marilib.communication_adapter import parse_mqtt_url

    host, _port, use_tls, _user, _pass = parse_mqtt_url(conn)
    if not use_tls and host not in _LOCAL_HOSTS:
        return Credentials(
            withheld=(
                f"not sending {USER_ENV} / {PASS_ENV} to {host}: plain mqtt:// "
                "would carry them unencrypted; use mqtts://"
            )
        )
    if host in _LOCAL_HOSTS or environ.get(HOST_ENV) == host or user_set:
        return Credentials(user, password)
    return Credentials(
        withheld=(
            f"not sending {USER_ENV} / {PASS_ENV} to {host}, which {origin or 'a site'} "
            f"chose; if they are meant for it, set {HOST_ENV}={host}"
        )
    )


def insecure_requested() -> bool:
    """Whether the environment asks for an unverified broker."""
    return os.environ.get(INSECURE_ENV, "").strip().lower() in _TRUE


def allow_unverified_broker() -> bool:
    """Drop certificate verification for later TLS connections, if asked.

    Returns whether verification is off. Callers that build an MQTT client
    call this first; with the variable unset it does nothing at all.

    marilib asks paho for a default context, so the substitution happens
    where that default is built rather than at any one call site, which is
    what makes one call cover the controller and the gateway bridge alike.
    """
    if not insecure_requested():
        return False

    import ssl

    import paho.mqtt.client as mqtt

    if getattr(mqtt.Client.tls_set_context, "_dotbot_insecure", False):
        return True

    verifying = mqtt.Client.tls_set_context

    def tls_set_context(self, context=None):
        if context is None:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return verifying(self, context)

    tls_set_context._dotbot_insecure = True
    mqtt.Client.tls_set_context = tls_set_context
    LOGGER.warning(
        "Broker certificate checking is OFF: the connection is encrypted but "
        "the broker is not authenticated, and credentials go over it. "
        "Unset %s once the broker's certificate is valid.",
        INSECURE_ENV,
    )
    return True
