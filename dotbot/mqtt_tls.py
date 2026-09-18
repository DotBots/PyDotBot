# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Connecting to a broker whose certificate does not validate.

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

from dotbot.logger import LOGGER

INSECURE_ENV = "DOTBOT_MQTT_INSECURE"
_TRUE = {"1", "true", "yes", "on"}


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
