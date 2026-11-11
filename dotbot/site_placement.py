# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's calibration routes: list the LH2 calibrations, draw one
over the site, and save it moved onto the site, or with its stations'
rectangles changed, as a new calibration.

The file a calibration is loaded from is never written; a new one is saved
under a new id in the site's calibration folder.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dotbot import site_coverage, site_history, site_library, site_toml
from dotbot.calibration import lighthouse2, site_frame, site_turn, station_rule
from dotbot.calibration.placement import (
    FREE_SOLVERS,
    PlacementRefused,
    Rigid2D,
    overlay,
    place_calibration,
    save_new,
    save_placed,
    site_tags,
    solved_in_own_frame,
    spin_centres,
)
from dotbot.calibration.station_boxes import (
    BoxesRefused,
    coverage_warnings,
    frame_refusal,
    push_line,
    reboxed,
)
from dotbot.config import SiteSection
from dotbot.site import PACK_CALIBRATIONS, Site, site_from_table


class PlaceRequest(BaseModel):
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    theta_deg: float = 0.0
    # Move a corner-collected calibration anyway: the anchor itself moved
    reanchor: bool = False


class FrameRequest(BaseModel):
    # The calibration re-expressed in the new frame: the served one
    calibration: str
    theta_deg: float = 0.0
    pivot: tuple[float, float] = (0.0, 0.0)
    # Where zero moves, in the old frame's mm
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    # The note on where zero is now; None keeps the old note
    note: str | None = None
    revision: str
    # Serve the re-expressed calibration on the controller after writing
    serve: bool = True
    dry_run: bool = False


class LibraryRequest(BaseModel):
    # A new tag for the file, outside its id
    tag: str | None = None
    # True moves it into archived/, False moves it back
    archived: bool | None = None
    # Go ahead although a config or a snapshot names the file; a served
    # file is still not archived
    force: bool = False


class BoxesRequest(BaseModel):
    # Station index to its new `[x_min, y_min, x_max, y_max]`, frame mm
    stations: dict[int, tuple[int, int, int, int]]
    # None takes the source's tag suffixed `-boxes`; "" saves it untagged
    tag: str | None = None
    # The site.toml revision the page checked the rectangles against
    revision: str | None = None


def _folders(pack: Path) -> list[tuple[Path, str]]:
    return [(pack / PACK_CALIBRATIONS, ""), (lighthouse2.calibration_root(), "*/")]


def _files(pack: Path) -> list[Path]:
    seen, out = set(), []
    for folder, prefix in _folders(pack):
        for path in sorted(folder.glob(prefix + lighthouse2.CALIBRATION_TOML_GLOB)):
            if path.resolve() not in seen:
                seen.add(path.resolve())
                out.append(path)
    return out


def _metadata(path: Path) -> dict | None:
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
    write_site: Callable[[str, str], None] | None = None,
    served_id: Callable[[], str | None] | None = None,
    serve: Callable[[str, bool], dict] | None = None,
    context: Callable[[], dict] | None = None,
) -> APIRouter:
    """Routes for the site `name` in `pack`; `site_text` reads its site.toml,
    `write_site(revision, text)` writes it over that revision, `served_id`
    names the calibration a controller serves, `context` says what the
    controller's configs name (`next_start`, `started_with`, `configured`)."""
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
        listed = [m for m in map(_metadata, _files(pack)) if m and m["id"]]
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

    @router.post("/api/frame")
    def frame_change(request: FrameRequest):
        """Turn the site's frame or move its zero, in order: the calibration
        re-expressed as a new file, site.toml with the new frame id, then
        that file served. A refusal names the largest legal shift."""
        source = resolve(request.calibration)
        text = site_text()
        if site_toml.revision(text.encode("utf-8")) != request.revision:
            raise HTTPException(
                409, "site.toml changed on disk since the page loaded it"
            )
        site = current_site()
        shift = (request.dx_mm, request.dy_mm)
        frame = site_frame.new_frame_id(
            site.frame_id, request.theta_deg, request.pivot, shift
        )
        note = site.anchor if request.note is None else request.note.strip()
        try:
            planned = site_frame.moved(
                source,
                site,
                request.theta_deg,
                request.pivot,
                shift,
                note,
                frame,
                taken_tags=site_tags(site.name, _files(pack)),
            )
        except site_turn.TurnRefused as exc:
            offer = site_frame.largest_shift(
                source, site, request.theta_deg, request.pivot, shift
            )
            raise HTTPException(
                422,
                {
                    "message": str(exc),
                    "offer": (
                        None
                        if offer is None
                        else {"dx_mm": offer[0], "dy_mm": offer[1]}
                    ),
                },
            ) from exc
        summary = {
            "frame": frame,
            "from_frame": site.frame_id,
            "calibration": {"id": planned.id, "id8": planned.id8, "tag": planned.tag},
            "source": source.id8,
            "warnings": site_turn.outside_warnings(planned, site)
            + site_turn.widened_note(request.theta_deg),
            "push": push_line(planned),
        }
        if request.dry_run:
            return {**summary, "steps": []}
        if write_site is None:
            raise HTTPException(405, "this editor cannot write site.toml")
        steps = []
        saved, path = save_new(planned)
        steps.append(
            {
                "step": "calibration",
                "status": "written",
                "detail": str(path),
                "id": saved.id,
            }
        )
        try:
            model = site_toml.site_model(site_toml.parse(text))
            model["frame"] = frame
            model["anchor"] = note or None
            for key in ("areas", "objects"):
                for entry in model.get(key) or []:
                    entry["was"] = entry["name"]
            for key in ("walls", "obstacles"):
                for i, entry in enumerate(model.get(key) or []):
                    entry["was"] = i
            write_site(request.revision, site_toml.patched_text(text, model))
        except (site_toml.SiteTomlError, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            steps.append(
                {"step": "site.toml", "status": "refused", "detail": str(detail)}
            )
            return {**summary, "steps": steps, "ok": False}
        steps.append(
            {"step": "site.toml", "status": "written", "detail": f"frame {frame}"}
        )
        if request.serve and serve is not None:
            try:
                serve(saved.id, False)
                steps.append(
                    {
                        "step": "serve",
                        "status": "written",
                        "detail": f"serving {saved.id8}, this run only",
                    }
                )
            except (ValueError, OSError) as exc:
                steps.append({"step": "serve", "status": "refused", "detail": str(exc)})
        return {
            **summary,
            "steps": steps,
            "ok": all(s["status"] != "refused" for s in steps),
        }

    def tag_holder(tag: str, own_id: str) -> str | None:
        """The id8 of another file of this site carrying `tag`."""
        for m in map(_metadata, _files(pack)):
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
    def coverage(spec: str, boxes: str | None = None, robots: int = 4):
        """Who gives the fix and the predicted error for `boxes` (JSON,
        station index to [x_min, y_min, x_max, y_max]), the file's own when
        absent."""
        cal = resolve(spec)
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
                    422, "each box is [x0, y0, x1, y1] with x1 > x0, y1 > y0"
                )
        return site_coverage.coverage(
            cal, current_site(), rects, max(0, min(robots, 8))
        )

    @router.post("/api/calibrations/{spec}/place")
    def place(spec: str, request: PlaceRequest):
        source = resolve(spec)
        site = current_site()
        taken = site_tags(site.name, _files(pack))
        move = Rigid2D(request.dx_mm, request.dy_mm, request.theta_deg)
        try:
            placed = place_calibration(
                source, site, move, reanchor=request.reanchor, taken_tags=taken
            )
            placed, path = save_placed(source, placed)
        except PlacementRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        warnings = []
        if site.extent_mm is not None:
            width, height = site.extent_mm
            outside = [
                c["name"]
                for circles in spin_centres(placed).values()
                for c in circles
                if c["x"] > width or c["y"] > height
            ]
            if outside:
                warnings.append(
                    f"{len(outside)} circle(s) land outside the site's extent "
                    f"({', '.join(sorted(set(outside)))}), where robots drop "
                    "their positions"
                )
        if not solved_in_own_frame(source):
            warnings.append(
                f"{source.id8} was collected at points of the room and has been "
                "re-anchored; check the anchor in site.toml says where zero is now"
            )
        changed = " --site-changed" if source.site.name != site.name else ""
        return {
            **overlay(placed),
            "path": str(path),
            "source": source.id8,
            "push": (
                f"dotbot swarm calibrate-lh2 push {placed.id8} --site {site.name}"
                f"{changed}"
            ),
            "warnings": warnings,
        }

    @router.post("/api/calibrations/{spec}/boxes")
    def boxes(spec: str, request: BoxesRequest, dry_run: bool = False):
        return save_boxes(spec, request, dry_run)

    def save_boxes(spec: str, request: BoxesRequest, dry_run: bool = False) -> dict:
        """Save `spec` with the requested boxes, or with `dry_run` say what
        that would write; HTTPException when refused."""
        source = resolve(spec)
        text = site_text()
        if (
            request.revision is not None
            and site_toml.revision(text.encode("utf-8")) != request.revision
        ):
            raise HTTPException(
                409, "site.toml changed on disk since the page loaded it"
            )
        site = current_site()
        try:
            boxed = reboxed(
                source,
                site,
                request.stations,
                tag=request.tag,
                taken_tags=site_tags(site.name, _files(pack)),
            )
            if dry_run:
                same = next(
                    (
                        m
                        for m in map(_metadata, _files(pack))
                        if m and m["id"] == boxed.id
                    ),
                    None,
                )
                return {
                    "id": boxed.id,
                    "id8": boxed.id8,
                    "source": source.id8,
                    "written": False,
                    "existing": (
                        None
                        if same is None
                        else {k: same[k] for k in ("id", "id8", "tag", "path")}
                    ),
                    "reading": station_rule.reading(
                        {st.index: st.valid_mm for st in boxed.stations}
                    ),
                }
            boxed, path = save_new(boxed)
        except BoxesRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            **overlay(boxed),
            "path": str(path),
            "source": source.id8,
            "push": push_line(boxed),
            "warnings": coverage_warnings(boxed),
        }

    router.save_boxes = save_boxes  # type: ignore[attr-defined]
    router.resolve = resolve  # type: ignore[attr-defined]
    router.current_site = current_site  # type: ignore[attr-defined]

    return router
