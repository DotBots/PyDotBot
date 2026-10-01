# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Find, start and stop the local swarm server `dotbot run controller` uses.

Run as `python -m dotbot.swarm_serve <swarmit args>`, this module is the
child `start` launches: swarmit's CLI, with `DOTBOT_MQTT_INSECURE` applied and
the broker login already in its environment.
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
# The pid the child exits with when its parent is gone
PARENT_ENV = "DOTBOT_SWARM_SERVE_PARENT"


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
    env[PARENT_ENV] = str(os.getpid())
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
            stdin=subprocess.DEVNULL,
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


def _follow_parent() -> None:  # pragma: no cover - runs in the child
    """Exit with the parent: on Linux a SIGTERM when it dies, everywhere an
    exit now if it is already gone."""
    parent = os.environ.get(PARENT_ENV)
    if sys.platform == "linux":
        try:
            import ctypes

            ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
        except (OSError, AttributeError):
            pass
    if parent is not None and os.getppid() != int(parent):
        sys.exit(0)


def main(args: list[str]) -> None:  # pragma: no cover - needs a broker
    _follow_parent()
    from swarmit.cli.main import main as swarmit_group

    from dotbot.mqtt_tls import allow_unverified_broker

    allow_unverified_broker()
    swarmit_group.main(
        args=args, prog_name="dotbot swarm", obj={}, standalone_mode=True
    )


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
