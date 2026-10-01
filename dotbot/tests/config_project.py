# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A project folder for tests: its dotbot.toml and its site packs."""

import tomllib
from pathlib import Path

import tomlkit


def write_project(config_file: Path, text: str) -> Path:
    """Write `text` as a project's dotbot.toml, each `[sites.<name>]` table
    moved to `sites/<name>/site.toml` beside it."""
    data = tomllib.loads(text)
    for name, table in data.pop("sites", {}).items():
        pack = config_file.parent / "sites" / name
        pack.mkdir(parents=True, exist_ok=True)
        (pack / "site.toml").write_text(tomlkit.dumps(table))
    config_file.write_text(tomlkit.dumps(data))
    return config_file
