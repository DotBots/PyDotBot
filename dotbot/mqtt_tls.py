# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Which broker gets a login, and one whose certificate does not validate.

A login comes from the `[login."<host>"]` table of ~/.dotbot/dotbot.toml,
which only that host's broker ever gets, or from `DOTBOT_MQTT_USER` /
`DOTBOT_MQTT_PASS`. The env's login goes to a broker the person named (a
flag, the env, their own config files), a site pack's broker they approved
at `dotbot site add` or that sits beside their project or at a path they
named, and one on this machine. Neither goes over plain `mqtt://` to another
host.

`DOTBOT_MQTT_INSECURE=1` makes every TLS broker connection this process
opens skip certificate verification. It exists for a bench whose broker
certificate has expired or is self-signed, and is env-only so it is never
left on: the connection is still encrypted, but the broker is no longer
authenticated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from dotbot.logger import LOGGER

if TYPE_CHECKING:
    from dotbot.config import Resolved

INSECURE_ENV = "DOTBOT_MQTT_INSECURE"
USER_ENV = "DOTBOT_MQTT_USER"
PASS_ENV = "DOTBOT_MQTT_PASS"
_TRUE = {"1", "true", "yes", "on"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class Credentials:
    """The broker login to send and why, or why it is withheld.

    `username` / `password` are None when there is nothing to send;
    `reason` says why this broker gets them; `withheld` is the warning to
    print when the environment has a login this broker does not get.
    """

    username: str | None = None
    password: str | None = None
    reason: str | None = None
    withheld: str | None = None


def _host_login(logins: Mapping[str, Any] | None, host: str) -> Any:
    for name, login in (logins or {}).items():
        if name.strip().lower() == host.lower():
            return login
    return None


def broker_credentials(
    conn: Resolved | None,
    environ: Mapping[str, str] = os.environ,
    logins: Mapping[str, Any] | None = None,
) -> Credentials:
    """The login the broker `conn` names gets: the env's when it is allowed
    there, else the `[login]` entry for its host (`logins`)."""
    url = conn.value if conn is not None else None
    if not isinstance(url, str) or not url.strip().lower().startswith(
        ("mqtt://", "mqtts://")
    ):
        return Credentials()
    from marilib.communication_adapter import parse_mqtt_url

    host, _port, use_tls, _user, _pass = parse_mqtt_url(url)
    local = host in LOCAL_HOSTS
    user, password = environ.get(USER_ENV), environ.get(PASS_ENV)
    login = _host_login(logins, host)
    withheld = None
    if user is not None or password is not None:
        if local:
            return Credentials(user, password, reason="it runs on this machine")
        if not use_tls:
            withheld = (
                f"not sending {USER_ENV} / {PASS_ENV} to {host}: plain mqtt:// "
                "would carry them unencrypted; use mqtts://"
            )
        elif conn.trust:
            return Credentials(user, password, reason=conn.trust)
        else:
            why = conn.site_distrust or f"{conn.source} chose it"
            withheld = f"not sending {USER_ENV} / {PASS_ENV} to {host}: {why}"
    if login is not None:
        if local or use_tls:
            return Credentials(
                login.user, login.password, reason=f"your [login] for {host}"
            )
        withheld = (
            f"not sending your [login] for {host}: plain mqtt:// would carry "
            "it unencrypted; use mqtts://"
        )
    return Credentials(withheld=withheld)


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
