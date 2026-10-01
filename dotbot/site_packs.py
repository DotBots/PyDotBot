# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Site packs: a site as a folder you can copy, commit or share.

A pack is a folder named after its site holding `site.toml` and optionally
`calibrations/`, the site's LH2 and camera files under their usual names.
Packs live in two homes, `sites/` beside the project's `dotbot.toml` and
~/.dotbot/sites, where `dotbot site add` puts them; the project's wins a
clash. `site` may also name a pack folder by its path.

A pack `dotbot site add` installs also holds `.approved.toml`, the broker the
person approved while adding it. The env's broker login goes to that broker,
and to the broker of a project or path pack, but not to one an installed pack
names without that approval.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dotbot.config import ConfigError, ConfigFile, SiteSection, resolve_relative
from dotbot.site import Site, check_site_name, site_from_table

PACK_FILE = "site.toml"
# The broker approved at `site add`, beside `site.toml` in an installed pack
APPROVAL_FILE = ".approved.toml"
# Where `dotbot site add` puts packs
USER_SITES_DIR = Path.home() / ".dotbot" / "sites"
# The project's packs, beside its dotbot.toml
PROJECT_SITES_DIR = "sites"


def user_sites_dir() -> Path:
    """Where `dotbot site add` puts packs."""
    return USER_SITES_DIR


@dataclass(frozen=True)
class SiteEntry:
    """One site and the pack it is read from.

    `home` is `project`, `user` or `path` (named by its path); `shadows` is
    the user pack of the same name a project pack hides.
    """

    name: str
    table: SiteSection
    pack: Path
    home: str = "user"
    shadows: Path | None = None

    @property
    def source(self) -> str:
        return str(self.pack) + (f", hiding {self.shadows}" if self.shadows else "")

    def site(self) -> Site:
        return site_from_table(self.name, self.table, self.pack)


def read_approval(folder: Path) -> str | None:
    """The broker approved for the installed pack in `folder`, if any."""
    try:
        with open(folder / APPROVAL_FILE, "rb") as handle:
            conn = tomllib.load(handle).get("conn")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return conn if isinstance(conn, str) else None


def write_approval(folder: Path, conn: str) -> None:
    """Record `conn` as the broker approved for the pack in `folder`."""
    (folder / APPROVAL_FILE).write_text(f"conn = {json.dumps(conn)}\n")


def broker_trust(entry: SiteEntry | None) -> tuple[str | None, str | None]:
    """Whether the site's broker gets the env's login: (why, None) or
    (None, why not)."""
    if entry is None:
        return None, None
    if entry.home == "project":
        return f"a pack beside your project file ({entry.pack.parent})", None
    if entry.home == "path":
        return "a pack you named by its path", None
    conn = entry.table.connection.conn if entry.table.connection else None
    approved = read_approval(entry.pack)
    if approved is not None and conn is not None and approved == conn.strip():
        return "approved at site add", None
    fix = f"approve it with `dotbot site add --force {entry.pack}`"
    if approved is None:
        return None, f"site {entry.name}'s broker was never approved; {fix}"
    return None, (
        f"site {entry.name}'s broker changed since you approved {approved}; {fix}"
    )


def site_homes(config: Any) -> list[tuple[str, Path]]:
    """The folders packs are found in, highest first, as (home, folder)."""
    homes = []
    project_dir = getattr(config, "project_dir", None)
    if project_dir is not None:
        homes.append(("project", project_dir / PROJECT_SITES_DIR))
    user = user_sites_dir()
    if not any(folder.resolve() == user.resolve() for _, folder in homes):
        homes.append(("user", user))
    return homes


def is_pack_path(value: str) -> bool:
    """Whether a `site` value names a pack folder rather than a site."""
    return "/" in value or "\\" in value or value.startswith((".", "~"))


def _packs_in(folder: Path) -> dict[str, Path]:
    packs: dict[str, Path] = {}
    if not folder.is_dir():
        return packs
    for candidate in sorted(folder.iterdir()):
        if candidate.name.startswith("."):
            continue
        if (candidate / PACK_FILE).is_file():
            packs[candidate.name] = candidate
    return packs


def find_packs(config: Any) -> dict[str, tuple[Path, str, Path | None]]:
    """Every pack in the two homes, by site name, as (folder, home, the
    lower pack it hides)."""
    found: dict[str, tuple[Path, str, Path | None]] = {}
    for home, folder in site_homes(config):
        for name, pack in _packs_in(folder).items():
            if name in found:
                first, first_home, _ = found[name]
                found[name] = (first, first_home, pack)
            else:
                found[name] = (pack, home, None)
    return found


def read_pack(folder: Path) -> SiteSection:
    """A pack's `site.toml`, validated."""
    path = folder / PACK_FILE
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read site pack {path}: {exc}") from exc
    try:
        return SiteSection.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid site pack {path}:\n{exc}") from exc


def site_catalog(config: Any) -> dict[str, SiteEntry]:
    """Every site the two homes hold."""
    return {
        name: SiteEntry(name, read_pack(pack), pack, home, shadows)
        for name, (pack, home, shadows) in find_packs(config).items()
    }


def pack_at(value: str, origin: ConfigFile | None = None) -> SiteEntry:
    """The pack a path-valued `site` names; a relative path is read from the
    folder of the file that set it (the cwd for env or a flag)."""
    folder = resolve_relative(value, origin)
    if not (folder / PACK_FILE).is_file():
        raise ConfigError(f"site {value!r} names {folder}, which holds no {PACK_FILE}")
    try:
        check_site_name(folder.name)
    except ValueError as exc:
        raise ConfigError(f"site pack {folder}: {exc}") from exc
    installed = folder.resolve().parent == user_sites_dir().resolve()
    home = "user" if installed else "path"
    return SiteEntry(folder.name, read_pack(folder), folder, home)


def resolve_site_entry(
    config: Any, name: str, origin: ConfigFile | None = None
) -> SiteEntry | None:
    """The site `name` names, reading only its own pack; None if unknown.

    `name` may be a pack's path, read from `origin`'s folder when relative.
    """
    if is_pack_path(name):
        return pack_at(name, origin)
    found = find_packs(config).get(name)
    if found is None:
        return None
    pack, home, shadows = found
    return SiteEntry(name, read_pack(pack), pack, home, shadows)
