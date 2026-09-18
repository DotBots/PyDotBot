# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for opting out of broker certificate checking.

The substitution is made on paho's class, so every test restores it: a leak
would silently disarm certificate checking for the rest of the session.
`_ssl_context` is paho's own attribute and the only way to read back the
context a client was given.
"""

import ssl

import paho.mqtt.client as mqtt
import pytest

from dotbot.mqtt_tls import INSECURE_ENV, allow_unverified_broker, insecure_requested


@pytest.fixture
def paho_restored():
    original = mqtt.Client.tls_set_context
    yield
    mqtt.Client.tls_set_context = original


def default_context():
    """The context a client gets when it asks for the default, as marilib does."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.tls_set_context(context=None)
    return client._ssl_context


def test_an_unset_environment_still_verifies_the_broker(monkeypatch, paho_restored):
    monkeypatch.delenv(INSECURE_ENV, raising=False)

    assert insecure_requested() is False
    assert allow_unverified_broker() is False

    context = default_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_the_flag_drops_verification(monkeypatch, paho_restored, value):
    monkeypatch.setenv(INSECURE_ENV, value)

    assert insecure_requested() is True
    assert allow_unverified_broker() is True

    context = default_context()
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


@pytest.mark.parametrize("value", ["", "0", "no", "off", "maybe"])
def test_anything_else_leaves_verification_on(monkeypatch, paho_restored, value):
    monkeypatch.setenv(INSECURE_ENV, value)

    assert insecure_requested() is False
    assert allow_unverified_broker() is False
    assert default_context().verify_mode == ssl.CERT_REQUIRED


def test_a_context_the_caller_built_is_passed_through(monkeypatch, paho_restored):
    """Only the default is substituted, so an explicit context still stands."""
    monkeypatch.setenv(INSECURE_ENV, "1")
    allow_unverified_broker()

    mine = ssl.create_default_context()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.tls_set_context(context=mine)

    assert client._ssl_context is mine
    assert client._ssl_context.verify_mode == ssl.CERT_REQUIRED


def test_asking_twice_does_not_wrap_twice(monkeypatch, paho_restored):
    monkeypatch.setenv(INSECURE_ENV, "1")

    assert allow_unverified_broker() is True
    once = mqtt.Client.tls_set_context
    assert allow_unverified_broker() is True

    assert mqtt.Client.tls_set_context is once
