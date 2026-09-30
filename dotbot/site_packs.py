# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Site packs: a site as a folder you can copy, commit or share.

A pack is a folder named after its site holding `site.toml`, the keys a
`[sites.<name>]` table holds, and optionally `calibrations/`, the site's LH2
and camera files under their usual names. Packs are found in the `site_dirs`
folders, in order; an inline `[sites.<name>]` table wins over a pack of the
same name.

A pack `dotbot site add` installs also holds `.approved.toml`, the broker the
person approved while adding it. The env's broker login goes to that broker
and to the broker of a pack found anywhere else in `site_dirs`, the person's
own folders, but not to one a pack in ~/.dotbot/sites names without that
approval.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dotbot.config import ConfigError, SiteSection
from dotbot.site import Site, site_from_table

PACK_FILE = "site.toml"
# The broker approved at `site add`, beside `site.toml` in an installed pack
APPROVAL_FILE = ".approved.toml"
# Where `dotbot site add` puts packs, searched last when `site_dirs` is unset
USER_SITES_DIR = Path.home() / ".dotbot" / "sites"
# Searched first when `site_dirs` is unset, from the config file's folder
PROJECT_SITES_DIR = "sites"


def user_sites_dir() -> Path:
    """Where `dotbot site add` puts packs."""
    return USER_SITES_DIR


@dataclass(frozen=True)
class SiteEntry:
    """One site the config can name, and where it was read from.

    `pack` is the pack folder, None for an inline table; `shadows` is the pack
    an inline table of the same name hides.
    """

    name: str
    table: SiteSection
    pack: Path | None = None
    shadows: Path | None = None

    @property
    def source(self) -> str:
        if self.pack is not None:
            return str(self.pack)
        return "inline" + (f", shadowing {self.shadows}" if self.shadows else "")

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


def is_installed(pack: Path) -> bool:
    """Whether `pack` is one `dotbot site add` put in ~/.dotbot/sites."""
    return pack.resolve().parent == user_sites_dir().resolve()


def broker_trust(entry: SiteEntry | None) -> tuple[str | None, str | None]:
    """Whether the site's broker gets the env's login: (why, None) or
    (None, why not)."""
    if entry is None:
        return None, None
    if entry.pack is None:
        return "an inline site table of your own file", None
    if not is_installed(entry.pack):
        return f"a pack in your site_dirs ({entry.pack.parent})", None
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


def site_dirs(config: Any, config_path: Path | None) -> list[Path]:
    """The folders searched for packs; relative ones from the config's folder."""
    entries = getattr(config, "site_dirs", None)
    base = config_path.parent if config_path is not None else Path.cwd()
    if entries is None:
        return [base / PROJECT_SITES_DIR, user_sites_dir()]
    folders = []
    for entry in entries:
        folder = Path(entry).expanduser()
        folders.append(folder if folder.is_absolute() else base / folder)
    return folders


def find_packs(folders: list[Path]) -> dict[str, Path]:
    """Every pack in `folders`, by site name; the first folder wins a clash."""
    packs: dict[str, Path] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir()):
            if candidate.name.startswith("."):
                continue
            if (candidate / PACK_FILE).is_file():
                packs.setdefault(candidate.name, candidate)
    return packs


def read_pack(folder: Path) -> SiteSection:
    """A pack's `site.toml`, held to the same schema as an inline table."""
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


def site_catalog(config: Any, config_path: Path | None) -> dict[str, SiteEntry]:
    """Every site the config can name: its inline tables, then its packs."""
    packs = find_packs(site_dirs(config, config_path))
    inline = getattr(config, "sites", None) or {}
    catalog = {
        name: SiteEntry(name, table, shadows=packs.get(name))
        for name, table in inline.items()
    }
    for name, folder in packs.items():
        if name not in catalog:
            catalog[name] = SiteEntry(name, read_pack(folder), pack=folder)
    return catalog


def resolve_site_entry(
    config: Any, config_path: Path | None, name: str
) -> SiteEntry | None:
    """The site `name` names, reading only its own pack; None if unknown."""
    packs = find_packs(site_dirs(config, config_path))
    inline = getattr(config, "sites", None) or {}
    if name in inline:
        return SiteEntry(name, inline[name], shadows=packs.get(name))
    if name in packs:
        return SiteEntry(name, read_pack(packs[name]), pack=packs[name])
    return None
