# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's calibration routes: list the LH2 calibrations, draw one
over the site, predict its coverage, and rename or archive a file.

New calibrations are written by the editor's one Save (`site_draft`), never
over the file one is loaded from.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dotbot import site_coverage, site_history, site_library
from dotbot.calibration import lighthouse2, site_frame, site_turn
from dotbot.calibration.placement import (
    FREE_SOLVERS,
    overlay,
)
from dotbot.calibration.station_boxes import (
    frame_refusal,
)
from dotbot.config import SiteSection
from dotbot.site import PACK_CALIBRATIONS, Site, site_from_table


class LibraryRequest(BaseModel):
    # A new tag for the file, outside its id
    tag: str | None = None
    # True moves it into archived/, False moves it back
    archived: bool | None = None
    # Go ahead although a config or a snapshot names the file; a served
    # file is still not archived
    force: bool = False


def _folders(pack: Path) -> list[tuple[Path, str]]:
    return [(pack / PACK_CALIBRATIONS, ""), (lighthouse2.calibration_root(), "*/")]


def files(pack: Path) -> list[Path]:
    seen, out = set(), []
    for folder, prefix in _folders(pack):
        for path in sorted(folder.glob(prefix + lighthouse2.CALIBRATION_TOML_GLOB)):
            if path.resolve() not in seen:
                seen.add(path.resolve())
                out.append(path)
    return out


def file_metadata(path: Path) -> dict | None:
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    meta = data.get("metadata", {})
    stations = data.get("station", [])
    return {
        "id": meta.get("id", ""),
        "id8": str(meta.get("id", ""))[:8],
        "created_at": meta.get("created_at", ""),
        "free": bool(stations)
        and all(st.get("solved_from") in FREE_SOLVERS for st in stations),
        "stations": sorted(int(st.get("index", 0)) for st in stations),
        "tag": meta.get("tag", ""),
        "site": data.get("site", {}).get("name", ""),
        "anchor": data.get("site", {}).get("anchor", ""),
        "frame": data.get("site", {}).get("frame"),
        "path": str(path),
    }


def create_router(
    name: str,
    pack: Path,
    site_text: Callable[[], str],
    served_id: Callable[[], str | None] | None = None,
    context: Callable[[], dict] | None = None,
) -> APIRouter:
    """Routes for the site `name` in `pack`; `site_text` reads its site.toml,
    `served_id` names the calibration a controller serves, `context` says
    what the controller's configs name (`next_start`, `started_with`,
    `configured`)."""
    router = APIRouter()

    def resolve(spec: str) -> lighthouse2.Calibration:
        try:
            path = lighthouse2.resolve_calibration_spec(
                spec,
                _folders(pack),
                glob=lighthouse2.CALIBRATION_TOML_GLOB,
                metadata=lighthouse2._file_metadata,
                what="calibration",
                created_key="created_at",
            )
            return lighthouse2.read_calibration_file(path)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def current_site() -> Site:
        try:
            table = SiteSection.model_validate(tomllib.loads(site_text()))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(409, f"site.toml does not read: {exc}") from exc
        return site_from_table(name, table, pack)

    @router.get("/api/calibrations")
    def calibrations(scope: str | None = None):
        if scope == "site":
            folders = [pack / PACK_CALIBRATIONS, lighthouse2.calibration_root() / name]
            served = served_id() if served_id is not None else None
            return site_library.library(folders, current_site(), served)
        if scope is not None:
            raise HTTPException(
                422, f"unknown scope {scope!r}; the one known is 'site'"
            )
        try:
            site = current_site()
        except HTTPException:
            site = None
        listed = [m for m in map(file_metadata, files(pack)) if m and m["id"]]
        for m in listed:
            file_site = Site(
                name=m["site"], anchor=m.pop("anchor"), frame=m.pop("frame")
            )
            m["in_frame"] = site is not None and frame_refusal(file_site, site) is None
        return listed

    @router.get("/api/calibrations/{spec}")
    def calibration(spec: str):
        cal = resolve(spec)
        try:
            refusal = frame_refusal(cal.site, current_site())
        except HTTPException as exc:
            refusal = exc.detail
        return {**overlay(cal), "path": str(cal.path), "frame_refusal": refusal}

    def tag_holder(tag: str, own_id: str) -> str | None:
        """The id8 of another file of this site carrying `tag`."""
        for m in map(file_metadata, files(pack)):
            if (
                m
                and m["site"] == name
                and m["id"] != own_id
                and str(m["tag"]).lower() == tag.lower()
            ):
                return m["id8"]
        return None

    def named_by(cal: lighthouse2.Calibration, by_tag_only: bool) -> list[str]:
        """What names `cal`: the controller's configs by id, id prefix or
        tag (by tag alone with `by_tag_only`), and the site's snapshots."""
        found = context() if context is not None else {}
        out = []
        for key in ("next_start", "started_with", "configured"):
            entry = found.get(key) or {}
            spec = str(entry.get("spec") or "").strip().lower()
            if not spec:
                continue
            by_tag = bool(cal.tag) and spec == cal.tag.lower()
            by_id = cal.id.lower().startswith(spec)
            if by_tag or (by_id and not by_tag_only):
                out.append(
                    f"named for the next start: {entry['spec']} in "
                    f"{entry.get('source') or 'unknown'}"
                )
        if not by_tag_only:
            for point in site_history.points(name):
                if point.get("served") == cal.id:
                    out.append(f"kept in snapshot {point['name']}")
        return out

    @router.patch("/api/calibrations/{spec}")
    def change(spec: str, request: LibraryRequest):
        """Rename a file's tag or archive it; only files under
        ~/.dotbot/calibrations, never a pack's tracked ones. A file a
        config or a snapshot names is refused with what names it, unless
        forced; a served file is never archived."""
        cal = resolve(spec)
        path = Path(cal.path)
        home = lighthouse2.calibration_root()
        if request.tag is not None:
            tag = request.tag.strip()
            if not tag:
                raise HTTPException(
                    422, "a tag cannot be empty: archive the file to hide it instead"
                )
            holder = tag_holder(tag, cal.id)
            if holder is not None:
                raise HTTPException(422, f'tag "{tag}" is already {holder}\'s')
            dependents = named_by(cal, by_tag_only=True)
            if dependents and not request.force:
                raise HTTPException(
                    409,
                    {
                        "message": f"{cal.id8} is {'; '.join(dependents)}",
                        "dependents": dependents,
                    },
                )
        if request.archived is True:
            served = served_id() if served_id is not None else None
            dependents = named_by(cal, by_tag_only=False)
            if served == cal.id:
                dependents.insert(0, "in use by this controller")
                raise HTTPException(
                    409,
                    {
                        "message": (
                            f"{cal.id8} is in use by this controller: serve "
                            "another calibration before archiving it"
                        ),
                        "dependents": dependents,
                    },
                )
            if dependents and not request.force:
                raise HTTPException(
                    409,
                    {
                        "message": f"{cal.id8} is {'; '.join(dependents)}",
                        "dependents": dependents,
                    },
                )
        try:
            if request.tag is not None:
                path = site_library.rename_tag(path, request.tag, home)
            if request.archived is True:
                path = site_library.archive(path, home)
            elif request.archived is False:
                path = site_library.restore(path, home)
        except site_library.LibraryRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        cal = lighthouse2.read_calibration_file(path)
        return {"id": cal.id, "id8": cal.id8, "tag": cal.tag, "path": str(path)}

    @router.get("/api/calibrations/{spec}/coverage")
    def coverage(
        spec: str, boxes: str | None = None, robots: int = 4, frame: str | None = None
    ):
        """Who gives the fix and the predicted error for `boxes` (JSON,
        station index to [x_min, y_min, x_max, y_max]), the file's own when
        absent; with `frame` (a drafted move of the origin, JSON) for the
        file re-expressed in the moved frame, `boxes` in its numbers."""
        cal = resolve(spec)
        site = current_site()
        if frame:
            from dotbot import site_draft

            try:
                move = site_draft.Move.model_validate_json(frame)
            except ValueError as exc:
                raise HTTPException(422, f"frame does not read: {exc}") from exc
            if move.moves:
                try:
                    cal = site_frame.moved(
                        cal,
                        site,
                        move.theta_deg,
                        move.pivot,
                        move.shift,
                        site.anchor,
                        site_frame.new_frame_id(
                            site.frame_id, move.theta_deg, move.pivot, move.shift
                        ),
                    )
                except site_turn.TurnRefused as exc:
                    raise HTTPException(422, str(exc)) from exc
        rects = None
        if boxes:
            try:
                rects = {
                    int(k): [int(v) for v in r] for k, r in json.loads(boxes).items()
                }
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(
                    422, "boxes is JSON: station index to [x0, y0, x1, y1]"
                ) from exc
            if any(len(r) != 4 or r[2] <= r[0] or r[3] <= r[1] for r in rects.values()):
                raise HTTPException(
                    422, "each coverage is [x0, y0, x1, y1] with x1 > x0, y1 > y0"
                )
        out = site_coverage.coverage(cal, site, rects, max(0, min(robots, 8)))
        return {**out, "id": resolve(spec).id}

    router.resolve = resolve  # type: ignore[attr-defined]
    router.current_site = current_site  # type: ignore[attr-defined]

    return router
