# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the controller's `--conn` / `--swarm-id` CLI surface.

These exercise `_conn_to_settings` (pure translation + validation) and
the Click wiring, without starting a real controller / MQTT / serial.
"""

import click
import pytest

from dotbot.controller_app import _conn_to_settings


def test_mqtt_conn_maps_to_cloud_adapter():
    s = _conn_to_settings("mqtts://argus:8883", "1234", sim_is_dotbot=True)
    assert s["adapter"] == "cloud"
    assert s["mqtt_host"] == "argus"
    assert s["mqtt_port"] == 8883
    assert s["mqtt_use_tls"] is True
    assert s["network_id"] == "1234"


def test_mqtt_conn_without_swarm_id_errors():
    with pytest.raises(click.ClickException) as exc:
        _conn_to_settings("mqtts://argus:8883", None, sim_is_dotbot=True)
    assert "swarm-id" in str(exc.value)


def test_serial_conn_maps_to_edge_adapter_no_swarm_id_needed():
    s = _conn_to_settings("/dev/ttyACM0", None, sim_is_dotbot=True)
    assert s["adapter"] == "edge"
    assert s["port"] == "/dev/ttyACM0"
    # No swarm-id required, and none injected when absent.
    assert "network_id" not in s


def test_serial_conn_keeps_swarm_id_when_given():
    s = _conn_to_settings("/dev/ttyACM0", "00aa", sim_is_dotbot=True)
    assert s["adapter"] == "edge"
    assert s["network_id"] == "00aa"


def test_simulator_conn_maps_to_dotbot_simulator():
    s = _conn_to_settings("simulator", None, sim_is_dotbot=True)
    assert s["adapter"] == "dotbot-simulator"


def test_simulator_conn_sailbot():
    s = _conn_to_settings("simulator", None, sim_is_dotbot=False)
    assert s["adapter"] == "sailbot-simulator"


def test_sim_alias_spelling():
    assert _conn_to_settings("sim", None, sim_is_dotbot=True)["adapter"] == (
        "dotbot-simulator"
    )


def test_no_conn_errors_with_guidance():
    with pytest.raises(click.ClickException) as exc:
        _conn_to_settings(None, None, sim_is_dotbot=True)
    msg = str(exc.value)
    assert "mqtts://" in msg and "simulator" in msg


def test_malformed_conn_errors():
    with pytest.raises(click.ClickException):
        _conn_to_settings("http://nope:1", "1234", sim_is_dotbot=True)


def test_env_credentials_threaded_into_mqtt_settings(monkeypatch):
    monkeypatch.setenv("DOTBOT_MQTT_USER", "alice")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "s3cret")
    s = _conn_to_settings("mqtts://argus:8883", "1234", sim_is_dotbot=True)
    assert s["mqtt_username"] == "alice"
    assert s["mqtt_password"] == "s3cret"


def test_env_credentials_absent_are_none(monkeypatch):
    monkeypatch.delenv("DOTBOT_MQTT_USER", raising=False)
    monkeypatch.delenv("DOTBOT_MQTT_PASS", raising=False)
    s = _conn_to_settings("mqtts://argus:8883", "1234", sim_is_dotbot=True)
    assert s["mqtt_username"] is None
    assert s["mqtt_password"] is None
