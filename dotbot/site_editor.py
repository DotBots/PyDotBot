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
import shlex
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotbot import site_backdrops, site_history, site_placement, site_toml
from dotbot.config import ObjectKind
from dotbot.same_origin import cross_site_refusal
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


class ObjectModel(BaseModel):
    name: str
    kind: ObjectKind
    x: int
    y: int
    heading_deg: float = 0.0
    comment: str | None = None
    # The object's name in the file when the page loaded it; None for a new one
    was: str | None = None


class SiteModel(BaseModel):
    anchor: str | None = None
    # None leaves the file's frame id as it is
    frame: str | None = None
    extent_mm: tuple[int, int] | None = None
    areas: list[AreaModel] = Field(default_factory=list)
    # None leaves the file's table as it is
    walls: list[BarrierModel] | None = None
    obstacles: list[BarrierModel] | None = None
    objects: list[ObjectModel] | None = None


class SaveRequest(BaseModel):
    revision: str
    site: SiteModel
    # site.toml as edited by hand on the page, patched instead of the file
    text: str | None = None


class PreviewRequest(BaseModel):
    site: SiteModel
    text: str | None = None


class ApplyRequest(BaseModel):
    """One Save: site.toml first, then a calibration's new boxes against the
    revision that write leaves."""

    revision: str
    site: SiteModel | None = None
    text: str | None = None
    # The calibration to save with new boxes, and the boxes
    boxes_of: str | None = None
    boxes: site_placement.BoxesRequest | None = None


class ServeRequest(BaseModel):
    # A calibration id, tag or path, resolved under the site
    spec: str
    # Also at the next start: written to the controller's config
    persist: bool = False


class CheckRequest(BaseModel):
    calibration: str
    mark_mm: tuple[float, float]
    measured_mm: tuple[float, float]
    robot: str
    predicted_mm: float | None = None
    note: str = ""


class PointRequest(BaseModel):
    name: str


class PointRestoreRequest(BaseModel):
    revision: str
    # Serve the calibration served when the point was kept
    serve: bool = True


class RestoreRequest(BaseModel):
    version: str
    revision: str


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
    if cross_site_refusal(headers) is not None:
        return "the site editor answers its own page only"
    return None


def _read_refusal(scope) -> str | None:
    """Why a read may not reach the editor: only another site's page is
    refused, so a console or a laptop on the network can view it."""
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    if cross_site_refusal(headers) is not None:
        return "the site editor answers its own page only"
    return None


def can_write(scope) -> bool:
    """Whether this request's client may write: this machine, by a loopback
    name, from the editor's page."""
    return _refusal(scope) is None


class LocalOnly:
    """ASGI middleware refusing, with a 403, a write from anywhere but this
    machine, and a read from another site's page."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        reason = None
        if scope["type"] == "http":
            read = scope.get("method", "GET") in ("GET", "HEAD")
            reason = _read_refusal(scope) if read else _refusal(scope)
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
    return {
        key: value
        for key, value in data.items()
        if value is not None or key in ("anchor", "extent_mm")
    }


def editor_command(path: Path) -> list[str]:
    """How to open `path` in the user's editor: DOTBOT_EDITOR when set, else
    the desktop's default for text files."""
    chosen = os.environ.get("DOTBOT_EDITOR")
    if chosen:
        return [*shlex.split(chosen), str(path)]
    if sys.platform == "darwin":
        return ["open", "-t", str(path)]
    if sys.platform.startswith("win"):
        return ["cmd", "/c", "start", "", str(path)]
    return ["xdg-open", str(path)]


def _shown_path(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home) :] if text.startswith(home + os.sep) else text


def create_app(
    state: EditorState,
    page_dir: Path | None = EDITOR_DIR,
    on_done: Callable[[], None] | None = None,
    on_saved: Callable[[], None] | None = None,
    context: Callable[[], dict] | None = None,
    serve: Callable[[str, bool], dict] | None = None,
) -> FastAPI:
    """The editor's app for `state`; `on_done` runs when the page says Done,
    `on_saved` after a save wrote the file, `context` says who opened it
    (`GET api/context`), `serve(spec, persist)` switches the calibration a
    controller serves. Without `page_dir` it serves the JSON routes only."""
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
        from dotbot.site import derived_frame_id

        return {
            "name": state.name,
            "path": str(state.path),
            "frame_id": site.get("frame") or derived_frame_id(state.name, site.get("anchor") or ""),
            "revision": site_toml.revision(data),
            "shown_path": _shown_path(state.path),
            "text": text,
            "site": site,
            "calibrations": state.calibrations(),
        }

    def patched(text: str, model: SiteModel) -> str:
        try:
            return site_toml.patched_text(text, _model_dict(model))
        except site_toml.SiteTomlError as exc:
            raise HTTPException(422, str(exc)) from exc

    def stamped(text: str, model: SiteModel) -> SiteModel:
        """`model` with the frame id written first when its note on zero
        changes and the file records none, so calibrations matched through
        the old note keep matching."""
        try:
            current = site_toml.site_model(site_toml.parse(text))
        except site_toml.SiteTomlError:
            return model
        if model.frame or current.get("frame") or (model.anchor or "") == (current.get("anchor") or ""):
            return model
        from dotbot.site import derived_frame_id

        return model.model_copy(
            update={"frame": derived_frame_id(state.name, current.get("anchor") or "")}
        )

    @app.get("/api/site")
    def get_site():
        return body(*read())

    def base_of(text: str, edited: str | None) -> str:
        if edited is None:
            return text
        try:
            site_toml.site_model(site_toml.parse(edited))
        except site_toml.SiteTomlError as exc:
            raise HTTPException(422, f"the edited site.toml does not read: {exc}") from exc
        return edited

    @app.post("/api/preview")
    def preview(request: PreviewRequest):
        _, text = read()
        base = base_of(text, request.text)
        result = patched(base, stamped(base, request.site))
        return {"text": result, "changed": result != text}

    @app.post("/api/parse")
    def parse(request: dict):
        """A hand-edited site.toml as the page's site model, or why it does not read."""
        text = request.get("text")
        if not isinstance(text, str):
            raise HTTPException(422, "send the file's text as {text}")
        try:
            return {"site": site_toml.site_model(site_toml.parse(text))}
        except site_toml.SiteTomlError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/revision")
    def get_revision():
        data, _ = read()
        return {"revision": site_toml.revision(data)}

    @app.post("/api/open")
    def open_in_editor():
        command = editor_command(state.path)
        try:
            subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise HTTPException(500, f"could not run {command[0]}: {exc}") from exc
        shown = (
            subprocess.list2cmdline(command)
            if sys.platform.startswith("win")
            else shlex.join(command)
        )
        return {"command": shown, "path": str(state.path)}

    def keep_and_write(old: bytes, text: str) -> None:
        site_history.snapshot(state.name, old)
        _write_atomic(state.path, text)
        if on_saved is not None:
            on_saved()

    def write_model(
        revision: str, model: SiteModel, edited: str | None = None
    ) -> tuple[bytes, str, bool]:
        with saving:
            data, text = read()
            if site_toml.revision(data) != revision:
                raise HTTPException(
                    409, f"{state.path} changed on disk since the page loaded it"
                )
            model = stamped(base_of(text, edited), model)
            result = patched(base_of(text, edited), model)
            if result == text:
                return data, text, False
            keep_and_write(data, result)
            return result.encode("utf-8"), result, True

    @app.put("/api/site")
    def save(request: SaveRequest):
        data, text, written = write_model(
            request.revision, request.site, request.text
        )
        return {**body(data, text), "written": written}

    @app.post("/api/apply")
    def apply(request: ApplyRequest):
        steps = []
        revision = request.revision
        if request.site is not None:
            data, text, written = write_model(revision, request.site, request.text)
            revision = site_toml.revision(data)
            steps.append(
                {
                    "step": "site.toml",
                    "status": "written" if written else "unchanged",
                    "detail": str(state.path),
                    "revision": revision,
                }
            )
        if request.boxes is not None and request.boxes_of:
            boxes = request.boxes.model_copy(update={"revision": revision})
            try:
                saved = placement.save_boxes(request.boxes_of, boxes)
                steps.append(
                    {
                        "step": "calibration",
                        "status": "written",
                        "detail": saved["path"],
                        "id": saved["id"],
                        "push": saved["push"],
                        "warnings": saved["warnings"],
                    }
                )
            except HTTPException as exc:
                steps.append(
                    {"step": "calibration", "status": "refused", "detail": exc.detail}
                )
        data, text = read()
        return {
            **body(data, text),
            "ok": all(s["status"] != "refused" for s in steps),
            "steps": steps,
        }

    @app.get("/api/history")
    def history():
        return site_history.versions(state.name)

    @app.post("/api/restore")
    def restore(request: RestoreRequest):
        try:
            kept = site_history.read_version(state.name, request.version)
        except KeyError as exc:
            raise HTTPException(404, f"no kept version {request.version}") from exc
        try:
            kept_text = kept.decode("utf-8")
            site_toml.site_model(site_toml.parse(kept_text))
        except (UnicodeDecodeError, site_toml.SiteTomlError) as exc:
            raise HTTPException(422, f"{request.version} does not read: {exc}") from exc
        with saving:
            data, text = read()
            if site_toml.revision(data) != request.revision:
                raise HTTPException(
                    409, f"{state.path} changed on disk since the page loaded it"
                )
            if kept_text != text:
                keep_and_write(data, kept_text)
        data, text = read()
        return {**body(data, text), "restored": request.version}

    def opened_by() -> dict:
        return context() if context is not None else {"mode": "standalone"}

    @app.get("/api/context")
    def get_context(request: Request):
        found = {"served": None, "next_start": None, "configured": None}
        return {
            **found,
            **opened_by(),
            "site": state.name,
            "path": str(state.path),
            "can_write": can_write(request.scope),
        }

    def served_calibration():
        found = opened_by()
        spec = (found.get("served") or found.get("configured") or {}).get("id")
        if not spec:
            return None
        try:
            return placement.resolve(spec)
        except HTTPException:
            return None

    @app.get("/api/checks")
    def get_checks():
        from dotbot.calibration import checks

        return {"checks": checks.read_checks(state.name), "path": str(checks.checks_path(state.name))}

    @app.post("/api/checks")
    def post_check(request: CheckRequest):
        from dotbot.calibration import checks

        return checks.append_check(
            state.name,
            request.calibration,
            request.mark_mm,
            request.measured_mm,
            request.robot,
            request.predicted_mm,
            request.note,
        )

    @app.get("/api/provenance")
    def get_provenance(request: Request):
        from dotbot.calibration import checks
        from dotbot.calibration.multi_station import error_map_from_calibration
        from dotbot.calibration.provenance import provenance_lines

        cal = served_calibration()
        if cal is None:
            raise HTTPException(404, "no calibration is served or configured, so there is nothing to record")
        try:
            error_map = error_map_from_calibration(cal)
        except (ValueError, ArithmeticError):
            error_map = None
        found = opened_by()
        served = found.get("served")
        by = None
        if served:
            how = served.get("source", "")
            by = f"{request.headers.get('host', 'this controller')}, {how}"
        lines = provenance_lines(
            cal,
            placement.current_site(),
            error_map,
            served=by,
            check=checks.last_check(state.name, cal.id),
        )
        return {"lines": lines, "text": "\n".join(lines)}

    @app.get("/api/points")
    def get_points():
        return site_history.points(state.name)

    @app.post("/api/points")
    def post_point(request: PointRequest):
        data, _ = read()
        served = (opened_by().get("served") or {}).get("id")
        return site_history.save_point(state.name, request.name, data, served)

    @app.post("/api/points/{point}/restore")
    def restore_point(point: str, request: PointRestoreRequest):
        try:
            kept, kept_bytes = site_history.read_point(state.name, point)
        except KeyError as exc:
            raise HTTPException(404, f"no restore point {point}") from exc
        kept_text = kept_bytes.decode("utf-8")
        with saving:
            data, text = read()
            if site_toml.revision(data) != request.revision:
                raise HTTPException(409, f"{state.path} changed on disk since the page loaded it")
            if kept_text != text:
                keep_and_write(data, kept_text)
        steps = [{"step": "site.toml", "status": "written", "detail": f"as at {kept['at']}"}]
        if request.serve and kept.get("served") and serve is not None:
            try:
                serve(kept["served"], False)
                steps.append({"step": "serve", "status": "written", "detail": f"serving {kept['served'][:8]}, this run only"})
            except (ValueError, OSError) as exc:
                steps.append({"step": "serve", "status": "refused", "detail": str(exc)})
        data, text = read()
        return {**body(data, text), "steps": steps}

    @app.put("/api/served")
    def put_served(request: ServeRequest):
        if serve is None:
            raise HTTPException(
                405, "no controller opened this editor, so nothing is served here"
            )
        from dotbot.cli._config_write import WriteError

        try:
            served = serve(request.spec, request.persist)
        except (ValueError, OSError, WriteError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {**served, "site": state.name, "path": str(state.path)}

    def served_id() -> str | None:
        served = opened_by().get("served")
        return served.get("id") if served else None

    @app.post("/api/done")
    def done():
        if on_done is not None:
            on_done()
        return {"ok": True}

    def write_site(revision: str, text: str) -> None:
        with saving:
            data, _ = read()
            if site_toml.revision(data) != revision:
                raise HTTPException(
                    409, f"{state.path} changed on disk since the page loaded it"
                )
            keep_and_write(data, text)

    placement = site_placement.create_router(
        state.name, state.pack, lambda: read()[1], write_site, served_id, serve
    )
    app.include_router(placement)
    app.include_router(
        site_backdrops.create_router(
            state.name,
            lambda: [state.pack / PACK_CALIBRATIONS, *state.calibration_dirs],
            lambda: read()[1],
        )
    )

    if page_dir is None:
        return app

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(page_dir / EDITOR_PAGE)

    if page_dir.is_dir():
        app.mount("/", StaticFiles(directory=page_dir), name="page")
    return app
