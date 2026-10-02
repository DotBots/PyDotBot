# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Find, start and stop the local swarm server `dotbot run controller` uses.

Run as `python -m dotbot.swarm_serve <swarmit args>`, this module is the
child `start` launches: swarmit's CLI, with `DOTBOT_MQTT_INSECURE` applied and
the broker login already in its environment. Its stdin is a pipe from the
controller, and it exits when that pipe closes, however the controller ends.
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from dotbot.mqtt_tls import LOCAL_HOSTS, PASS_ENV, USER_ENV

# How long a stopping server gets before it is killed
STOP_TIMEOUT_S = 5.0
# Set in the child's environment: exit when stdin reaches end of file
LIFELINE_ENV = "DOTBOT_SWARM_SERVE_LIFELINE"


def server_settings(url: str, timeout: float = 0.5) -> dict | None:
    """The `/settings` of the swarm server at `url`; None unless a swarm
    server answers there."""
    try:
        with urlopen(f"{url.rstrip('/')}/settings", timeout=timeout) as response:
            settings = json.loads(response.read())
    except (URLError, OSError, ValueError):
        return None
    if not isinstance(settings, dict) or "network_id" not in settings:
        return None
    return settings


def local_address(url: str) -> tuple[str, int] | None:
    """The host and port of an `http://` `url` on this machine, else None."""
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in LOCAL_HOSTS:
        return None
    return parts.hostname, parts.port or 80


def port_taken(host: str, port: int) -> bool:
    """Whether something accepts connections at `host`:`port`."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@dataclass
class SwarmServer:
    """A swarm server the controller started, and where its output goes."""

    process: subprocess.Popen
    log_path: Path
    stopping: bool = False

    def stop(self) -> None:
        self.stopping = True
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def start(
    host: str,
    port: int,
    conn: str,
    swarm_id: str,
    username: str | None,
    password: str | None,
    log_path: Path,
) -> SwarmServer:
    """Start `swarm serve --local` at `host`:`port`, against `conn` and
    `swarm_id`, with exactly this login (none when both are None)."""
    env = dict(os.environ)
    env.pop(USER_ENV, None)
    env.pop(PASS_ENV, None)
    if username is not None:
        env[USER_ENV] = username
    if password is not None:
        env[PASS_ENV] = password
    env[LIFELINE_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        "dotbot.swarm_serve",
        "--conn",
        conn,
        "--swarm-id",
        swarm_id,
        "serve",
        "--local",
        "--bind-host",
        host,
        "--http-port",
        str(port),
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as log:
        # Its own session, so a terminal Ctrl-C reaches only the controller,
        # which then stops it.
        process = subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=sys.platform != "win32",
        )
    server = SwarmServer(process, log_path)
    atexit.register(server.stop)
    return server


def watch(server: SwarmServer, on_exit) -> None:
    """Call `on_exit(returncode)` from a daemon thread if the server exits
    before `stop`."""

    def wait():
        code = server.process.wait()
        if not server.stopping:
            on_exit(code)

    threading.Thread(target=wait, name="swarm server watch", daemon=True).start()


def exit_with_parent() -> None:
    """Under `LIFELINE_ENV`, end this process once stdin reaches end of file,
    which happens when the process holding the pipe's other end exits."""
    if os.environ.get(LIFELINE_ENV) != "1" or sys.stdin is None:
        return
    stdin = sys.stdin.buffer

    def wait():
        while stdin.read(1024):
            pass
        if sys.platform == "win32":
            os._exit(0)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=wait, name="swarm server lifeline", daemon=True).start()


def main(args: list[str]) -> None:  # pragma: no cover - needs a broker
    exit_with_parent()
    from swarmit.cli.main import main as swarmit_group

    from dotbot.mqtt_tls import allow_unverified_broker

    allow_unverified_broker()
    swarmit_group.main(
        args=args, prog_name="dotbot swarm", obj={}, standalone_mode=True
    )


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
