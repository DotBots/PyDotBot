# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's server: one site pack's `site.toml` over JSON, and the
page that draws it.

It runs on its own, with no controller, broker or robot. Every save is
checked against the revision the page loaded, so an edit made to the file
meanwhile is never overwritten.
"""

from __future__ import annotations

import ipaddress
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotbot import site_toml
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


class SiteModel(BaseModel):
    anchor: str | None = None
    extent_mm: tuple[int, int] | None = None
    areas: list[AreaModel] = Field(default_factory=list)


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


def _is_loopback(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _refusal(scope) -> str | None:
    """Why a request may not reach the editor, or None when it may.

    Only a client on this machine, addressing it by a loopback name, from the
    editor's own page or from no page at all, is let through."""
    client = scope.get("client")
    if client is None or not _is_loopback(client[0]):
        return "the site editor answers this machine only"
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    host = headers.get("host", "")
    if urlsplit(f"//{host}").hostname not in ("127.0.0.1", "localhost", "::1"):
        return "the site editor answers 127.0.0.1 and localhost only"
    if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return "the site editor answers its own page only"
    origin = headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != host:
        return "the site editor answers its own page only"
    return None


class LocalOnly:
    """ASGI middleware refusing, with a 403, any request `_refusal` names."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        reason = _refusal(scope) if scope["type"] == "http" else None
        if reason is not None:
            await PlainTextResponse(reason, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` beside `path` and rename it over, keeping its mode; a
    symlink's target is the file written."""
    path = path.resolve()
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
    app.add_middleware(LocalOnly)

    saving = threading.Lock()

    def read() -> tuple[bytes, str]:
        try:
            data = state.path.read_bytes()
        except OSError as exc:
            raise HTTPException(500, f"could not read {state.path}: {exc}") from exc
        try:
            return data, data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, f"{state.path} is not UTF-8: {exc}") from exc

    def body(data: bytes, text: str) -> dict:
        try:
            site = site_toml.site_model(site_toml.parse(text))
        except site_toml.SiteTomlError as exc:
            raise HTTPException(422, f"{state.path}: {exc}") from exc
        return {
            "name": state.name,
            "path": str(state.path),
            "revision": site_toml.revision(data),
            "site": site,
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
        with saving:
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

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(page_dir / EDITOR_PAGE)

    if page_dir.is_dir():
        app.mount("/", StaticFiles(directory=page_dir), name="page")
    return app
