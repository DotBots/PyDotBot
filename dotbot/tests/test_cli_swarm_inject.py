# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot swarm` config -> swarmit flag injection.

Tests the pure helper (`_swarm_inject`) so swarmit itself is never imported -
its protocol registry collides with PyDotBot's in a shared test process (the
full `dotbot swarm` invocation is covered by the subprocess test in
`test_cli_dispatcher`).
"""

import pytest

from dotbot.cli._swarm_inject import inject_config
from dotbot.config import DotbotConfig


@pytest.fixture(autouse=True)
def _clean_conn_env(monkeypatch):
    # The resolver also reads env; clear the swarm/conn vars for determinism.
    for var in (
        "DOTBOT_CONN",
        "DOTBOT_SWARM_CONN",
        "DOTBOT_SWARM_ID",
        "DOTBOT_SWARM_SWARM_ID",
    ):
        monkeypatch.delenv(var, raising=False)


def _obj(**kw):
    return {"config": DotbotConfig(**kw), "deployment": None}


def test_injects_conn_and_swarm_id():
    out = inject_config(["status"], _obj(conn="mqtts://b:8883", swarm_id="1234"))
    assert out == ["--conn", "mqtts://b:8883", "--swarm-id", "1234", "status"]


def test_swarm_id_only():
    out = inject_config(["status"], _obj(swarm_id="1234"))
    assert out == ["--swarm-id", "1234", "status"]


def test_explicit_conn_flag_wins():
    out = inject_config(
        ["--conn", "mqtts://x:1", "status"],
        _obj(conn="mqtts://b:8883", swarm_id="1234"),
    )
    # conn not re-injected; swarm_id still filled in.
    assert out.count("--conn") == 1
    assert out[-3:] == ["--conn", "mqtts://x:1", "status"]
    assert "--swarm-id" in out and "1234" in out


def test_short_conn_flag_wins():
    out = inject_config(["-n", "simulator", "status"], _obj(conn="mqtts://b:8883"))
    assert "mqtts://b:8883" not in out


def test_config_path_flag_skips_injection():
    out = inject_config(
        ["-c", "other.toml", "status"],
        _obj(conn="mqtts://b:8883", swarm_id="1234"),
    )
    assert out == ["-c", "other.toml", "status"]


def test_help_skips_injection():
    assert inject_config(["--help"], _obj(conn="mqtts://b:8883")) == ["--help"]
    assert inject_config(["status", "-h"], _obj(conn="mqtts://b:8883")) == [
        "status",
        "-h",
    ]


def test_no_config_is_noop():
    assert inject_config(["status"], None) == ["status"]
    assert inject_config(["status"], _obj()) == ["status"]
