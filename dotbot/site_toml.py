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
from tomlkit.items import AoT, Comment, InlineTable, Table, Whitespace
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
    if key not in doc:
        return None
    table = doc[key]
    if not isinstance(table, Table):
        raise SiteTomlError(
            f"the site editor edits {key} written as one run of [{key}.<name>] "
            f"tables, or as one [{key}] table; this file writes them otherwise "
            "(split by another table, as dotted keys or inline), so edit it by "
            "hand or gather them first"
        )
    return table


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


def _barriers_table(doc: TOMLDocument, key: str) -> AoT | None:
    if key not in doc:
        return None
    items = doc[key]
    if not isinstance(items, AoT):
        raise SiteTomlError(
            f"the site editor edits {key} written as [[{key}]] tables; this file "
            "writes them otherwise (inline), so edit it by hand or rewrite them "
            "that way first"
        )
    return items


def _barriers_model(doc: TOMLDocument, key: str) -> list[dict[str, Any]]:
    items = _barriers_table(doc, key)
    if items is None:
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


def _clean_comment(comment: str | None) -> str | None:
    if comment is not None and ("\n" in comment or "\r" in comment):
        raise SiteTomlError("a comment is one line")
    return (comment or "").strip() or None


def _set_comment(item: Any, comment: str | None) -> None:
    comment = _clean_comment(comment)
    if _comment(item) == comment:
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


def _split_trailing(table: Table) -> str:
    """Take the comments and blank lines ending `table`, which head whatever
    follows it in the file, out of it; return them as text."""
    body = table.value.body
    end = len(body)
    while end and body[end - 1][0] is None:
        if not isinstance(body[end - 1][1], (Comment, Whitespace)):
            break
        end -= 1
    text = "".join(item.as_string() for _, item in body[end:])
    del body[end:]
    return text


def _end_with(table: Table, text: str) -> None:
    if text:
        table.value.body.append((None, Whitespace(text)))


def _set_heading(doc: TOMLDocument, key: str, text: str) -> None:
    """Make `text` the comments and blank lines just above the top-level `key`."""
    body = doc.body
    index = next(i for i, (k, _) in enumerate(body) if k is not None and k == key)
    start = index
    while start and body[start - 1][0] is None:
        start -= 1
    if start < index:
        body[start] = (None, Whitespace(text))
        for i in range(start + 1, index):
            body[i] = (None, Whitespace(""))
        return
    before = body[index - 1][1] if index else None
    if isinstance(before, AoT) and before.body:
        before = before.body[-1]
    if isinstance(before, Table):
        _split_trailing(before)
        _end_with(before, text)


def _delete_table(doc: TOMLDocument, parent: str, table: Table, name: str) -> None:
    """Delete `table[name]`, keeping the comments that head the next table."""
    names = list(table)
    index = names.index(name)
    item = table[name]
    if isinstance(item, Table):
        tail = _split_trailing(item)
        previous = table[names[index - 1]] if index else None
        if isinstance(previous, Table):
            _split_trailing(previous)
            _end_with(previous, tail)
        elif index == 0:
            _set_heading(doc, parent, tail)
    del table[name]


def _rename(table: Table, was: str, name: str) -> None:
    # tomlkit has no public rename; this keeps the area's place, comment and
    # layout, the header written in the plain form
    item = table[was]
    body = item.value.body if isinstance(item, Table) else None
    length = len(body) if body is not None else 0
    table.value._replace(was, name, item)
    if isinstance(item, Table):
        if len(body) == length + 1 and body[-1][1].as_string() == "\n":
            body.pop()
        item.display_name = None
        item.name = name


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
        _delete_table(doc, key, table, name)
    for was in renames:
        if was not in table:
            raise SiteTomlError(f"{key} entry {was!r} is not in the file")
    # A swap or a chain goes through names no entry has, so it never meets itself
    clash = any(name in table for name in renames.values())
    passing = {
        was: f"\0rename-{i}" if clash else name
        for i, (was, name) in enumerate(renames.items())
    }
    try:
        for was, through in passing.items():
            _rename(table, was, through)
        for was, through in passing.items():
            if through != renames[was]:
                _rename(table, through, renames[was])
    except (KeyError, ValueError) as exc:
        raise SiteTomlError(f"could not rename the {key} in this file: {exc}") from exc
    for area in areas:
        name = area["name"]
        if name not in table:
            last = table[list(table)[-1]] if table else None
            tail = _split_trailing(last) if isinstance(last, Table) else ""
            table[name] = _new_entry(key, inline, area)
            if isinstance(table[name], Table):
                _end_with(table[name], tail)
            elif isinstance(last, Table):
                _end_with(last, tail)
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


def _normal(model: dict[str, Any]) -> dict[str, Any]:
    """The parts of a model a written file must give back."""
    extent = model.get("extent_mm")
    return {
        "anchor": model.get("anchor") or None,
        "extent_mm": [int(v) for v in extent] if extent is not None else None,
        "areas": sorted(
            (
                area["name"],
                *(int(area[key]) for key in AREA_KEYS),
                area.get("role"),
                (area.get("comment") or "").strip() or None,
            )
            for area in model.get("areas") or []
        ),
        **{
            key: sorted(
                repr(
                    (
                        item.get("name") or None,
                        [[int(x), int(y)] for x, y in item.get("points") or []],
                        (item.get("comment") or "").strip() or None,
                    )
                )
                for item in model.get(key) or []
            )
            for key in BARRIERS
            if key in model
        },
        **(
            {
                "objects": sorted(
                    (
                        item["name"],
                        item.get("kind"),
                        int(item["x"]),
                        int(item["y"]),
                        float(item.get(HEADING) or 0.0),
                        (item.get("comment") or "").strip() or None,
                    )
                    for item in model.get("objects") or []
                )
            }
            if "objects" in model
            else {}
        ),
    }


def _patch_barriers(doc: TOMLDocument, key: str, items: list[dict[str, Any]]) -> None:
    """Write one array of tables; an entry's `was` is its index in the file."""
    least = BARRIERS[key]
    for item in items:
        if len(item.get("points") or []) < least:
            raise SiteTomlError(f"each of {key} needs at least {least} points")
    table = _barriers_table(doc, key)
    if table is None:
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
        # The comments ending an entry head whatever follows it
        tail = _split_trailing(table[index])
        if index:
            _split_trailing(table[index - 1])
            _end_with(table[index - 1], tail)
        else:
            _set_heading(doc, key, tail)
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
            tail = ""
            if len(table):
                tail = _split_trailing(table[-1])
                _end_with(table[-1], "\n")
            table.append(entry)
            _end_with(entry, tail)
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


def parse(text: str) -> TOMLDocument:
    try:
        return tomlkit.parse(text)
    except tomlkit.exceptions.ParseError as exc:
        raise SiteTomlError(f"not valid TOML: {exc}") from exc


def patched_text(text: str, model: dict[str, Any]) -> str:
    """`text` with `model` written into it, validated, and read back as
    `model`; SiteTomlError when the patch cannot be made faithfully."""
    result = tomlkit.dumps(patch(parse(text), model))
    validate(result)
    want = _normal(model)
    got = _normal(site_model(parse(result)))
    if {key: got[key] for key in want} != want:
        raise SiteTomlError(
            "the edit could not be written into site.toml as it is laid out; "
            "edit the file by hand"
        )
    return result
