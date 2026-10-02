"""The swarm server `run controller` reuses or starts."""

import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from dotbot import swarm_serve
from dotbot.controller import ControllerSettings
from dotbot.controller_app import _swarm_server, main
from dotbot.swarm_serve import SwarmServer, local_address
from dotbot.swarm_serve import server_settings as real_server_settings
from dotbot.swarm_serve import start as real_start
from dotbot.swarm_serve import watch as real_watch

_CTX = SimpleNamespace(obj={})


def _broker(**overrides):
    fields = dict(
        adapter="cloud",
        mqtt_host="argus.example",
        mqtt_port=8883,
        mqtt_use_tls=True,
        mqtt_username="me",
        mqtt_password="secret",
        network_id="A001",
    )
    fields.update(overrides)
    return ControllerSettings(**fields)


def test_starts_one_beside_a_broker_with_the_controllers_login(no_swarm_server, capsys):
    server = _swarm_server(_CTX, None, _broker())
    assert server is no_swarm_server.return_value
    args = no_swarm_server.call_args.args
    assert args[:6] == (
        "localhost",
        8001,
        "mqtts://argus.example:8883",
        "A001",
        "me",
        "secret",
    )
    assert "Swarmit server: started at http://localhost:8001" in capsys.readouterr().out


def test_reuses_one_already_answering(no_swarm_server, monkeypatch, capsys):
    monkeypatch.setattr(
        swarm_serve, "server_settings", lambda url: {"network_id": 0xB002}
    )
    assert _swarm_server(_CTX, None, _broker()) is None
    no_swarm_server.assert_not_called()
    captured = capsys.readouterr()
    assert "reusing the one at http://localhost:8001" in captured.out
    assert "on swarm B002, not A001" in captured.err


@pytest.mark.parametrize(
    "flag, settings, why",
    [
        (False, _broker(), "swarm_serve off, from the command line"),
        (None, _broker(swarmit_url="http://lab:8001"), "address on this machine"),
        (None, _broker(controller_http_host="0.0.0.0"), "unauthenticated"),
        (True, _broker(adapter="edge", port="/dev/ttyACM0"), "beside a broker"),
    ],
)
def test_starts_none_when(no_swarm_server, capsys, flag, settings, why):
    assert _swarm_server(_CTX, flag, settings) is None
    no_swarm_server.assert_not_called()
    assert why in capsys.readouterr().out


def test_starts_none_on_a_port_something_else_holds(
    no_swarm_server, monkeypatch, capsys
):
    monkeypatch.setattr(swarm_serve, "port_taken", lambda *a: True)
    assert _swarm_server(_CTX, None, _broker()) is None
    no_swarm_server.assert_not_called()
    assert "holds port 8001" in capsys.readouterr().out


def test_says_nothing_for_a_serial_gateway_by_default(no_swarm_server, capsys):
    assert _swarm_server(_CTX, None, _broker(adapter="edge")) is None
    assert "Swarmit server" not in capsys.readouterr().out


def test_starts_none_without_a_swarmit_url(no_swarm_server):
    assert _swarm_server(_CTX, None, _broker(swarmit_url=None)) is None
    no_swarm_server.assert_not_called()


def test_swarm_serve_comes_from_the_config(no_swarm_server, tmp_path, monkeypatch):
    from dotbot.cli.main import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "dotbot.toml").write_text("[run.controller]\nswarm_serve = false\n")
    monkeypatch.setattr("dotbot.controller_app.asyncio.run", lambda coro: coro.close())
    monkeypatch.setattr("dotbot.controller_app.Controller.__init__", lambda *a: None)
    monkeypatch.setattr(
        "dotbot.controller_app.Controller.run", lambda self: _noop(), raising=False
    )
    result = CliRunner().invoke(
        cli,
        ["run", "controller", "--conn", "mqtts://argus:8883", "--swarm-id", "A001"],
    )
    assert result.exit_code == 0, result.output
    assert "swarm_serve off, from" in result.output
    no_swarm_server.assert_not_called()


async def _noop():
    return None


@pytest.mark.parametrize("raised", [None, KeyboardInterrupt, SystemExit])
def test_the_controller_stops_the_server_it_started(
    no_swarm_server, monkeypatch, raised
):
    def run(coro):
        coro.close()
        if raised is not None:
            raise raised

    monkeypatch.setattr("dotbot.controller_app.asyncio.run", run)
    monkeypatch.setattr("signal.signal", lambda *a: None)
    monkeypatch.setattr("dotbot.controller_app.Controller.__init__", lambda *a: None)
    monkeypatch.setattr(
        "dotbot.controller_app.Controller.run", lambda self: _noop(), raising=False
    )
    result = CliRunner().invoke(
        main, ["--conn", "mqtts://argus:8883", "--swarm-id", "A001"]
    )
    assert result.exit_code == 0, result.output
    no_swarm_server.return_value.stop.assert_called_once()


def test_run_controller_help_names_the_opt_out():
    assert "--no-swarm-serve" in CliRunner().invoke(main, ["--help"]).output


def test_local_address():
    assert local_address("http://localhost:8001") == ("localhost", 8001)
    assert local_address("http://127.0.0.1") == ("127.0.0.1", 80)
    assert local_address("http://[::1]:8001") == ("::1", 8001)
    assert local_address("https://localhost:8001") is None
    assert local_address("http://lab.example:8001") is None


@pytest.mark.parametrize(
    "body, found",
    [
        (b'{"network_id": 40961, "auth_mode": "none"}', True),
        (b'{"name": "something else"}', False),
        (b"[1, 2]", False),
        (b"<html></html>", False),
    ],
)
def test_server_settings_reuses_only_a_swarm_server(body, found):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.handle_request, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        assert (real_server_settings(url) is not None) == found
    finally:
        httpd.server_close()


def test_start_hands_the_child_exactly_the_login(monkeypatch, tmp_path):
    seen = {}

    class Popen:
        def __init__(self, command, env, **kwargs):
            seen.update(command=command, env=env, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", Popen)
    monkeypatch.setattr("atexit.register", lambda func: None)
    monkeypatch.setenv("DOTBOT_MQTT_USER", "someone-else")
    monkeypatch.setenv("DOTBOT_MQTT_PASS", "theirs")
    real_start(
        "localhost", 8123, "mqtts://b:8883", "A001", None, None, tmp_path / "s.log"
    )
    assert "DOTBOT_MQTT_USER" not in seen["env"]
    assert "DOTBOT_MQTT_PASS" not in seen["env"]
    assert seen["command"][1:3] == ["-m", "dotbot.swarm_serve"]
    assert seen["stdin"] == subprocess.PIPE
    assert seen["env"][swarm_serve.LIFELINE_ENV] == "1"
    assert seen["command"][-6:] == [
        "serve",
        "--local",
        "--bind-host",
        "localhost",
        "--http-port",
        "8123",
    ]
    real_start(
        "localhost", 8123, "mqtts://b:8883", "A001", "me", "pw", tmp_path / "s.log"
    )
    assert (seen["env"]["DOTBOT_MQTT_USER"], seen["env"]["DOTBOT_MQTT_PASS"]) == (
        "me",
        "pw",
    )


def test_stop_ends_the_child_without_reporting_it_as_a_crash(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    server = SwarmServer(process, tmp_path / "s.log")
    exits = []
    real_watch(server, exits.append)
    server.stop()
    assert process.poll() is not None
    time.sleep(0.1)
    assert exits == []


def test_watch_reports_a_server_that_exits_on_its_own(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    exits = []
    real_watch(SwarmServer(process, tmp_path / "s.log"), exits.append)
    process.wait()
    for _ in range(50):
        if exits:
            break
        time.sleep(0.02)
    assert exits == [3]


_LIFELINE_CHILD = (
    "import time; from dotbot.swarm_serve import exit_with_parent; "
    "exit_with_parent(); print('up', flush=True); time.sleep(60)"
)


def _lifeline_env():
    import os

    return {**os.environ, swarm_serve.LIFELINE_ENV: "1"}


def test_the_child_exits_when_its_stdin_closes():
    child = subprocess.Popen(
        [sys.executable, "-c", _LIFELINE_CHILD],
        env=_lifeline_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        assert child.stdout.readline().strip() == b"up"
        child.stdin.close()
        child.wait(timeout=10)
    finally:
        child.kill()
        child.wait()


def _running(pid: int) -> bool:
    """Whether `pid` runs, a zombie nobody has reaped yet counting as ended."""
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX")
def test_the_child_exits_when_the_controller_is_killed():
    import os
    import signal

    controller = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess, sys, time; "
            "child = subprocess.Popen([sys.executable, '-c', sys.argv[1]], "
            "stdin=subprocess.PIPE, stdout=subprocess.PIPE); "
            "child.stdout.readline(); print(child.pid, flush=True); time.sleep(60)",
            _LIFELINE_CHILD,
        ],
        env=_lifeline_env(),
        stdout=subprocess.PIPE,
    )
    child_pid = int(controller.stdout.readline())
    controller.send_signal(signal.SIGKILL)
    controller.wait()
    for _ in range(100):
        if not _running(child_pid):
            return
        time.sleep(0.1)
    os.kill(child_pid, signal.SIGKILL)
    pytest.fail("the swarm server outlived the controller")
