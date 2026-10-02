# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A site pack's `site.toml` as a model the site editor edits, and back.

`site_model` reads the keys the editor draws from a tomlkit document;
`patch` writes a model back by assigning only what differs, so comments,
blank lines, key order and keys the editor does not model survive.
"""

from __future__ import annotations

import hashlib
import tomllib
from typing import Any

import tomlkit
from pydantic import ValidationError
from tomlkit.items import InlineTable, SingleKey, Table
from tomlkit.toml_document import TOMLDocument

from dotbot.config import SiteSection

AREA_KEYS = ("x", "y", "w", "h")


class SiteTomlError(ValueError):
    """A model the file cannot take, or a patched file the schema refuses."""


def revision(data: bytes) -> str:
    """The revision a page edits against: the SHA-256 of the file's bytes."""
    return hashlib.sha256(data).hexdigest()


def _comment(item: Any) -> str | None:
    comment = item.trivia.comment.strip().removeprefix("#").strip()
    return comment or None


def _areas_table(doc: TOMLDocument) -> Table | None:
    areas = doc.get("areas")
    return areas if isinstance(areas, Table) else None


def site_model(doc: TOMLDocument) -> dict[str, Any]:
    """The editor's model of a `site.toml`: anchor, extent, areas in file
    order with their declared role and comment, and the connection."""
    areas = []
    for name, item in (_areas_table(doc) or {}).items():
        areas.append(
            {
                "name": name,
                **{key: int(item[key]) for key in AREA_KEYS},
                "role": item.get("role"),
                "comment": _comment(item),
            }
        )
    extent = doc.get("extent_mm")
    connection = doc.get("connection")
    return {
        "anchor": doc.get("anchor"),
        "extent_mm": [int(v) for v in extent] if extent is not None else None,
        "areas": areas,
        "connection": dict(connection) if connection is not None else None,
    }


def _set(container: Any, key: str, value: Any) -> None:
    """Assign `value` unless it is already there; None removes the key."""
    if value is None:
        if key in container:
            del container[key]
    elif container.get(key) != value:
        container[key] = value


def _set_comment(item: Any, comment: str | None) -> None:
    if _comment(item) == (comment or None):
        return
    if comment:
        if not item.trivia.comment_ws:
            item.trivia.comment_ws = "  "
        item.trivia.comment = f"# {comment}"
    else:
        item.trivia.comment = ""
        item.trivia.comment_ws = ""


def _new_area(inline: bool, area: dict[str, Any]) -> Table | InlineTable:
    item = tomlkit.inline_table() if inline else tomlkit.table()
    if area.get("role") is not None:
        item["role"] = area["role"]
    for key in AREA_KEYS:
        item[key] = area[key]
    _set_comment(item, area.get("comment"))
    return item


def _check_names(areas: list[dict[str, Any]]) -> None:
    seen = set()
    for area in areas:
        name = area["name"]
        if not isinstance(name, str) or not name.strip():
            raise SiteTomlError("an area needs a name")
        if name != name.strip():
            raise SiteTomlError(f"area {name!r}: no spaces around the name")
        if "," in name:
            raise SiteTomlError(
                f"area {name!r}: a comma makes the name read as an x,y,w,h literal"
            )
        if name in seen:
            raise SiteTomlError(f"two areas are named {name!r}")
        seen.add(name)


def _patch_areas(doc: TOMLDocument, areas: list[dict[str, Any]]) -> None:
    table = _areas_table(doc)
    if table is None:
        if not areas:
            return
        table = tomlkit.table(is_super_table=True)
        doc["areas"] = table
    inline = any(isinstance(item, InlineTable) for item in table.values())
    renames = {
        area["was"]: area["name"]
        for area in areas
        if area.get("was") is not None and area["was"] != area["name"]
    }
    kept = {area.get("was") or area["name"] for area in areas}
    for name in [name for name in table if name not in kept]:
        del table[name]
    for was, name in renames.items():
        if was not in table:
            raise SiteTomlError(f"area {was!r} is not in the file")
        # tomlkit has no public rename; this keeps the area's place, comment
        # and layout
        item = table[was]
        table.value._replace(was, name, item)
        if isinstance(item, Table) and item.display_name:
            old_key = SingleKey(was).as_string()
            prefix = item.display_name.removesuffix(old_key)
            item.display_name = prefix + SingleKey(name).as_string()
        if isinstance(item, Table):
            item.name = name
    for area in areas:
        name = area["name"]
        if name not in table:
            table[name] = _new_area(inline, area)
            continue
        item = table[name]
        _set(item, "role", area.get("role"))
        for key in AREA_KEYS:
            _set(item, key, area[key])
        _set_comment(item, area.get("comment"))
    if not table:
        del doc["areas"]


def patch(doc: TOMLDocument, model: dict[str, Any]) -> TOMLDocument:
    """Write `model` into `doc` in place, changing only what differs.

    An area's `was` names it as the file does, so a rename is told from a
    delete and an add. `connection` is not written.
    """
    areas = model.get("areas") or []
    _check_names(areas)
    anchor = model.get("anchor")
    _set(doc, "anchor", anchor if anchor else None)
    extent = model.get("extent_mm")
    if extent is None:
        _set(doc, "extent_mm", None)
    elif "extent_mm" not in doc:
        doc["extent_mm"] = [int(v) for v in extent]
    elif [int(v) for v in doc["extent_mm"]] != [int(v) for v in extent]:
        array = doc["extent_mm"]
        array.clear()
        array.extend(int(v) for v in extent)
    _patch_areas(doc, areas)
    return doc


def validate(text: str) -> SiteSection:
    """`text` held to the schema a pack is read with; SiteTomlError if not."""
    try:
        return SiteSection.model_validate(tomllib.loads(text))
    except tomllib.TOMLDecodeError as exc:
        raise SiteTomlError(f"not valid TOML: {exc}") from exc
    except ValidationError as exc:
        raise SiteTomlError(str(exc)) from exc


def patched_text(text: str, model: dict[str, Any]) -> str:
    """`text` with `model` written into it, validated."""
    doc = tomlkit.parse(text)
    result = tomlkit.dumps(patch(doc, model))
    validate(result)
    return result
