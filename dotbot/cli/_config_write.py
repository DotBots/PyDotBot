# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Writing one config key: which file it goes to, and the write itself.

The CLI writes only untracked files unless told otherwise: a machine key
goes to the user file wherever you are, any other key to the overlay
beside the project file when one is in use, else to the user file.
"""

from __future__ import annotations

import difflib
import os
import tomllib
import typing
from pathlib import Path
from typing import Any

import click
import tomlkit
from pydantic import BaseModel

from dotbot import config as _config

# Keys true of this computer, which go to the user file from anywhere.
MACHINE_KEYS = frozenset(
    {
        ("fw", "segger_dir"),
        ("fw", "artifacts_dir"),
        ("fw", "board"),
        ("device", "board"),
        ("device", "probe"),
        *(
            ("run", "controller", key)
            for key in (
                "camera_max_robots",
                "camera_detect_share",
                "swarmit_url",
                "swarm_serve",
                "mrta_url",
                "http_port",
                "http_host",
                "headless",
            )
        ),
    }
)


class WriteError(Exception):
    """A key that cannot be written, with the reason."""


def parse_key(text: str) -> tuple[str, ...]:
    """A dotted key in TOML spelling (`fw.segger_dir`, `login."a.b".user`)."""
    try:
        data = tomllib.loads(f"{text} = 0")
    except tomllib.TOMLDecodeError as exc:
        raise WriteError(f"{text!r} is not a key; write it as in TOML") from exc
    path: list[str] = []
    while isinstance(data, dict):
        ((key, data),) = data.items()
        path.append(key)
    return tuple(path)


def key_text(path: tuple[str, ...]) -> str:
    return ".".join(tomlkit.key(part).as_string() for part in path)


# The keys config loading refuses with a pointer, by the table they sat in.
_REMOVED = {
    (): _config._TOP_REMOVED,
    ("fw",): _config._FW_REMOVED,
    ("run",): _config._RUN_REMOVED,
    ("run", "controller"): _config._CONTROLLER_REMOVED,
}


def _unknown(path: tuple[str, ...], i: int, known) -> WriteError:
    removed = _REMOVED.get(path[:i], {}).get(path[i])
    if removed is not None:
        return WriteError(removed)
    close = difflib.get_close_matches(path[i], list(known), n=1)
    hint = f"; did you mean {key_text((*path[:i], close[0]))}?" if close else ""
    return WriteError(f"{key_text(path)} is not a config key{hint}")


def check_key(path: tuple[str, ...]) -> Any:
    """The annotation of the schema field at `path`; WriteError if unknown."""
    model: Any = _config.DotbotConfig
    i = 0
    while True:
        fields = {(f.alias or name): f for name, f in model.model_fields.items()}
        field = fields.get(path[i])
        if field is None:
            raise _unknown(path, i, fields)
        annotation = field.annotation
        i += 1
        if typing.get_origin(annotation) is dict:
            model = typing.get_args(annotation)[1]
            i += 1
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            model = annotation
        elif i == len(path):
            return annotation
        else:
            raise WriteError(f"{key_text(path)} is not a config key")
        if i >= len(path):
            raise WriteError(f"{key_text(path[:i])} is a table; name a key in it")


def coerce(path: tuple[str, ...], raw: str) -> Any:
    """`raw` as the type the schema gives the key at `path`."""
    annotation = check_key(path)
    kinds = set(typing.get_args(annotation)) or {annotation}
    if bool in kinds:
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise WriteError(f"{key_text(path)} is true or false, not {raw!r}")
    if int in kinds:
        try:
            return int(raw)
        except ValueError as exc:
            raise WriteError(f"{key_text(path)} is a whole number") from exc
    if float in kinds:
        try:
            return float(raw)
        except ValueError as exc:
            raise WriteError(f"{key_text(path)} is a number") from exc
    return raw


def target(config: Any, path: tuple[str, ...], where: str | None) -> Path:
    """The file a write of `path` goes to; `where` is `user`, `project` or
    None (route by key)."""
    project = getattr(config, "project_path", None)
    if where == "user" or path[0] == "login" or path in MACHINE_KEYS:
        if where == "project":
            raise WriteError(f"{key_text(path)} belongs in the user file")
        return _config.USER_CONFIG_PATH
    if where == "project":
        if project is None:
            raise WriteError(
                "no project dotbot.toml is in use here; run this from the "
                "project's folder, or pass -c FILE"
            )
        return Path(project)
    if project is not None:
        return _config.local_path_for(Path(project))
    return _config.USER_CONFIG_PATH


def _document(path: Path) -> tomlkit.TOMLDocument:
    if path.is_file():
        return tomlkit.parse(path.read_text())
    return tomlkit.document()


def _save(path: Path, document: tomlkit.TOMLDocument) -> None:
    """Validate the edited file as a whole, then write it."""
    text = tomlkit.dumps(document)
    try:
        _config.load_config_text(text, source=str(path))
    except _config.ConfigError as exc:
        raise WriteError(str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if document.get("login"):
        os.chmod(path, 0o600)


def set_value(path: Path, key: tuple[str, ...], value: Any) -> None:
    """Set `key` to `value` in the file at `path`, keeping its comments."""
    document = _document(path)
    table: Any = document
    for part in key[:-1]:
        if part not in table:
            table[part] = tomlkit.table()
        table = table[part]
        if not isinstance(table, dict):
            raise WriteError(f"{key_text(key)}: {part} is not a table in {path}")
    table[key[-1]] = value
    _save(path, document)


def unset_value(path: Path, key: tuple[str, ...]) -> bool:
    """Remove `key` from the file at `path`, and any table it leaves empty;
    False when the file does not set it."""
    if not path.is_file():
        return False
    document = _document(path)
    tables: list[Any] = [document]
    for part in key[:-1]:
        nxt = tables[-1].get(part)
        if not isinstance(nxt, dict):
            return False
        tables.append(nxt)
    if key[-1] not in tables[-1]:
        return False
    del tables[-1][key[-1]]
    for depth in range(len(key) - 1, 0, -1):
        if len(tables[depth]) == 0:
            del tables[depth - 1][key[depth - 1]]
    _save(path, document)
    return True


def lookup(data: Any, key: tuple[str, ...]) -> Any:
    """The raw value at `key` in a parsed file, or None."""
    for part in key:
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def hiders(config: Any, written: Path, key: tuple[str, ...]) -> list[str]:
    """What overrides `key` once written to `written`: the higher files that
    set it, and the env variables that do, one phrase each."""
    phrases = []
    files = list(getattr(config, "files", ()))
    order = [item.path.resolve() for item in files]
    if written.resolve() in order:
        higher = files[order.index(written.resolve()) + 1 :]
    elif written.resolve() == _config.USER_CONFIG_PATH.resolve():
        higher = [item for item in files if item.kind != "user"]
    else:
        higher = [item for item in files if item.kind == "local"]
    for item in higher:
        if lookup(item.data, key) is not None:
            phrases.append(f"{item.label} sets {key_text(key)}")
    if key[0] != "login":
        section = ".".join(key[:-1]) or None
        for name in _config._env_candidates(section, key[-1]):
            if name in os.environ:
                phrases.append(f"{name} is set")
    return phrases


# Keys whose value is a path, read from the folder of the file that sets it.
PATH_KEYS = frozenset(
    {
        ("fw", "segger_dir"),
        ("fw", "artifacts_dir"),
        ("fw", "sources", "dotbot-firmware"),
        ("fw", "sources", "swarmit"),
        ("fw", "sources", "mari"),
    }
)


def path_value(key: tuple[str, ...], raw: str, written: Path) -> str:
    """`raw`, a path typed relative to the cwd, as `written` will read it:
    relative to its folder when inside it, else absolute."""
    from dotbot.site_packs import is_pack_path

    if key not in PATH_KEYS and not (key == ("site",) and is_pack_path(raw)):
        return raw
    if raw.startswith(("~", "/", "\\")) or Path(raw).is_absolute():
        return raw
    resolved = (Path.cwd() / raw).resolve()
    try:
        return resolved.relative_to(written.resolve().parent).as_posix()
    except ValueError:
        return str(resolved)


def where_options(project_help: str):
    """The `--user` / `--project` flags of a command that writes a key, as
    one decorator setting `where`."""

    def decorate(func):
        func = click.option(
            "--project", "where", flag_value="project", help=project_help
        )(func)
        return click.option(
            "--user",
            "where",
            flag_value="user",
            help="Write your user file, ~/.dotbot/dotbot.toml.",
        )(func)

    return decorate
