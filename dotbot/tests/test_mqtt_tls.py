# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for opting out of broker certificate checking.

The substitution is made on paho's class, so every test restores it: a leak
would silently disarm certificate checking for the rest of the session.
`_ssl_context` is paho's own attribute and the only way to read back the
context a client was given.
"""

import ssl
import sys
import types

import paho.mqtt.client as mqtt
import pytest
from click.testing import CliRunner

from dotbot.config import Resolved
from dotbot.mqtt_tls import (
    INSECURE_ENV,
    Credentials,
    allow_unverified_broker,
    broker_credentials,
    insecure_requested,
)


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


def test_the_dispatcher_arms_the_opt_out_for_every_subcommand(
    monkeypatch, paho_restored, tmp_path
):
    """Guards `dotbot swarm ...`, which builds its client inside swarmit."""
    from dotbot.cli.main import cli

    monkeypatch.setenv(INSECURE_ENV, "1")
    config = tmp_path / "dotbot.toml"
    config.write_text('conn = "simulator"\n')

    result = CliRunner().invoke(cli, ["-c", str(config), "fw", "--help"])

    assert result.exit_code == 0, result.output
    assert default_context().verify_mode == ssl.CERT_NONE


def _stub_swarmit(monkeypatch, build_client):
    """Stand in for swarmit, whose protocol registry cannot load here."""
    modules = {
        "swarmit": types.ModuleType("swarmit"),
        "swarmit.cli": types.ModuleType("swarmit.cli"),
        "swarmit.cli.main": types.ModuleType("swarmit.cli.main"),
        "swarmit.client": types.ModuleType("swarmit.client"),
        "swarmit.testbed": types.ModuleType("swarmit.testbed"),
        "swarmit.testbed.controller": types.ModuleType("swarmit.testbed.controller"),
    }
    modules["swarmit.cli.main"].DEFAULTS = {
        "serial_port": "/dev/ttyACM0",
        "baudrate": 1000000,
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_use_tls": False,
        "adapter": "cloud",
        "swarmit_network_id": "0000",
    }
    modules["swarmit.cli.main"]._conn_to_config = lambda conn, swarm_id: {
        "mqtt_host": "broker",
        "mqtt_port": 8883,
        "mqtt_use_tls": True,
        "swarmit_network_id": swarm_id,
    }
    modules["swarmit.testbed.controller"].ControllerSettings = lambda **kwargs: kwargs
    modules["swarmit.client"].build_client = build_client
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_the_fleet_builder_drops_verification_before_it_connects(
    monkeypatch, paho_restored
):
    """swarmit connects inside `build_client`, so arming after it is too late."""
    from dotbot.swarm_client import build_swarmit_client

    monkeypatch.setenv(INSECURE_ENV, "1")
    seen = {}

    def build_client(settings):
        seen["verify_mode"] = default_context().verify_mode
        return "client"

    _stub_swarmit(monkeypatch, build_client)

    assert build_swarmit_client("mqtts://broker:8883", "A001") == "client"
    assert seen["verify_mode"] == ssl.CERT_NONE


def test_asking_twice_does_not_wrap_twice(monkeypatch, paho_restored):
    monkeypatch.setenv(INSECURE_ENV, "1")

    assert allow_unverified_broker() is True
    once = mqtt.Client.tls_set_context
    assert allow_unverified_broker() is True

    assert mqtt.Client.tls_set_context is once


# --- which broker gets the credentials ---------------------------------------

_LOGIN = {"DOTBOT_MQTT_USER": "me", "DOTBOT_MQTT_PASS": "secret"}
_ARGUS = "mqtts://argus.example:8883"


def _site(conn, trust=None, distrust=None):
    return Resolved(conn, "site", "site c405-arena", (), trust, distrust)


@pytest.mark.parametrize(
    "conn, reason",
    [
        (Resolved(_ARGUS, "flag", "--conn"), "you named it (--conn)"),
        (Resolved(_ARGUS, "file", "dotbot.toml"), "you named it (dotbot.toml)"),
        (_site(_ARGUS, "approved at site add"), "approved at site add"),
        (_site("mqtt://localhost:1883"), "it runs on this machine"),
        (_site("mqtt://127.0.0.1"), "it runs on this machine"),
    ],
    ids=["a flag", "your file", "an approved site", "localhost", "loopback"],
)
def test_credentials_are_sent(conn, reason):
    got = broker_credentials(conn, _LOGIN)
    assert (got.username, got.password, got.withheld) == ("me", "secret", None)
    assert got.reason == reason


def test_credentials_are_refused_to_a_broker_a_site_chose_without_approval():
    why = "site c405-arena's broker was never approved; approve it with ..."
    got = broker_credentials(_site(_ARGUS, distrust=why), _LOGIN)
    assert got.username is None and got.password is None
    assert (
        got.withheld
        == f"not sending DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS to argus.example: {why}"
    )


@pytest.mark.parametrize("kind", ["flag", "site"])
def test_credentials_never_go_over_plain_mqtt_to_a_remote_host(kind):
    conn = Resolved("mqtt://argus.example:1883", kind, "x", (), "approved at site add")
    got = broker_credentials(conn, _LOGIN)
    assert got.username is None
    assert "plain mqtt://" in got.withheld


def test_no_login_in_the_env_is_nothing_to_decide():
    assert broker_credentials(_site("mqtts://h"), {}) == Credentials()


def test_a_non_broker_conn_takes_no_credentials():
    assert (
        broker_credentials(Resolved("simulator", "flag", "--conn"), _LOGIN)
        == Credentials()
    )


# --- a [login] saved for a host ----------------------------------------------

_SAVED = {"Argus.Example": types.SimpleNamespace(user="me", password="hunter2")}


def test_a_saved_login_goes_to_its_host_whoever_chose_the_broker():
    why = "site c405-arena's broker was never approved"
    got = broker_credentials(_site(_ARGUS, distrust=why), {}, _SAVED)
    assert (got.username, got.password, got.withheld) == ("me", "hunter2", None)
    assert got.reason == "your [login] for argus.example"


def test_a_saved_login_never_reaches_another_host():
    conn = Resolved("mqtts://evil.example:8883", "site", "site x", (), "approved")
    assert broker_credentials(conn, {}, _SAVED) == Credentials()


def test_a_saved_login_never_goes_over_plain_mqtt_to_a_remote_host():
    conn = Resolved("mqtt://argus.example:1883", "flag", "--conn")
    got = broker_credentials(conn, {}, _SAVED)
    assert got.username is None
    assert "not sending your [login] for argus.example" in got.withheld


def test_the_env_login_wins_where_it_is_allowed_and_the_saved_one_elsewhere():
    named = broker_credentials(Resolved(_ARGUS, "flag", "--conn"), _LOGIN, _SAVED)
    assert named.username == "me" and named.password == "secret"
    unapproved = broker_credentials(_site(_ARGUS, distrust="no"), _LOGIN, _SAVED)
    assert unapproved.password == "hunter2" and unapproved.withheld is None
