# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Site packs: a site as a folder you can copy, commit or share.

A pack is a folder named after its site holding `site.toml`, the keys a
`[sites.<name>]` table holds, and optionally `calibrations/`, the site's LH2
and camera files under their usual names. Packs are found in the `site_dirs`
folders, in order; an inline `[sites.<name>]` table wins over a pack of the
same name.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dotbot.config import ConfigError, SiteSection
from dotbot.site import Site, site_from_table

PACK_FILE = "site.toml"
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
