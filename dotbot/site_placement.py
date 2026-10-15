# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's calibration routes: list the LH2 calibrations, draw one
over the site, and save it moved onto the site, or with its stations'
rectangles changed, as a new calibration.

The file a calibration is loaded from is never written; a new one is saved
under a new id in the site's calibration folder.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dotbot import site_toml
from dotbot.calibration import lighthouse2
from dotbot.calibration.placement import (
    FREE_SOLVERS,
    PlacementRefused,
    Rigid2D,
    is_free_mode,
    overlay,
    place_calibration,
    save_placed,
    site_tags,
    save_new,
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
        "path": str(path),
    }


def create_router(name: str, pack: Path, site_text: Callable[[], str]) -> APIRouter:
    """Routes for the site `name` in `pack`; `site_text` reads its site.toml."""
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
    def calibrations():
        try:
            site = current_site()
        except HTTPException:
            site = None
        listed = [m for m in map(_metadata, _files(pack)) if m and m["id"]]
        for m in listed:
            file_site = Site(name=m["site"], anchor=m.pop("anchor"))
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
        if not is_free_mode(source):
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
    def boxes(spec: str, request: BoxesRequest):
        source = resolve(spec)
        text = site_text()
        if (
            request.revision is not None
            and site_toml.revision(text.encode("utf-8")) != request.revision
        ):
            raise HTTPException(409, "site.toml changed on disk since the page loaded it")
        site = current_site()
        try:
            boxed = reboxed(
                source,
                site,
                request.stations,
                tag=request.tag,
                taken_tags=site_tags(site.name, _files(pack)),
            )
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

    return router
