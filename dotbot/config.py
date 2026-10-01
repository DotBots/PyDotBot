# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Unified `dotbot` configuration: layered TOML files, one precedence chain.

Pure - no Click, no network, no global state - so discovery and precedence
are unit-testable without hardware. The CLI layer feeds it the flags and
`os.environ`.

Three files can be in use, each validated on its own and then merged key by
key, the closest to you winning:

    ./dotbot.local.toml     you, in this project (untracked)
    ./dotbot.toml           the project (committed; or the -c FILE)
    ~/.dotbot/dotbot.toml   you, on this machine; the only home of [login]

Precedence for any value, highest wins:

    CLI flag  >  env (DOTBOT_<SECTION>_<KEY>, then shared DOTBOT_<KEY>)
              >  dotbot.local.toml  >  dotbot.toml  >  ~/.dotbot/dotbot.toml
              >  the active site's [connection] (conn and swarm_id only)
              >  built-in default

Unknown keys are rejected (`extra='forbid'`) so a typo fails loud, and a
removed key names where it went.
"""

from __future__ import annotations

import difflib
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
    PrivateAttr,
    ValidationError,
    model_validator,
)

from dotbot.area import Role, area_role

# The sections whose keys derive env-var names (DOTBOT_<SECTION>_<KEY>).
SECTIONS = ("fw", "device", "run")

# The project file, discovered in the current directory only.
PROJECT_CONFIG_NAME = "dotbot.toml"
# `<stem>.local.toml` beside the project file is your overlay on it.
LOCAL_CONFIG_SUFFIX = ".local.toml"
# The user file: you, on this machine.
USER_CONFIG_PATH = Path.home() / ".dotbot" / PROJECT_CONFIG_NAME
# The user file's former name, refused rather than read.
LEGACY_USER_CONFIG_NAME = "config.toml"
# The keys a site's `[connection]` table can supply.
CONNECTION_KEYS = ("conn", "swarm_id")

# DOTBOT_* variables read outside the config schema.
EXTRA_ENV = frozenset(
    {
        "DOTBOT_CONFIG",
        "DOTBOT_MQTT_USER",
        "DOTBOT_MQTT_PASS",
        "DOTBOT_MQTT_INSECURE",
        "DOTBOT_CONTROLLER_URL",
        "DOTBOT_CONTROLLER_PORT",
        "DOTBOT_CONTROLLER_USE_HTTPS",
        "DOTBOT_SCT_PATH",
        "DOTBOT_ADDRESS",
    }
)


class ConfigError(Exception):
    """A config file is malformed or has an unknown key."""


def _check_conn(value: str | None) -> str | None:
    """Validate a connection string with the same parser the `--conn` flag uses.

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


def _refuse_removed(data: Any, removed: Mapping[str, str]) -> Any:
    """Raise the message for the first removed key `data` still sets."""
    if isinstance(data, dict):
        for key, message in removed.items():
            if key in data:
                raise ValueError(message)
    return data


# All fields are Optional and default to None: the model captures only what a
# file *explicitly* set, so the resolver can tell "unset" from "set to the
# default". Built-in defaults live in code, not here.


class FwSources(_Strict):
    """`[fw.sources]`: the source folder `dotbot fw build` reads, per source repo."""

    dotbot_firmware: str | None = Field(None, alias="dotbot-firmware")
    swarmit: str | None = None
    mari: str | None = None


_FW_REMOVED = {
    "firmware_repo": "[fw].firmware_repo is now the dotbot-firmware key of [fw.sources]",
    "swarmit_repo": "[fw].swarmit_repo is now the swarmit key of [fw.sources]",
    "mari_repo": "[fw].mari_repo is now the mari key of [fw.sources]",
}


class FwSection(_Strict):
    board: str | None = None
    bare: bool | None = None
    build_config: str | None = None  # Debug | Release
    segger_dir: str | None = None
    artifacts_dir: str | None = None
    sources: FwSources = Field(default_factory=FwSources)

    @model_validator(mode="before")
    @classmethod
    def _removed(cls, data: Any) -> Any:
        return _refuse_removed(data, _FW_REMOVED)


class DeviceSection(_Strict):
    board: str | None = None
    probe: str | None = None


class AreaSection(_Strict):
    """One `[areas.<name>]` table of a site: a rectangle in frame millimetres.

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
                "with --conn or set conn in your own config"
            )
        from urllib.parse import urlparse

        parsed = urlparse(conn)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(
                "a site's conn carries no credentials; drop the user:pass@ "
                "part and save a login with `dotbot config login HOST`"
            )
        return self


class SiteSection(_Strict):
    """A site pack's `site.toml`: a place, its anchor, extent, areas and
    usual connection.

    `anchor` is prose and no code parses it: it is the whole specification
    for re-establishing zero in the physical world. `extent_mm` is
    `[width, height]` with zero at the extent's top-left corner, which is
    where the anchor points.
    """

    anchor: str | None = None
    extent_mm: tuple[int, int] | None = None
    connection: ConnectionSection | None = None
    areas: dict[str, AreaSection] = Field(default_factory=dict)

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


_CONTROLLER_REMOVED = {
    key: f"[run.controller] {key} is gone: pass {flag} instead"
    for key, flag in (
        ("background_map", "--background-map"),
        ("log_output", "--log-output"),
        ("csv_data_output", "--csv-data-output"),
        ("gw_address", "--gw-address"),
        ("simulator_init_state", "--simulator-init-state"),
    )
}


class ControllerSection(_Strict):
    http_port: int | None = None
    http_host: str | None = None
    headless: bool | None = None
    lh2_calibration: str | None = None
    # Older than this at load, the LH2 calibration is warned about; 0: never
    lh2_calibration_max_age_days: int | None = Field(None, ge=0)
    camera_calibration: str | None = None
    camera_detect: bool | None = None
    camera_max_robots: int | None = Field(None, ge=1)
    camera_detect_share: float | None = Field(None, gt=0.0, le=1.0)
    simulator_area: str | None = None
    swarmit_url: str | None = None
    mrta_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _removed(cls, data: Any) -> Any:
        return _refuse_removed(data, _CONTROLLER_REMOVED)


_RUN_REMOVED = {
    "conn": "[run] conn is now the top-level conn",
    "swarm_id": "[run] swarm_id is now the top-level swarm_id",
    "gateway": "[run.gateway] is gone: pass --port / --mqtt-url, or set conn",
}


class RunSection(_Strict):
    controller: ControllerSection = Field(default_factory=ControllerSection)

    @model_validator(mode="before")
    @classmethod
    def _removed(cls, data: Any) -> Any:
        return _refuse_removed(data, _RUN_REMOVED)


class Login(_Strict):
    """One `[login."<broker host>"]` table: the login sent to that broker."""

    user: str
    password: str | None = None


_SITE_GONE = (
    "`dotbot site use <name>` switches sites; give each one its broker in "
    "the [connection] table of its site.toml"
)
_TOP_REMOVED = {
    "deployment": f"[deployment.*] is gone: {_SITE_GONE}",
    "default_deployment": f"default_deployment is gone: {_SITE_GONE}",
    "sites": (
        "inline [sites.<name>] tables are gone: move each one to "
        "sites/<name>/site.toml beside this file"
    ),
    "site_dirs": (
        "site_dirs is gone: site packs live in sites/ beside the project's "
        "dotbot.toml and in ~/.dotbot/sites, and site can name a pack's path"
    ),
    "log_level": "log_level is gone: pass --log-level instead",
    "swarm": "[swarm] is gone: conn and swarm_id are top-level keys",
}


@dataclass(frozen=True)
class ConfigFile:
    """One config file in use: which layer it is, where, and what it set.

    `kind` is `user`, `project` or `local`.
    """

    kind: str
    path: Path
    data: dict
    config: DotbotConfig

    @property
    def label(self) -> str:
        return display_path(self.path)


class DotbotConfig(_Strict):
    """A config file's keys, or the merge of every file in use."""

    conn: Conn = None
    swarm_id: str | None = None
    # The active site: a pack's name, or the path of a pack folder.
    site: str | None = None

    fw: FwSection = Field(default_factory=FwSection)
    device: DeviceSection = Field(default_factory=DeviceSection)
    run: RunSection = Field(default_factory=RunSection)
    # Broker logins keyed by host; only the user file may hold them.
    login: dict[str, Login] = Field(default_factory=dict)

    # The files merged into this config, lowest first, and the file that
    # set each leaf key.
    _files: tuple[ConfigFile, ...] = PrivateAttr(default=())
    _origins: dict[tuple[str, ...], ConfigFile] = PrivateAttr(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _removed(cls, data: Any) -> Any:
        return _refuse_removed(data, _TOP_REMOVED)

    @property
    def files(self) -> tuple[ConfigFile, ...]:
        return self._files

    def file(self, kind: str) -> ConfigFile | None:
        for item in self._files:
            if item.kind == kind:
                return item
        return None

    def origin(self, *path: str) -> ConfigFile | None:
        """The file that set the key at `path` (TOML spelling), if any."""
        return self._origins.get(tuple(path))

    @property
    def project_path(self) -> Path | None:
        found = self.file("project")
        return found.path if found is not None else None

    @property
    def project_dir(self) -> Path | None:
        path = self.project_path
        return path.resolve().parent if path is not None else None


def display_path(path: Path) -> str:
    """`path` as a person reads it: relative to the cwd when inside it,
    `~/...` under the home directory, else absolute."""
    resolved = Path(path).absolute()
    cwd, home = Path.cwd().absolute(), Path.home().absolute()
    if resolved.is_relative_to(cwd) and not home.is_relative_to(cwd):
        return resolved.relative_to(cwd).as_posix()
    if resolved.is_relative_to(home):
        return "~/" + resolved.relative_to(home).as_posix()
    return str(resolved)


# --- Discovery --------------------------------------------------------------


def local_path_for(project: Path) -> Path:
    """The overlay beside a project file: `<stem>.local.toml`."""
    return project.with_name(project.stem + LOCAL_CONFIG_SUFFIX)


def discover_files(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
) -> list[tuple[str, Path]]:
    """The config files in use, lowest priority first, as (kind, path).

    The user file `~/.dotbot/dotbot.toml`; the project file, which is
    `explicit` (`-c`), else `DOTBOT_CONFIG`, else a `dotbot.toml` in the
    current directory (no walking up); and `<stem>.local.toml` beside it.

    Raises `ConfigError` when the user file still has its former name.
    """
    check_user_config_name()
    files: list[tuple[str, Path]] = []
    user = USER_CONFIG_PATH
    if user.is_file():
        files.append(("user", user))
    project: Path | None = None
    if explicit:
        project = Path(explicit)
    elif environ.get("DOTBOT_CONFIG"):
        project = Path(environ["DOTBOT_CONFIG"])
    else:
        candidate = Path(start_dir or Path.cwd()).resolve() / PROJECT_CONFIG_NAME
        if candidate.is_file():
            project = candidate
    if project is not None and not (
        user.is_file() and project.exists() and project.resolve() == user.resolve()
    ):
        files.append(("project", project))
        local = local_path_for(project)
        if local.is_file():
            files.append(("local", local))
    return files


def _invalid(where: str, exc: ValidationError) -> str:
    """The message for a config that fails validation; one line for a
    whole-table refusal such as a removed key."""
    errors = exc.errors()
    tables = {"fw", "device", "run", "controller"}
    if (
        len(errors) == 1
        and errors[0]["type"] == "value_error"
        and set(errors[0]["loc"]) <= tables
    ):
        message = errors[0]["msg"].removeprefix("Value error, ")
        return f"invalid config {where}: {message}"
    return f"invalid config {where}:\n{exc}"


def check_user_config_name() -> None:
    """Refuse a user config still under its former name."""
    legacy = USER_CONFIG_PATH.with_name(LEGACY_USER_CONFIG_NAME)
    if legacy.is_file() and not USER_CONFIG_PATH.exists():
        raise ConfigError(
            f"{legacy} is the user config's former name; rename it to "
            f"{USER_CONFIG_PATH}"
        )


def _read(path: Path) -> dict:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read config {path}: {exc}") from exc


def _validate(data: dict, where: str) -> DotbotConfig:
    try:
        return DotbotConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_invalid(where, exc)) from exc


def load_config(path: os.PathLike[str] | str | None) -> DotbotConfig:
    """Load and validate one config file. `None` -> an empty config.

    Raises `ConfigError` (with the file path) on bad TOML, an unknown key, a
    wrong-typed value, or an invalid connection string.
    """
    if path is None:
        return DotbotConfig()
    return _validate(_read(Path(path)), str(path))


def load_config_text(text: str, *, source: str = "<text>") -> DotbotConfig:
    """Validate a config TOML *string*, with the same checks as `load_config`."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML from {source}: {exc}") from exc
    return _validate(data, f"from {source}")


def _merge(into: dict, data: dict, file: ConfigFile, origins: dict, path=()) -> None:
    """Merge `data` into `into` key by key, recording `file` as each leaf's
    origin."""
    for key, value in data.items():
        here = (*path, key)
        if isinstance(value, dict):
            target = into.get(key)
            if not isinstance(target, dict):
                target = into[key] = {}
            _merge(target, value, file, origins, here)
        else:
            into[key] = value
            origins[here] = file


def load_files(files: list[tuple[str, Path]]) -> DotbotConfig:
    """Validate each file on its own, then merge them, later ones winning."""
    loaded = []
    for kind, path in files:
        data = _read(path)
        config = _validate(data, str(path))
        if kind != "user" and config.login:
            raise ConfigError(
                f"invalid config {path}: [login] belongs only in "
                f"{display_path(USER_CONFIG_PATH)}, which is never committed; "
                "save one with `dotbot config login HOST`"
            )
        loaded.append(ConfigFile(kind, path, data, config))
    merged: dict = {}
    origins: dict = {}
    for item in loaded:
        _merge(merged, item.data, item, origins)
    config = _validate(merged, "(the merged files)") if loaded else DotbotConfig()
    config._files = tuple(loaded)
    config._origins = origins
    return config


def load_discovered(
    explicit: os.PathLike[str] | str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    start_dir: os.PathLike[str] | str | None = None,
) -> DotbotConfig:
    """Discover and merge every config file in use."""
    return load_files(discover_files(explicit, environ=environ, start_dir=start_dir))


def resolve_relative(value: str, origin: ConfigFile | None) -> Path:
    """A path a config value names: `~` expanded, a relative one read from
    the folder of the file that set it (the cwd for env or a flag)."""
    path = Path(value).expanduser()
    if not path.is_absolute() and origin is not None:
        path = origin.path.resolve().parent / path
    return Path(os.path.normpath(path.absolute()))


# --- Env names --------------------------------------------------------------


def _model_env_names(model: type[BaseModel], section: str | None) -> set[str]:
    names: set[str] = set()
    for name, field in model.model_fields.items():
        key = field.alias or name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested = key if section is None else f"{section}.{key}"
            names |= _model_env_names(annotation, nested)
            continue
        names.update(_env_candidates(section, key))
    return names


def known_env_names() -> frozenset[str]:
    """Every DOTBOT_* variable dotbot reads."""
    names = _model_env_names(DotbotConfig, None) - {"DOTBOT_LOGIN"}
    return frozenset(names | EXTRA_ENV)


def unknown_env(environ: Mapping[str, str] = os.environ) -> list[tuple[str, str]]:
    """The DOTBOT_* variables nothing reads, each with a close known name
    ("" when none is close)."""
    known = known_env_names()
    unknown = []
    for name in sorted(environ):
        if name.startswith("DOTBOT_") and name not in known:
            close = difflib.get_close_matches(name, known, n=1, cutoff=0.8)
            unknown.append((name, close[0] if close else ""))
    return unknown


# --- Precedence resolution --------------------------------------------------


def _env_candidates(section: str | None, key: str) -> tuple[str, ...]:
    """Env-var names to check, in priority order (Cargo's mechanical mapping).

    Sectioned key -> `DOTBOT_<SECTION>_<KEY>`, then the shared `DOTBOT_<KEY>`
    alias. Top-level key -> just `DOTBOT_<KEY>`. A nested section like
    `run.controller` flattens its dots: `DOTBOT_RUN_CONTROLLER_<KEY>`.
    """
    key_part = key.upper().replace("-", "_")
    if section:
        section_part = section.upper().replace(".", "_").replace("-", "_")
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
    if isinstance(like, float):
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(f"expected a number, got {raw!r}") from exc
    return raw


@dataclass(frozen=True)
class SiteLayer:
    """The active site as a precedence layer: its name, its `[connection]`,
    and whether its broker is trusted with the env's login.

    `trust` says why it is (e.g. `approved at site add`); when it is None,
    `distrust` says why not, as the clause of a warning.
    """

    name: str
    connection: ConnectionSection | None = None
    trust: str | None = None
    distrust: str | None = None


@dataclass(frozen=True)
class Resolved:
    """One resolved value, the layer it came from, and the layers it hides.

    `kind` is `flag`, `env`, `file`, `site` or `default`; `source` names the
    layer for a person (`--conn`, `DOTBOT_SWARM_ID`, `dotbot.local.toml`,
    `site c405-arena`); `hidden` holds the (source, value) pairs of the lower
    layers that set the key too, highest first. `site_trust` and
    `site_distrust` carry the site layer's, for a `site` value.
    """

    value: Any
    kind: str
    source: str
    hidden: tuple[tuple[str, Any], ...] = ()
    site_trust: str | None = None
    site_distrust: str | None = None

    @property
    def trust(self) -> str | None:
        """Why this value is trusted with the env's broker login, or None."""
        if self.kind in ("flag", "env", "file"):
            return f"you named it ({self.source})"
        if self.kind == "site":
            return self.site_trust
        return None


def _lookup(config: DotbotConfig, section: str | None, key: str) -> Any:
    obj: Any = config
    if section is not None:
        for part in section.split("."):
            obj = getattr(obj, part.replace("-", "_"), None)
    return getattr(obj, key.replace("-", "_"), None)


def _layers(
    config: DotbotConfig | None,
    section: str | None,
    key: str,
    site: SiteLayer | None,
    config_label: str,
) -> list[tuple[str, str, Any]]:
    """The file and site layers for `key`, highest first, as (kind, source, value).

    A merged config contributes one layer per file; a lone one, one layer
    named `config_label`. The site layer counts only for `CONNECTION_KEYS`.
    """
    layers: list[tuple[str, str, Any]] = []
    if config is not None:
        if config.files:
            for item in reversed(config.files):
                layers.append(("file", item.label, _lookup(item.config, section, key)))
        else:
            layers.append(("file", config_label, _lookup(config, section, key)))
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

    `section` is one of `SECTIONS`, a dotted path for a nested table (e.g.
    `run.controller`), or `None` for a top-level key (`conn`, `swarm_id`).
    Env values are coerced to the type of `default`.
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
    if kind == "site" and site is not None:
        return Resolved(value, kind, source, hidden, site.trust, site.distrust)
    return Resolved(value, kind, source, hidden)


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
