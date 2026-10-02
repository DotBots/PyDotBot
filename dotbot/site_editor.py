# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's server: one site pack's `site.toml` over JSON, and the
page that draws it.

It runs on its own, with no controller, broker or robot. Every save is
checked against the revision the page loaded, so an edit made to the file
meanwhile is never overwritten.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

import tomlkit
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from dotbot import site_backdrops, site_placement, site_toml
from dotbot.site import PACK_CALIBRATIONS
from dotbot.site_packs import PACK_FILE

EDITOR_DIR = Path(__file__).parent / "console-web" / "dist"
EDITOR_PAGE = "site-editor.html"


class AreaModel(BaseModel):
    name: str
    x: int
    y: int
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    role: Literal["field", "staging", "corner"] | None = None
    comment: str | None = None
    # The area's name in the file when the page loaded it; None for a new one
    was: str | None = None


class BarrierModel(BaseModel):
    name: str | None = None
    points: list[tuple[int, int]]
    comment: str | None = None
    # The entry's index in the file when the page loaded it; None for a new one
    was: int | None = None


class SiteModel(BaseModel):
    anchor: str | None = None
    extent_mm: tuple[int, int] | None = None
    areas: list[AreaModel] = Field(default_factory=list)
    walls: list[BarrierModel] = Field(default_factory=list)
    obstacles: list[BarrierModel] = Field(default_factory=list)


class SaveRequest(BaseModel):
    revision: str
    site: SiteModel


@dataclass
class EditorState:
    """The pack being edited and where its calibrations may be."""

    name: str
    pack: Path
    calibration_dirs: list[Path] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.pack / PACK_FILE

    def calibrations(self) -> list[dict]:
        folders = [self.pack / PACK_CALIBRATIONS, *self.calibration_dirs]
        return [
            {
                "folder": str(folder),
                "count": len(list(folder.glob("*.toml"))) if folder.is_dir() else 0,
            }
            for folder in folders
        ]


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` beside `path` and rename it over, keeping its mode."""
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _model_dict(model: SiteModel) -> dict:
    data = model.model_dump()
    data["extent_mm"] = list(model.extent_mm) if model.extent_mm else None
    return data


def create_app(
    state: EditorState,
    page_dir: Path = EDITOR_DIR,
    on_done: Callable[[], None] | None = None,
) -> FastAPI:
    """The editor's app for `state`; `on_done` runs when the page says Done."""
    app = FastAPI(title="DotBot site editor", docs_url=None, redoc_url=None)
    # A page from another site that rebinds its name to 127.0.0.1 is refused.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    def read() -> tuple[bytes, str]:
        try:
            data = state.path.read_bytes()
        except OSError as exc:
            raise HTTPException(500, f"could not read {state.path}: {exc}") from exc
        return data, data.decode("utf-8")

    def body(data: bytes, text: str) -> dict:
        return {
            "name": state.name,
            "path": str(state.path),
            "revision": site_toml.revision(data),
            "site": site_toml.site_model(tomlkit.parse(text)),
            "calibrations": state.calibrations(),
        }

    def patched(text: str, model: SiteModel) -> str:
        try:
            return site_toml.patched_text(text, _model_dict(model))
        except site_toml.SiteTomlError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/site")
    def get_site():
        return body(*read())

    @app.post("/api/preview")
    def preview(model: SiteModel):
        _, text = read()
        result = patched(text, model)
        return {"text": result, "changed": result != text}

    @app.put("/api/site")
    def save(request: SaveRequest):
        data, text = read()
        if site_toml.revision(data) != request.revision:
            raise HTTPException(
                409, f"{state.path} changed on disk since the page loaded it"
            )
        result = patched(text, request.site)
        written = result != text
        if written:
            _write_atomic(state.path, result)
            data = result.encode("utf-8")
            text = result
        return {**body(data, text), "written": written}

    @app.post("/api/done")
    def done():
        if on_done is not None:
            on_done()
        return {"ok": True}

    app.include_router(
        site_placement.create_router(state.name, state.pack, lambda: read()[1])
    )
    app.include_router(
        site_backdrops.create_router(
            state.name,
            lambda: [state.pack / PACK_CALIBRATIONS, *state.calibration_dirs],
            lambda: read()[1],
        )
    )

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(page_dir / EDITOR_PAGE)

    if page_dir.is_dir():
        app.mount("/", StaticFiles(directory=page_dir), name="page")
    return app
