# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Unified `dotbot` configuration: one file, one precedence chain.

This is the resolver core for the single `dotbot` config file. It is
intentionally pure - no Click, no network, no global state - so the whole
precedence/discovery story is
exhaustively unit-testable without hardware. The CLI layer (a later phase)
feeds it the actual flags and `os.environ`.

The file mirrors the four-namespace CLI: top-level shared keys plus `[fw]` /
`[device]` / `[swarm]` / `[run]` tables, and `[testbed.<name>]` entries for the
physical deployments you switch between.

```toml
default_testbed = "inria"
conn     = "mqtts://broker.local:8883"   # shared; sections/testbeds override
swarm_id = "0001"

[testbed.inria]                          # a named deployment - select, don't edit
conn = "mqtts://broker.inria.fr:8883"
swarm_id = "0001"

[fw]
board = "dotbot-v3"

[run.controller]
http_port = 8000
```

Precedence for any value, highest wins:

    CLI flag  >  env (DOTBOT_<SECTION>_<KEY>, then shared DOTBOT_<KEY>)
              >  file (section value > selected testbed > top-level)
              >  built-in default

The selected testbed (`--testbed` > `DOTBOT_TESTBED` > `default_testbed`)
resolves first and slots into the file layer; an explicit flag/env still beats
it. Unknown keys are rejected (`extra='forbid'`) so a typo fails loud.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, Any, Mapping, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

# The four CLI namespaces, used to derive env-var names (DOTBOT_<SECTION>_<KEY>).
SECTIONS = ("fw", "device", "swarm", "run")

# Where the user-level config lives. Geovane's call (2026-06-01): one dir,
# shared with the calibration data under ~/.dotbot/ - no XDG split.
USER_CONFIG_PATH = Path.home() / ".dotbot" / "config.toml"
# Project-level config, discovered by walking up from the cwd.
PROJECT_CONFIG_NAME = "dotbot.toml"


class ConfigError(Exception):
    """A config file is malformed, has an unknown key, or names a missing testbed."""


def _check_conn(value: str | None) -> str | None:
    """Validate a connection string with the same parser the `--conn` flag uses.

    One validator for the file path and the flag path, so they can't drift.
    Imported lazily so merely importing this module doesn't pull in marilib.
    """
    if value is None:
        return value
    from dotbot.cli._conn import ConnError, parse_connection

    try:
        parse_connection(value)
    except ConnError as exc:
        raise ValueError(str(exc)) from exc
    return value


# A connection string validated against `parse_connection` wherever it appears.
Conn = Annotated[Optional[str], AfterValidator(_check_conn)]


class _Strict(BaseModel):
    """Base for every config section: reject unknown keys so typos fail loud."""

    model_config = ConfigDict(extra="forbid")


# All fields are Optional and default to None: the model captures only what the
# file *explicitly* set, so the resolver can tell "unset" from "set to the
# default" and apply the precedence chain correctly. Built-in defaults live in
# code (dotbot/__init__.py), not here.


class Testbed(_Strict):
    """One named physical deployment (Inria/100, La Poste/1000, ...).

    Holds only the environment-binding keys plus descriptive metadata. You
    select a testbed; you never edit the file to switch.
    """

    conn: Conn = None
    swarm_id: str | None = None
    serial_port: str | None = None
    location: str | None = None  # descriptive, for `dotbot testbed list`
    bots: int | None = None  # descriptive


class FwSection(_Strict):
    board: str | None = None
    sandbox: bool | None = None
    build_config: str | None = None  # Debug | Release
    segger_dir: str | None = None


class DeviceSection(_Strict):
    board: str | None = None
    sn_starting_digits: str | None = None
    build_config: str | None = None


class SwarmSection(_Strict):
    conn: Conn = None
    swarm_id: str | None = None
    devices: str | None = None


class ControllerSection(_Strict):
    http_port: int | None = None
    map_size: str | None = None
    background_map: str | None = None
    log_output: str | None = None
    csv_data_output: str | None = None
    webbrowser: bool | None = None
    gw_address: str | None = None
    simulator_init_state: str | None = None


class GatewaySection(_Strict):
    serial_port: str | None = None
    mqtt: Conn = None


class RunSection(_Strict):
    conn: Conn = None
    swarm_id: str | None = None
    controller: ControllerSection = Field(default_factory=ControllerSection)
    gateway: GatewaySection = Field(default_factory=GatewaySection)


class DotbotConfig(_Strict):
    """The whole file: top-level shared keys + the four section tables + testbeds."""

    default_testbed: str | None = None
    artifacts_dir: str | None = None
    log_level: str | None = None
    conn: Conn = None
    swarm_id: str | None = None

    fw: FwSection = Field(default_factory=FwSection)
    device: DeviceSection = Field(default_factory=DeviceSection)
    swarm: SwarmSection = Field(default_factory=SwarmSection)
    run: RunSection = Field(default_factory=RunSection)

    # `[testbed.<name>]` tables map to {name: Testbed}.
    testbed: dict[str, Testbed] = Field(default_factory=dict)


# --- Discovery --------------------------------------------------------------


def discover_config_path(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
    include_user_file: bool = True,
) -> Path | None:
    """Find the config file to load, highest priority first.

    1. `explicit` (the `-c/--config PATH` flag) wins outright.
    2. `DOTBOT_CONFIG` env var (an explicit path by another name).
    3. The nearest `dotbot.toml`, searching the cwd and its parents (stopping at
       a `.git` boundary) - so a per-experiment config "just works".
    4. The user file `~/.dotbot/config.toml` (skipped when
       `include_user_file=False` - used while the legacy `~/.dotbot/config.toml`
       fw segger_dir reader still owns that file).
    5. None (caller uses built-in defaults).
    """
    if explicit:
        return Path(explicit)
    env_path = environ.get("DOTBOT_CONFIG")
    if env_path:
        return Path(env_path)

    start = Path(start_dir or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break

    if include_user_file and USER_CONFIG_PATH.is_file():
        return USER_CONFIG_PATH
    return None


def load_config(path: os.PathLike[str] | str | None) -> DotbotConfig:
    """Load and validate a config file. `None` -> an empty config (all defaults).

    Raises `ConfigError` (with the file path) on bad TOML, an unknown key, a
    wrong-typed value, or an invalid connection string.
    """
    if path is None:
        return DotbotConfig()
    path = Path(path)
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read config {path}: {exc}") from exc
    try:
        return DotbotConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config {path}:\n{exc}") from exc


def load_discovered(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
) -> tuple[DotbotConfig, Path | None]:
    """Discover + load in one step. Returns (config, source_path or None)."""
    path = discover_config_path(explicit, environ=environ, start_dir=start_dir)
    return load_config(path), path


# --- Testbed selection ------------------------------------------------------


def select_testbed(
    config: DotbotConfig,
    *,
    cli_name: str | None = None,
    environ: Mapping[str, str] = os.environ,
) -> tuple[Testbed | None, str | None]:
    """Resolve the active testbed: `--testbed` > `DOTBOT_TESTBED` > default_testbed.

    Returns (testbed, name), or (None, None) if none is selected. Raises
    `ConfigError` if the selected name has no `[testbed.<name>]` entry.
    """
    name = cli_name or environ.get("DOTBOT_TESTBED") or config.default_testbed
    if not name:
        return None, None
    if name not in config.testbed:
        known = ", ".join(sorted(config.testbed)) or "(none defined)"
        raise ConfigError(f"unknown testbed {name!r}; defined testbeds: {known}")
    return config.testbed[name], name


# --- Precedence resolution --------------------------------------------------


def _env_candidates(section: str | None, key: str) -> tuple[str, ...]:
    """Env-var names to check, in priority order (Cargo's mechanical mapping).

    Sectioned key -> `DOTBOT_<SECTION>_<KEY>`, then the shared `DOTBOT_<KEY>`
    alias. Top-level key -> just `DOTBOT_<KEY>`.
    """
    key_part = key.upper().replace("-", "_")
    if section:
        return (f"DOTBOT_{section.upper()}_{key_part}", f"DOTBOT_{key_part}")
    return (f"DOTBOT_{key_part}",)


def _coerce(raw: str, like: Any) -> Any:
    """Coerce an env-var string to the type of `like` (the default)."""
    if isinstance(like, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(like, int):
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"expected an integer, got {raw!r}") from exc
    return raw


def _file_value(
    config: DotbotConfig | None,
    section: str | None,
    key: str,
    testbed: Testbed | None,
) -> Any:
    """The value this key has in the file layer: section > testbed > top-level."""
    if config is None:
        return None
    if section is not None:
        section_obj = getattr(config, section, None)
        value = getattr(section_obj, key, None)
        if value is not None:
            return value
    if testbed is not None:
        value = getattr(testbed, key, None)
        if value is not None:
            return value
    return getattr(config, key, None)


def resolve(
    key: str,
    *,
    section: str | None = None,
    flag: Any = None,
    config: DotbotConfig | None = None,
    testbed: Testbed | None = None,
    default: Any = None,
    environ: Mapping[str, str] = os.environ,
) -> Any:
    """Resolve one setting through the full precedence chain.

    `flag` > env (`DOTBOT_<SECTION>_<KEY>`, then shared `DOTBOT_<KEY>`) >
    file (section > testbed > top-level) > `default`.

    `section` is one of `SECTIONS` for a per-namespace key, or `None` for a
    top-level shared key (e.g. `conn`, `swarm_id`). Env values are coerced to
    the type of `default`.
    """
    if flag is not None:
        return flag
    for name in _env_candidates(section, key):
        if name in environ:
            return _coerce(environ[name], default)
    file_value = _file_value(config, section, key, testbed)
    if file_value is not None:
        return file_value
    return default
