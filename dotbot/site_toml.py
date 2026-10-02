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
from tomlkit.items import AoT, InlineTable, SingleKey, Table
from tomlkit.toml_document import TOMLDocument

from dotbot.config import SiteSection

AREA_KEYS = ("x", "y", "w", "h")
# Each table of named tables the editor models, and its keys in file order;
# the first may be left out (None), the rest are whole millimetres
NAMED = {"areas": ("role", *AREA_KEYS), "objects": ("kind", "x", "y")}
# An object's optional heading, written only when not zero
HEADING = "heading_deg"
# The arrays of tables of barriers, and the fewest points each entry takes
BARRIERS = {"walls": 2, "obstacles": 3}


class SiteTomlError(ValueError):
    """A model the file cannot take, or a patched file the schema refuses."""


def revision(data: bytes) -> str:
    """The revision a page edits against: the SHA-256 of the file's bytes."""
    return hashlib.sha256(data).hexdigest()


def _comment(item: Any) -> str | None:
    comment = item.trivia.comment.strip().removeprefix("#").strip()
    return comment or None


def _named_table(doc: TOMLDocument, key: str) -> Table | None:
    table = doc.get(key)
    return table if isinstance(table, Table) else None


def _areas_table(doc: TOMLDocument) -> Table | None:
    return _named_table(doc, "areas")


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
        **{key: _barriers_model(doc, key) for key in BARRIERS},
        "objects": [
            {
                "name": name,
                "kind": item.get("kind"),
                "x": int(item["x"]),
                "y": int(item["y"]),
                HEADING: float(item.get(HEADING, 0.0)),
                "comment": _comment(item),
            }
            for name, item in (_named_table(doc, "objects") or {}).items()
        ],
    }


def _barriers_model(doc: TOMLDocument, key: str) -> list[dict[str, Any]]:
    items = doc.get(key)
    if not isinstance(items, AoT):
        return []
    return [
        {
            "name": item.get("name"),
            "points": [[int(x), int(y)] for x, y in item["points"]],
            "comment": _comment(item),
        }
        for item in items
    ]


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


def _new_entry(key: str, inline: bool, entry: dict[str, Any]) -> Table | InlineTable:
    item = tomlkit.inline_table() if inline else tomlkit.table()
    first, *numbers = NAMED[key]
    if entry.get(first) is not None:
        item[first] = entry[first]
    for field in numbers:
        item[field] = entry[field]
    if entry.get(HEADING):
        item[HEADING] = entry[HEADING]
    _set_comment(item, entry.get("comment"))
    return item


def _check_names(entries: list[dict[str, Any]], what: str = "area") -> None:
    seen = set()
    for entry in entries:
        name = entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise SiteTomlError(f"an {what} needs a name")
        if name != name.strip():
            raise SiteTomlError(f"{what} {name!r}: no spaces around the name")
        if "," in name:
            raise SiteTomlError(
                f"{what} {name!r}: a comma makes the name read as an x,y,w,h literal"
            )
        if name in seen:
            raise SiteTomlError(f"two {what}s are named {name!r}")
        seen.add(name)


def _patch_areas(doc: TOMLDocument, areas: list[dict[str, Any]]) -> None:
    _patch_named(doc, "areas", areas)


def _patch_named(doc: TOMLDocument, key: str, areas: list[dict[str, Any]]) -> None:
    """Write one table of named tables (`areas`, `objects`); an entry's `was`
    names it as the file does, so a rename is told from a delete and an add."""
    table = _named_table(doc, key)
    if table is None:
        if not areas:
            return
        table = tomlkit.table(is_super_table=True)
        if not tomlkit.dumps(doc).endswith("\n\n"):
            doc.add(tomlkit.nl())
        doc[key] = table
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
            raise SiteTomlError(f"{key} entry {was!r} is not in the file")
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
            table[name] = _new_entry(key, inline, area)
            continue
        item = table[name]
        first, *numbers = NAMED[key]
        _set(item, first, area.get(first))
        for field in numbers:
            _set(item, field, area[field])
        if key == "objects":
            _set(item, HEADING, area.get(HEADING) or None)
        _set_comment(item, area.get("comment"))
    if not table:
        del doc[key]


def _patch_barriers(doc: TOMLDocument, key: str, items: list[dict[str, Any]]) -> None:
    """Write one array of tables; an entry's `was` is its index in the file."""
    least = BARRIERS[key]
    for item in items:
        if len(item.get("points") or []) < least:
            raise SiteTomlError(f"each of {key} needs at least {least} points")
    table = doc.get(key)
    if not isinstance(table, AoT):
        if not items:
            return
        table = tomlkit.aot()
        if not tomlkit.dumps(doc).endswith("\n\n"):
            doc.add(tomlkit.nl())
        doc[key] = table
    kept = sorted({item["was"] for item in items if item.get("was") is not None})
    if any(was >= len(table) for was in kept):
        raise SiteTomlError(f"{key} changed in the file since the page loaded it")
    for index in sorted(set(range(len(table))) - set(kept), reverse=True):
        del table[index]
    position = {was: k for k, was in enumerate(kept)}
    for item in items:
        points = [[int(x), int(y)] for x, y in item["points"]]
        if item.get("was") is None:
            entry = tomlkit.table()
            if item.get("name"):
                entry["name"] = item["name"]
            entry["points"] = points
            _set_comment(entry, item.get("comment"))
            table.append(entry)
            continue
        entry = table[position[item["was"]]]
        _set(entry, "name", item.get("name") or None)
        if [[int(x), int(y)] for x, y in entry["points"]] != points:
            entry["points"] = points
        _set_comment(entry, item.get("comment"))
    if not table:
        del doc[key]


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
    if "objects" in model:
        _check_names(model["objects"] or [], "object")
        _patch_named(doc, "objects", model["objects"] or [])
    for key in BARRIERS:
        if key in model:
            _patch_barriers(doc, key, model[key] or [])
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
