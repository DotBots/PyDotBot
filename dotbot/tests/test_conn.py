# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the `--conn` connection-string parser (`dotbot.cli._conn`)."""

import pytest

from dotbot.cli._conn import ConnError, needs_swarm_id, parse_connection


def test_parse_mqtt_tls():
    c = parse_connection("mqtts://argus.paris.inria.fr:8883")
    assert c.kind == "mqtt"
    assert c.host == "argus.paris.inria.fr"
    assert c.port == 8883
    assert c.use_tls is True


def test_parse_mqtt_plain():
    c = parse_connection("mqtt://localhost:1883")
    assert c.kind == "mqtt"
    assert c.host == "localhost"
    assert c.port == 1883
    assert c.use_tls is False


def test_parse_mqtt_default_ports():
    # No explicit port → 8883 for TLS, 1883 for plain.
    assert parse_connection("mqtts://host").port == 8883
    assert parse_connection("mqtt://host").port == 1883


def test_parse_mqtt_missing_host_errors():
    with pytest.raises(ConnError):
        parse_connection("mqtts://:8883")


def test_parse_serial_device_path():
    c = parse_connection("/dev/ttyACM0")
    assert c.kind == "serial"
    assert c.serial_port == "/dev/ttyACM0"


def test_parse_serial_macos_usbmodem():
    c = parse_connection("/dev/tty.usbmodem0007745943981")
    assert c.kind == "serial"
    assert c.serial_port == "/dev/tty.usbmodem0007745943981"


def test_parse_serial_windows_com():
    c = parse_connection("COM3")
    assert c.kind == "serial"
    assert c.serial_port == "COM3"


def test_parse_simulator_both_spellings():
    assert parse_connection("simulator").kind == "simulator"
    assert parse_connection("sim").kind == "simulator"


def test_parse_simulator_case_insensitive():
    assert parse_connection("Simulator").kind == "simulator"


def test_parse_unknown_scheme_errors():
    # A scheme we don't recognize is an error, not a silent serial path.
    with pytest.raises(ConnError):
        parse_connection("http://example.com:8000")
    with pytest.raises(ConnError):
        parse_connection("serial:///dev/ttyACM0")  # scheme deliberately unsupported


def test_parse_empty_errors():
    with pytest.raises(ConnError):
        parse_connection("")


def test_needs_swarm_id_only_for_mqtt():
    assert needs_swarm_id(parse_connection("mqtts://host:8883")) is True
    assert needs_swarm_id(parse_connection("/dev/ttyACM0")) is False
    assert needs_swarm_id(parse_connection("simulator")) is False
