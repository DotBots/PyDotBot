# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The packaged guide names only commands, flags, modules and routes that
exist, and stays short."""

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from importlib.resources import files

import click
from click.testing import CliRunner

from dotbot.cli.main import cli

GUIDE_MAX_LINES = 150

_FENCE = re.compile(r"^```[a-z]*\n(.*?)^```", re.M | re.S)
_INLINE = re.compile(r"`((?:dotbot|curl) [^`]+)`")
_ROUTE = re.compile(r"/controller/[^\s`'\"?)]*")
_PROSE_CALL = re.compile(r"`(GET|PUT|POST|DELETE) (/controller/[^\s`]*)")
# A guide segment a route's `{param}` may stand for: `$ADDR`, an address, `0`
_PARAM_VALUE = re.compile(r"^(\$[A-Z_]+|[0-9A-Fa-f]+)$")
_ENV_ASSIGNMENT = re.compile(r"^[A-Z_]+=\S*$")


def guide() -> str:
    return files("dotbot").joinpath("guide.md").read_text("utf-8")


def _code_lines(text: str):
    """Each shell line of the guide's fenced blocks, continuations joined and
    comments dropped."""
    for block in _FENCE.findall(text):
        for line in block.replace("\\\n", " ").splitlines():
            line = re.sub(r"\s+#.*$", "", line).strip()
            if line:
                yield line


def _words(line: str):
    """The words of one command line, without leading `VAR=value`."""
    words = shlex.split(line)
    while words and _ENV_ASSIGNMENT.match(words[0]):
        words.pop(0)
    return words


def dotbot_commands(text: str):
    """The argument words of every `dotbot ...` the guide names, in code
    blocks and in inline code; placeholders (`<group>`, `...`) end one."""
    lines = [*_code_lines(text), *_INLINE.findall(text)]
    for line in lines:
        words = _words(line)
        if words[:1] != ["dotbot"]:
            continue
        kept = []
        for word in words[1:]:
            if "<" in word or word == "...":
                break
            kept.append(word)
        yield kept


def api_calls(text: str):
    """(method, path) for each curl the guide shows and each `METHOD /path`
    it names in prose; a curl without `-X` is a GET."""
    for line in [*_code_lines(text), *_INLINE.findall(text)]:
        words = _words(line)
        if words[:1] != ["curl"]:
            continue
        method = words[words.index("-X") + 1] if "-X" in words else "GET"
        for route in _ROUTE.findall(line):
            yield method, route.rstrip(".,:")
    for method, route in _PROSE_CALL.findall(text):
        yield method, route.rstrip(".,:")


def python_modules(text: str):
    for line in _code_lines(text):
        words = _words(line)
        if words[:2] == ["python", "-m"]:
            yield words[2]


def _flag_names(command: click.Command, ctx: click.Context):
    names = set()
    for param in command.get_params(ctx):
        names.update(getattr(param, "opts", ()))
        names.update(getattr(param, "secondary_opts", ()))
    return names


def _split_flag(word: str, known):
    """`--x=1` is `--x`; `-ys` is `-y` and `-s` unless `-ys` is itself a flag."""
    word = word.split("=", 1)[0]
    if word in known or word.startswith("--") or len(word) <= 2:
        return [word]
    return [f"-{letter}" for letter in word[1:]]


def unknown_flags(group: click.Group, words, substitutes=None):
    """Walk `words` down from `group` and return (path, flag) for each flag
    the command it follows does not take, or (path, None) for a subcommand
    that does not resolve. `substitutes` maps a command path to the command
    that really parses its flags."""
    substitutes = substitutes or {}
    command, path, problems = group, [], []
    descending = True
    for word in words:
        ctx = click.Context(command, info_name=" ".join(path) or "dotbot")
        if word.startswith("-"):
            known = _flag_names(command, ctx)
            for flag in _split_flag(word, known):
                if flag not in known:
                    problems.append((" ".join(path), flag))
            continue
        if not (descending and isinstance(command, click.Group)):
            descending = False
            continue
        sub = command.get_command(ctx, word)
        if sub is None:
            problems.append((" ".join([*path, word]), None))
            descending = False
            continue
        path.append(word)
        command = substitutes.get(tuple(path), sub)
    return problems


def unknown_targets(words):
    """The `device flash` role or `swarm flash` app in `words`, when it is
    not one those commands know."""
    from dotbot.cli._swarm_flash import APP_CATALOG
    from dotbot.cli.device import FLASH_TARGETS

    known = {("device", "flash"): FLASH_TARGETS, ("swarm", "flash"): APP_CATALOG}
    allowed = known.get(tuple(words[:2]))
    target = next((w for w in words[2:] if not w.startswith("-")), None)
    if allowed is None or target is None or target in allowed:
        return []
    return [(" ".join(words[:2]), target)]


def _swarm_problems(commands):
    """Check `dotbot swarm ...` lines against swarmit's group in a separate
    process: swarmit and dotbot.protocol cannot both register their payload
    types in one interpreter."""
    script = (
        "import json, sys\n"
        "from dotbot.cli.swarm import _load_swarmit_group, _mount_native_lh2\n"
        "from dotbot.tests.test_guide import unknown_flags\n"
        "group = _load_swarmit_group()\n"
        "_mount_native_lh2(group)\n"
        "print(json.dumps([unknown_flags(group, w) for w in json.load(sys.stdin)]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(commands),
        capture_output=True,
        text=True,
        check=True,
    )
    return [problem for each in json.loads(result.stdout) for problem in each]


def test_guide_fits_its_line_budget():
    assert len(guide().splitlines()) < GUIDE_MAX_LINES


def test_guide_command_prints_the_guide_with_the_version():
    result = CliRunner().invoke(cli, ["guide"])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0].startswith("# DotBot guide (pydotbot ")
    assert result.stdout.splitlines()[1:] == guide().splitlines()[1:]
    assert "config file" not in result.output


def test_root_help_points_at_the_guide():
    result = CliRunner().invoke(cli, ["--help"])
    head = result.output.split("Options:", 1)[0]
    assert "Start with: dotbot guide" in head


def test_guide_names_only_real_commands_and_flags():
    from dotbot.controller_app import main as controller_main

    commands = list(dotbot_commands(guide()))
    assert commands
    swarm = [words[1:] for words in commands if words[:1] == ["swarm"]]
    problems = [problem for words in commands for problem in unknown_targets(words)]
    for words in commands:
        if words[:1] != ["swarm"]:
            problems += unknown_flags(
                cli, words, {("run", "simulator"): controller_main}
            )
    problems += [
        (f"swarm {path}".strip(), flag) for path, flag in _swarm_problems(swarm)
    ]
    assert problems == []


def test_guide_names_only_real_modules():
    modules = list(python_modules(guide()))
    assert modules
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    assert missing == []


def _route_matches(path: str, template: str) -> bool:
    got, want = path.strip("/").split("/"), template.strip("/").split("/")
    return len(got) == len(want) and all(
        g == w or (w.startswith("{") and _PARAM_VALUE.match(g))
        for g, w in zip(got, want)
    )


def _route_methods(path: str):
    """The methods the API serves at `path`, empty when no route matches."""
    from dotbot.server import api

    return {
        method
        for route in api.routes
        if _route_matches(path, route.path)
        for method in getattr(route, "methods", None) or {"GET"}
    }


def test_guide_names_only_real_routes():
    from dotbot.server import api

    templates = {route.path for route in api.routes}
    assert api.docs_url in templates and api.openapi_url in templates
    routes = {route.rstrip(".,:") for route in _ROUTE.findall(guide())}
    assert routes
    assert [route for route in routes if not _route_methods(route)] == []


def test_guide_uses_each_route_with_a_method_it_takes():
    calls = set(api_calls(guide()))
    assert ("DELETE", "/controller/dotbots/waypoints") in calls
    wrong = [(m, path) for m, path in calls if m not in _route_methods(path)]
    assert wrong == []


def test_the_checker_catches_a_renamed_flag():
    assert unknown_flags(cli, ["run", "demo", "--lst"]) == [("run demo", "--lst")]
    assert unknown_flags(cli, ["fw", "fetchh"]) == [("fw fetchh", None)]


def test_the_checker_catches_a_misspelt_target_route_or_method():
    words = ["device", "flash", "mari-gatway", "--probe", "10"]
    assert unknown_targets(words) == [("device flash", "mari-gatway")]
    assert unknown_targets(["swarm", "flash", "remote-contrl", "-ys"]) != []
    assert not _route_methods("/controller/dotbots/waypointz")
    assert "DELETE" not in _route_methods("/controller/site")


def test_guide_does_not_mention_mcp():
    assert "mcp" not in guide().lower()
