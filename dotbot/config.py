# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Unified `dotbot` configuration: one file, one precedence chain.

This is the resolver core for the single `dotbot` config file. It is
intentionally pure - no Click, no network, no global state - so the whole
precedence/discovery story is exhaustively unit-testable without hardware.
The CLI layer feeds it the actual flags and `os.environ`.

The file mirrors the four-namespace CLI: top-level shared keys plus `[fw]` /
`[device]` / `[swarm]` / `[run]` tables, and `[sites.<name>]` entries for the
places you work in. A site may carry its usual way in, a `[connection]`
table, which site packs carry the same way.

```toml
site     = "default"
swarm_id = "0001"
site_dirs = ["sites", "~/.dotbot/sites"]    # where site packs are found, in order

[sites.default]                             # a place: where zero is, how big, its areas
anchor = "top-left corner of a 5 x 5 m floor; the field starts 1.5 m in from each wall"
extent_mm = [5000, 5000]

[sites.default.connection]                  # the site's broker, unless you set conn
conn = "mqtts://broker.local:8883"

[sites.default.areas]                       # a name that is a role has it
field   = { x = 1500, y = 1500, w = 2000, h = 2000 }
staging = { x = 1500, y = 3500, w = 2000, h = 600 }
bench   = { x = 3000, y = 1500, w = 500,  h = 500, role = "corner" }

[fw]
board = "dotbot-v3"

[run.controller]
http_port = 8000
```

Precedence for any value, highest wins:

    CLI flag  >  env (DOTBOT_<SECTION>_<KEY>, then shared DOTBOT_<KEY>)
              >  file (section value > top-level)
              >  the active site's [connection] (conn and swarm_id only)
              >  built-in default

Unknown keys are rejected (`extra='forbid'`) so a typo fails loud.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Mapping, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from dotbot.area import Role, area_role

# The four CLI namespaces, used to derive env-var names (DOTBOT_<SECTION>_<KEY>).
SECTIONS = ("fw", "device", "swarm", "run")

# Project-level config, discovered in the current directory only.
PROJECT_CONFIG_NAME = "dotbot.toml"
# The user-level config, under the same name as a project's.
USER_CONFIG_PATH = Path.home() / ".dotbot" / PROJECT_CONFIG_NAME
# The user-level config's former name, refused rather than read.
LEGACY_USER_CONFIG_NAME = "config.toml"
# The keys a site's `[connection]` table can supply.
CONNECTION_KEYS = ("conn", "swarm_id")


class ConfigError(Exception):
    """A config file is malformed or has an unknown key."""


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


class FwSources(_Strict):
    """`[fw.sources]`: the source folder `dotbot fw build` reads, per source repo."""

    dotbot_firmware: str | None = Field(None, alias="dotbot-firmware")
    swarmit: str | None = None
    mari: str | None = None


# The `[fw]` keys that became `[fw.sources]` keys.
_MOVED_SOURCE_KEYS = {
    "firmware_repo": "dotbot-firmware",
    "swarmit_repo": "swarmit",
    "mari_repo": "mari",
}


class FwSection(_Strict):
    board: str | None = None
    bare: bool | None = None
    build_config: str | None = None  # Debug | Release
    segger_dir: str | None = None
    sources: FwSources = Field(default_factory=FwSources)

    @model_validator(mode="before")
    @classmethod
    def _source_keys_moved(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for old, new in _MOVED_SOURCE_KEYS.items():
                if old in data:
                    raise ValueError(f"[fw].{old} is now the {new} key of [fw.sources]")
        return data


class DeviceSection(_Strict):
    board: str | None = None
    probe: str | None = None


class SwarmSection(_Strict):
    conn: Conn = None
    swarm_id: str | None = None
    devices: str | None = None


class AreaSection(_Strict):
    """One `[sites.<site>.areas.<name>]` table: a rectangle in frame millimetres.

    `role` is needed only when the name is not already a role.
    """

    x: int
    y: int
    w: int
    h: int
    role: Role | None = None


def _is_simulator(conn: str) -> bool:
    return conn.strip().lower() in ("simulator", "sim")


class ConnectionSection(_Strict):
    """A site's `[connection]` table: the broker it is usually reached through.

    Credentials never belong here, and neither does a serial path, which
    names a port on one machine.
    """

    conn: Conn = None
    swarm_id: str | None = None

    @model_validator(mode="after")
    def _broker_only(self) -> ConnectionSection:
        conn = self.conn
        if conn is None or _is_simulator(conn):
            return self
        if not conn.strip().lower().startswith(("mqtt://", "mqtts://")):
            raise ValueError(
                f"a site's conn is a broker URL (mqtt:// or mqtts://), not "
                f"{conn!r}: a serial port belongs to one machine, so pass it "
                "with --conn or set conn in your own dotbot.toml"
            )
        from urllib.parse import urlparse

        parsed = urlparse(conn)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(
                "a site's conn carries no credentials; drop the user:pass@ "
                "part and set DOTBOT_MQTT_USER / DOTBOT_MQTT_PASS instead"
            )
        return self


class SiteSection(_Strict):
    """One `[sites.<name>]` table: a place, its anchor, extent, areas and
    usual connection.

    `anchor` is prose and no code parses it: it is the whole specification
    for re-establishing zero in the physical world. `extent_mm` is
    `[width, height]` with zero at the extent's top-left corner, which is
    where the anchor points. A `virtual` site exists only in simulation, and
    `simulator` is the one conn it takes.
    """

    anchor: str | None = None
    extent_mm: tuple[int, int] | None = None
    virtual: bool | None = None
    connection: ConnectionSection | None = None
    areas: dict[str, AreaSection] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _virtual_conn(self) -> SiteSection:
        conn = self.connection.conn if self.connection is not None else None
        if conn is None:
            return self
        if self.virtual and not _is_simulator(conn):
            raise ValueError(f'a virtual site\'s conn is "simulator", not {conn!r}')
        if not self.virtual and _is_simulator(conn):
            raise ValueError(
                'conn = "simulator" needs virtual = true: only a site that '
                "exists in simulation alone names the simulator"
            )
        return self

    @model_validator(mode="after")
    def _one_field(self) -> SiteSection:
        fields = [
            name
            for name, area in self.areas.items()
            if area_role(name, area.role) == "field"
        ]
        if len(fields) > 1:
            raise ValueError(
                f"a site has at most one field, and {' and '.join(fields)} "
                'are both one; give all but one another role (role = "staging" '
                'or "corner") or another name'
            )
        return self


class ControllerSection(_Strict):
    http_port: int | None = None
    http_host: str | None = None
    lh2_calibration: str | None = None
    # Older than this at load, the LH2 calibration is warned about; 0: never
    lh2_calibration_max_age_days: int | None = Field(None, ge=0)
    camera_calibration: str | None = None
    camera_detect: bool | None = None
    camera_max_robots: int | None = Field(None, ge=1)
    camera_detect_share: float | None = Field(None, gt=0.0, le=1.0)
    background_map: str | None = None
    log_output: str | None = None
    csv_data_output: str | None = None
    headless: bool | None = None
    gw_address: str | None = None
    simulator_init_state: str | None = None
    simulator_area: str | None = None
    swarmit_url: str | None = None
    mrta_url: str | None = None


class GatewaySection(_Strict):
    serial_port: str | None = None
    mqtt: Conn = None


class RunSection(_Strict):
    conn: Conn = None
    swarm_id: str | None = None
    controller: ControllerSection = Field(default_factory=ControllerSection)
    gateway: GatewaySection = Field(default_factory=GatewaySection)


_DEPLOYMENT_GONE = (
    "{key} is gone: give each site its broker in a [connection] table (its "
    "site.toml, or [sites.<name>.connection]) and switch sites with "
    "`dotbot site use <name>`"
)


class DotbotConfig(_Strict):
    """The whole file: top-level shared keys + the four section tables + sites."""

    log_level: str | None = None
    conn: Conn = None
    swarm_id: str | None = None
    # The active site, and with it the coordinate frame this session's
    # positions and calibrations live in. Read by `swarm calibrate-lh2` and
    # by the controller's calibration lookup, so it is shared rather than
    # per-command.
    site: str | None = None

    # `[sites.<name>]` tables map to {name: SiteSection}.
    sites: dict[str, SiteSection] = Field(default_factory=dict)
    # Folders searched, in order, for site packs (`dotbot.site_packs`);
    # relative entries are read from this file's folder.
    site_dirs: list[str] | None = None

    fw: FwSection = Field(default_factory=FwSection)
    device: DeviceSection = Field(default_factory=DeviceSection)
    swarm: SwarmSection = Field(default_factory=SwarmSection)
    run: RunSection = Field(default_factory=RunSection)

    @model_validator(mode="before")
    @classmethod
    def _deployments_gone(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, label in (
                ("deployment", "[deployment.*]"),
                ("default_deployment", "default_deployment"),
            ):
                if key in data:
                    raise ValueError(_DEPLOYMENT_GONE.format(key=label))
        return data


# --- Discovery --------------------------------------------------------------


def discover_config_path(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
) -> Path | None:
    """Find the config file to load, highest priority first.

    1. `explicit` (the `-c/--config PATH` flag) wins outright.
    2. `DOTBOT_CONFIG` env var (an explicit path by another name).
    3. A `dotbot.toml` in the current directory (the cwd only - no walking up to
       parent directories, so the active config is always unambiguous).
    4. The user file `~/.dotbot/dotbot.toml`.
    5. None (caller uses built-in defaults).

    Raises `ConfigError` when neither 1 nor 2 applies and the user file still
    has its former name, `~/.dotbot/config.toml`.
    """
    if explicit:
        return Path(explicit)
    env_path = environ.get("DOTBOT_CONFIG")
    if env_path:
        return Path(env_path)
    check_user_config_name()

    start = Path(start_dir or Path.cwd()).resolve()
    candidate = start / PROJECT_CONFIG_NAME
    if candidate.is_file():
        return candidate

    if USER_CONFIG_PATH.is_file():
        return USER_CONFIG_PATH
    return None


def _invalid(where: str, exc: ValidationError) -> str:
    """The message for a config that fails validation; one line for a
    whole-file refusal such as a removed key."""
    errors = exc.errors()
    if len(errors) == 1 and not errors[0]["loc"]:
        message = errors[0]["msg"].removeprefix("Value error, ")
        return f"invalid config {where}: {message}"
    return f"invalid config {where}:\n{exc}"


def check_user_config_name() -> None:
    """Refuse a user config still under its former name."""
    legacy = USER_CONFIG_PATH.with_name(LEGACY_USER_CONFIG_NAME)
    if legacy.is_file() and not USER_CONFIG_PATH.exists():
        raise ConfigError(f"rename {legacy} to {USER_CONFIG_PATH}")


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
        raise ConfigError(_invalid(str(path), exc)) from exc


def load_config_text(text: str, *, source: str = "<text>") -> DotbotConfig:
    """Validate a config TOML *string*, with the same checks as `load_config`.

    `source` names the origin in error messages.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML from {source}: {exc}") from exc
    try:
        return DotbotConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_invalid(f"from {source}", exc)) from exc


def load_discovered(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
) -> tuple[DotbotConfig, Path | None]:
    """Discover + load in one step. Returns (config, source_path or None)."""
    path = discover_config_path(explicit, environ=environ, start_dir=start_dir)
    return load_config(path), path


# --- Precedence resolution --------------------------------------------------


def _env_candidates(section: str | None, key: str) -> tuple[str, ...]:
    """Env-var names to check, in priority order (Cargo's mechanical mapping).

    Sectioned key -> `DOTBOT_<SECTION>_<KEY>`, then the shared `DOTBOT_<KEY>`
    alias. Top-level key -> just `DOTBOT_<KEY>`. A nested section like
    `run.controller` flattens its dots: `DOTBOT_RUN_CONTROLLER_<KEY>`.
    """
    key_part = key.upper().replace("-", "_")
    if section:
        section_part = section.upper().replace(".", "_")
        return (f"DOTBOT_{section_part}_{key_part}", f"DOTBOT_{key_part}")
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


@dataclass(frozen=True)
class SiteLayer:
    """The active site as a precedence layer: its name, its `[connection]`,
    and whether that is an inline table in the person's own file rather than
    a site pack."""

    name: str
    connection: ConnectionSection | None = None
    inline: bool = False


@dataclass(frozen=True)
class Resolved:
    """One resolved value, the layer it came from, and the layers it hides.

    `kind` is `flag`, `env`, `file`, `site` or `default`; `source` names the
    layer for a person (`--conn`, `DOTBOT_SWARM_ID`, `dotbot.toml [run]`,
    `site c405-arena`); `hidden` holds the (source, value) pairs of the lower
    layers that set the key too, highest first. `inline` marks a `site`
    value read from an inline `[sites.<name>]` table rather than a pack.
    """

    value: Any
    kind: str
    source: str
    hidden: tuple[tuple[str, Any], ...] = ()
    inline: bool = False

    @property
    def user_set(self) -> bool:
        """True when the person set this value: a flag, the env or their own
        file, an inline site table in it included."""
        return self.kind in ("flag", "env", "file") or (
            self.kind == "site" and self.inline
        )


def _layers(
    config: DotbotConfig | None,
    section: str | None,
    key: str,
    site: SiteLayer | None,
    config_label: str,
) -> list[tuple[str, str, Any]]:
    """The file and site layers for `key`, highest first, as (kind, source, value).

    `section` may be nested (dot-separated, e.g. `run.controller`); each part
    is walked with getattr. The site layer counts only for `CONNECTION_KEYS`.
    """
    layers: list[tuple[str, str, Any]] = []
    if config is not None:
        if section is not None:
            section_obj: Any = config
            for part in section.split("."):
                section_obj = getattr(section_obj, part, None)
            layers.append(
                ("file", f"{config_label} [{section}]", getattr(section_obj, key, None))
            )
        layers.append(("file", config_label, getattr(config, key, None)))
    if site is not None and site.connection is not None and key in CONNECTION_KEYS:
        layers.append(("site", f"site {site.name}", getattr(site.connection, key)))
    return layers


def resolve_source(
    key: str,
    *,
    section: str | None = None,
    flag: Any = None,
    flag_name: str | None = None,
    config: DotbotConfig | None = None,
    config_label: str = "the config file",
    site: SiteLayer | None = None,
    default: Any = None,
    environ: Mapping[str, str] = os.environ,
) -> Resolved:
    """Resolve one setting through the full precedence chain, with its source.

    `flag` > env (`DOTBOT_<SECTION>_<KEY>`, then shared `DOTBOT_<KEY>`) >
    file (section > top-level) > the active site's `[connection]` > `default`.

    `section` is one of `SECTIONS` for a per-namespace key, a dotted path for
    a nested table (e.g. `run.controller`), or `None` for a top-level shared
    key (e.g. `conn`, `swarm_id`). Env values are coerced to the type of
    `default`. `flag_name` and `config_label` only name the layers.
    """
    found: list[tuple[str, str, Any]] = []
    if flag is not None:
        found.append(("flag", flag_name or "the command line", flag))
    for name in _env_candidates(section, key):
        if name in environ:
            found.append(("env", name, _coerce(environ[name], default)))
    found += [
        layer
        for layer in _layers(config, section, key, site, config_label)
        if layer[2] is not None
    ]
    if not found:
        return Resolved(default, "default", "the default")
    (kind, source, value), rest = found[0], found[1:]
    hidden = tuple((src, val) for _, src, val in rest)
    inline = kind == "site" and site is not None and site.inline
    return Resolved(value, kind, source, hidden, inline)


def resolve(
    key: str,
    *,
    section: str | None = None,
    flag: Any = None,
    config: DotbotConfig | None = None,
    site: SiteLayer | None = None,
    default: Any = None,
    environ: Mapping[str, str] = os.environ,
) -> Any:
    """The value `resolve_source` settles on, for callers that need no source."""
    return resolve_source(
        key,
        section=section,
        flag=flag,
        config=config,
        site=site,
        default=default,
        environ=environ,
    ).value
