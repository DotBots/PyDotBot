# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
# SPDX-License-Identifier: BSD-3-Clause

"""Encrypted-MQTT phone bridge for PyDotBot, built on top of the
standalone `qrkey` library (see https://github.com/DotBots/qrkey).

This example consumes qrkey-decrypted MQTT commands from a phone and
forwards them to a running PyDotBot controller via the controller's
REST API. The controller stays unaware of qrkey.
"""

from dotbot.examples.qrkey_demo.client import (  # noqa: F401
    AsyncWorker,
    QrKeyClient,
    QrKeyClientSettings,
)
