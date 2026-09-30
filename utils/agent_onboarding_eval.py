# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Agent-onboarding eval: can a coding agent, given only an installed wheel and
one sentence, move a simulated DotBot?

Each run builds (once) a wheel of a committed ref, installs it into a fresh venv, and starts the
agent in an empty directory with that venv first on PATH, `BROWSER=true` in its
environment, and the prompt below. While it works, this script polls
`GET /controller/dotbots` on a side port and records every robot's first
pose. A run passes when some robot moved more than 100 mm from where it was
first seen, and the agent read no installed source (`site-packages`,
`dotbot.__file__`, `inspect.getsource`).

It spends tokens and is not deterministic, so it is run by hand, not in CI.
Linux only: it reads /proc to find and stop what the agent started.

    python utils/agent_onboarding_eval.py --runs 3 --workdir /some/scratch
    python utils/agent_onboarding_eval.py --ref origin/main --runs 1
    python utils/agent_onboarding_eval.py --console-dist dotbot/console-web/dist
    python utils/agent_onboarding_eval.py --dry-run
"""

import argparse
import json
import math
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPT = "run dotbot --help and help me move a robot in the simulator"
# Port 8000 is the controller's default, and may be a controller someone runs
PORT_NOTE = (
    "Port 8000 is taken on this machine: run the simulator with "
    "--controller-http-port {port}."
)
AGENT_CMD = (
    "claude -p {prompt} --output-format stream-json --verbose "
    "--permission-mode bypassPermissions --no-session-persistence "
    "--strict-mcp-config --disable-slash-commands --max-budget-usd {budget}"
)
MOVED_MM = 100
SOURCE_READS = ("site-packages", "dotbot.__file__", "inspect.getsource", "/lib/python")
PROJECT_FILES = ("AGENTS.md", "CLAUDE.md")
MARKER = "DOTBOT_ONBOARDING_EVAL"


def build_wheel(ref: str, out: Path, console: Path | None) -> Path:
    """A wheel of the committed tree at `ref`, with `console` as its built
    web console when given."""
    out.mkdir(parents=True, exist_ok=True)
    source = out / "source"
    shutil.rmtree(source, ignore_errors=True)
    source.mkdir()
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", ref], check=True, capture_output=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(source)], input=archive, check=True)
    if console is not None:
        shutil.copytree(console, source / "dotbot" / "console-web" / "dist")
    for old in out.glob("pydotbot-*.whl"):
        old.unlink()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-q",
            "-w",
            str(out),
            str(source),
        ],
        check=True,
    )
    return next(out.glob("pydotbot-*.whl"))


def make_venv(wheel: Path, venv: Path) -> None:
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run(
        [str(venv / "bin" / "pip"), "install", "-q", str(wheel)],
        check=True,
    )


def project_files_above(directory: Path) -> list[Path]:
    return [
        parent / name
        for parent in (directory, *directory.parents)
        for name in PROJECT_FILES
        if (parent / name).exists()
    ]


def agent_env(venv: Path, run_id: str, config: Path) -> dict:
    """The environment with the fresh venv first on PATH, so its `dotbot` is
    the one found, and an empty dotbot config in place of this machine's."""
    env = {
        k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")
    }
    env["PATH"] = os.pathsep.join([str(venv / "bin"), env.get("PATH", "")])
    env["VIRTUAL_ENV"] = str(venv)
    env["BROWSER"] = "true"
    env["DOTBOT_CONFIG"] = str(config)
    env[MARKER] = run_id
    return env


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class PoseWatch(threading.Thread):
    """Polls the side port and keeps each robot's first pose and its largest
    distance from it."""

    def __init__(self, port: int):
        super().__init__(daemon=True)
        self.url = f"http://127.0.0.1:{port}/controller/dotbots"
        self.first: dict = {}
        self.moved: dict = {}
        self.first_move_at = None
        self.started = time.monotonic()
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(0.5):
            try:
                with urllib.request.urlopen(self.url, timeout=2) as response:
                    robots = json.load(response)
            except (OSError, ValueError):
                continue
            for robot in robots:
                pose = robot.get("pose") or robot.get("lh2_position")
                if not pose:
                    continue
                here = (pose["x"], pose["y"])
                start = self.first.setdefault(robot["address"], here)
                distance = math.dist(start, here)
                self.moved[robot["address"]] = max(
                    distance, self.moved.get(robot["address"], 0.0)
                )
                if distance > MOVED_MM and self.first_move_at is None:
                    self.first_move_at = time.monotonic() - self.started

    def best(self) -> float:
        return max(self.moved.values(), default=0.0)


def marked_pids(run_id: str) -> list[int]:
    """Every process whose environment carries this run's marker."""
    needle = f"{MARKER}={run_id}".encode()
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if needle in (entry / "environ").read_bytes().split(b"\0"):
                pids.append(int(entry.name))
        except OSError:
            continue
    return pids


def stop_marked(run_id: str) -> list[int]:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = marked_pids(run_id)
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        if not pids:
            return []
        time.sleep(2)
    return marked_pids(run_id)


def read_transcript(path: Path) -> dict:
    """Tool calls, the commands run, source reads and the final message."""
    calls, commands, source_reads, result = [], [], [], {}
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            result = event
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            text = json.dumps(block.get("input", {}))
            calls.append(block.get("name"))
            if block.get("name") == "Bash":
                commands.append(block["input"].get("command", ""))
            else:
                commands.append(f"[{block.get('name')}] {text[:120]}")
            if any(needle in text for needle in SOURCE_READS):
                source_reads.append(text[:200])
    final = result.get("result") or ""
    shows = any(
        word in final for word in ("curl ", "dotbot run", "dotbot guide", "python -m")
    )
    return {
        "tool_calls": len(calls),
        "commands": commands,
        "source_reads": source_reads,
        "final": final,
        "shows_command": shows,
        "cost_usd": result.get("total_cost_usd"),
        "num_turns": result.get("num_turns"),
        "is_error": result.get("is_error"),
    }


def one_run(args, wheel: Path, index: int) -> dict:
    run_id = f"{int(time.time())}-{index}"
    run_dir = args.workdir / f"run-{run_id}"
    project = run_dir / "project"
    project.mkdir(parents=True)
    venv = run_dir / "venv"
    make_venv(wheel, venv)
    config = run_dir / "dotbot.toml"
    config.write_text("")
    prompt = f"{args.prompt} {PORT_NOTE.format(port=args.port)}"
    cmd = shlex.split(
        args.agent_cmd.replace("{prompt}", shlex.quote(prompt)).replace(
            "{budget}", str(args.budget)
        )
    )
    cmd[0] = shutil.which(cmd[0]) or cmd[0]
    transcript = run_dir / "transcript.jsonl"
    watch = PoseWatch(args.port)
    watch.start()
    started = time.monotonic()
    agent = None
    # The agent runs in its own session, so Ctrl-C here never reaches it
    try:
        with transcript.open("w") as out:
            agent = subprocess.Popen(
                cmd,
                cwd=project,
                env=agent_env(venv, run_id, config),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                agent.wait(timeout=args.timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
        seconds = time.monotonic() - started
        time.sleep(1)
    finally:
        watch.stop.set()
        watch.join()
        left = stop_marked(run_id)
        if agent is not None:
            try:
                agent.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    summary = read_transcript(transcript)
    moved = watch.best()
    passed = moved > MOVED_MM and not summary["source_reads"] and not timed_out
    record = {
        "run": run_id,
        "pass": passed,
        "moved_mm": round(moved, 1),
        "first_move_s": watch.first_move_at and round(watch.first_move_at, 1),
        "seconds": round(seconds, 1),
        "timed_out": timed_out,
        "read_source": bool(summary["source_reads"]),
        "port_left_open": port_open(args.port),
        "processes_left": left,
        **summary,
    }
    (run_dir / "result.json").write_text(json.dumps(record, indent=2))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--ref", default="HEAD", help="Build the wheel from this git ref."
    )
    parser.add_argument(
        "--console-dist",
        type=Path,
        help="A built console (dotbot/console-web/dist) to ship in the wheel.",
    )
    parser.add_argument("--wheel", type=Path, help="Use this wheel; build none.")
    parser.add_argument("--workdir", type=Path, help="Where runs are kept.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument(
        "--agent-cmd",
        default=AGENT_CMD,
        help="The agent command line; {prompt} and {budget} are substituted.",
    )
    parser.add_argument("--budget", type=float, default=5.0, help="USD per run.")
    parser.add_argument("--timeout", type=float, default=900, help="Seconds per run.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the setup and print the agent command; run nothing.",
    )
    args = parser.parse_args()
    args.workdir = (
        args.workdir or Path(tempfile.mkdtemp(prefix="agent-eval-"))
    ).resolve()
    args.workdir.mkdir(parents=True, exist_ok=True)

    agent = shlex.split(args.agent_cmd)[0]
    problems = []
    if shutil.which(agent) is None:
        problems.append(f"{agent} is not on PATH")
    found = project_files_above(args.workdir)
    if found:
        problems.append(f"project instructions above the workdir: {found}")
    if port_open(args.port):
        problems.append(f"port {args.port} is already in use")
    if args.port != 8000 and port_open(8000):
        problems.append(
            "port 8000 is in use: the guide's commands target it, so the agent "
            "could drive whatever serves it"
        )
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    for skill in (claude / "skills" / "dotbot", Path.home() / ".agents/skills/dotbot"):
        if skill.exists():
            problems.append(f"a dotbot skill is already installed: {skill}")
    if (claude / "CLAUDE.md").exists():
        print(f"note: the agent also reads {claude / 'CLAUDE.md'}", file=sys.stderr)
    if not Path("/proc/self/environ").exists():
        problems.append("no /proc: this eval runs on Linux only")
    if args.dry_run:
        print(f"workdir: {args.workdir}")
        print("agent command:", args.agent_cmd)
        print("prompt:", f"{args.prompt} {PORT_NOTE.format(port=args.port)}")
        print("\n".join(problems) or "setup ok")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    wheel = args.wheel or build_wheel(
        args.ref, args.workdir / "wheel", args.console_dist
    )
    print(f"wheel: {wheel}\nworkdir: {args.workdir}")
    records = []
    for index in range(args.runs):
        record = one_run(args, wheel, index)
        records.append(record)
        print(
            f"run {record['run']}: {'PASS' if record['pass'] else 'FAIL'}"
            f"  moved {record['moved_mm']} mm  {record['tool_calls']} tool calls"
            f"  {record['seconds']} s  read source: "
            f"{'yes' if record['read_source'] else 'no'}"
            f"  shows a command: {'yes' if record['shows_command'] else 'no'}"
            f"  cost: {record['cost_usd']}"
        )
        if record["processes_left"] or record["port_left_open"]:
            print(f"  left running: {record['processes_left']}", file=sys.stderr)
    passed = sum(record["pass"] for record in records)
    print(f"{passed} of {len(records)} passed")
    (args.workdir / "summary.json").write_text(json.dumps(records, indent=2))
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    sys.exit(main())
