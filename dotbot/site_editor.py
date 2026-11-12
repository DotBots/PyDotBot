# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's server: one site pack's `site.toml` over JSON, and the
page that draws it.

It runs on its own, with no controller, broker or robot. Every save is
checked against the revision the page loaded, so an edit made to the file
meanwhile is never overwritten.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotbot import site_backdrops, site_draft, site_history, site_placement, site_toml
from dotbot.calibration import site_frame, site_turn, station_rule
from dotbot.calibration.placement import save_new, site_tags
from dotbot.calibration.station_boxes import push_line
from dotbot.config import ObjectKind, SiteSection
from dotbot.same_origin import cross_site_refusal
from dotbot.site import PACK_CALIBRATIONS, Site, site_from_table
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


class AnchorSpotModel(BaseModel):
    at_mm: tuple[float, float]
    error_mm: float = Field(ge=0.0)


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
    anchor_spots: list[AnchorSpotModel] | None = None


class SaveRequest(BaseModel):
    revision: str
    site: SiteModel
    # site.toml as edited by hand on the page, patched instead of the file
    text: str | None = None


class PreviewRequest(BaseModel):
    site: SiteModel
    text: str | None = None


class ApplyRequest(BaseModel):
    """One Save of the editor's draft: site.toml and at most one calibration,
    composed from every pending edit, written in one go."""

    revision: str
    site: SiteModel | None = None
    text: str | None = None
    calibration: site_draft.CalibrationEdit | None = None
    # Make this controller use the calibration the save leaves
    use: bool = True
    # Say what the save would write, and write nothing
    dry_run: bool = False


class FrameRequest(BaseModel):
    """The draft as it would be after a move of the origin."""

    # The calibration the move re-expresses
    calibration: str
    # The draft's site, in the frame `start` leaves, and the file as loaded
    site: SiteModel
    base: SiteModel
    start: site_draft.Move | None = None
    move: site_draft.Move
    # The drafted station rectangles, in the frame `start` leaves
    stations: dict[int, tuple[int, int, int, int]] | None = None


class SpotPair(BaseModel):
    # Where the spot is, tape-measured, in the frame to anchor
    at_mm: tuple[float, float]
    # Where a robot standing on it read itself, in the saved frame
    read_mm: tuple[float, float]


class AnchorRequest(BaseModel):
    spots: list[SpotPair] = Field(min_length=1)


class ServeRequest(BaseModel):
    # A calibration id, tag or path, resolved under the site
    spec: str
    # Also at the next start: written to the controller's config
    persist: bool = False
    # The id the page saw served, "" or "none" for nothing: the switch is
    # refused when the controller serves something else by now
    expected: str | None = None


class CheckRequest(BaseModel):
    calibration: str
    mark_mm: tuple[float, float]
    measured_mm: tuple[float, float]
    robot: str
    predicted_mm: float | None = None
    note: str = ""
    # The fix taken as the robot's without a measurement on the mark
    assumed: bool = False
    # The site.toml revision the check was made against
    revision: str | None = None


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
            "frame_id": site.get("frame")
            or derived_frame_id(state.name, site.get("anchor") or ""),
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
        if (
            model.frame
            or current.get("frame")
            or (model.anchor or "") == (current.get("anchor") or "")
        ):
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
            raise HTTPException(
                422, f"the edited site.toml does not read: {exc}"
            ) from exc
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
        data, text, written = write_model(request.revision, request.site, request.text)
        return {**body(data, text), "written": written}

    def site_of(text: str) -> Site:
        try:
            table = SiteSection.model_validate(tomllib.loads(text))
            return site_from_table(state.name, table, state.pack)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"site.toml would not read: {exc}") from exc

    def existing_file(calibration_id: str) -> dict | None:
        for meta in map(site_placement.file_metadata, site_placement.files(state.pack)):
            if meta and meta["id"] == calibration_id:
                return {key: meta[key] for key in ("id", "id8", "tag", "path")}
        return None

    def refused(exc: site_draft.ComposeRefused) -> HTTPException:
        offer = (
            None
            if exc.offer is None
            else {"dx_mm": exc.offer[0], "dy_mm": exc.offer[1]}
        )
        return HTTPException(422, {"message": str(exc), "offer": offer})

    def taken_tags() -> list[str]:
        return site_tags(state.name, site_placement.files(state.pack))

    def planned(request: ApplyRequest, data: bytes, text: str) -> dict:
        """What `request` writes, worked out and checked; nothing written."""
        if site_toml.revision(data) != request.revision:
            raise HTTPException(
                409, f"{state.path} changed on disk since the page loaded it"
            )
        base = base_of(text, request.text)
        edit = request.calibration
        frame = edit.frame if edit is not None and edit.frame is not None else None
        frame = frame if frame is not None and frame.moves else None
        model = request.site
        site_now = placement.current_site()
        frame_id = None
        if frame is not None:
            if model is None:
                raise HTTPException(
                    422, "a move of the origin is saved with the site as drafted"
                )
            frame_id = site_frame.new_frame_id(
                site_now.frame_id, frame.theta_deg, frame.pivot, frame.shift
            )
            model = model.model_copy(update={"frame": frame_id})
        new_text = patched(base, stamped(base, model)) if model is not None else base
        out: dict = {
            "text": new_text,
            "site_changed": new_text != text,
            "frame": frame_id,
            "from_frame": site_now.frame_id,
            "calibration": None,
            "result": None,
        }
        if edit is None:
            return out
        source = placement.resolve(edit.source)
        try:
            result, warnings = site_draft.composed(
                source, site_now, site_of(new_text), edit, taken_tags()
            )
        except site_draft.ComposeRefused as exc:
            raise refused(exc) from exc
        unchanged = result is source
        existing = None if unchanged else existing_file(result.id)
        out["result"] = result
        out["calibration"] = {
            "id": result.id,
            "id8": result.id8,
            "tag": existing["tag"] if existing else result.tag,
            "source": source.id8,
            "source_tag": source.tag,
            "unchanged": unchanged,
            "existing": existing,
            "new": not unchanged and existing is None,
            "warnings": warnings,
            "reading": station_rule.reading(
                {st.index: st.coverage_mm for st in result.stations}
            ),
            "push": push_line(result),
        }
        return out

    @app.post("/api/apply")
    def apply(request: ApplyRequest):
        """One Save: the calibration the draft makes, if new, then site.toml,
        then this controller uses that calibration. With `dry_run`, what it
        would write."""
        steps = []
        with saving:
            data, text = read()
            plan = planned(request, data, text)
            cal = plan.pop("calibration")
            result = plan.pop("result")
            use = (
                cal is not None
                and not cal["unchanged"]
                and request.use
                and serve is not None
                and served_id() != cal["id"]
            )
            if request.dry_run:
                return {**plan, "calibration": cal, "use": use}
            if cal is not None:
                if cal["unchanged"]:
                    steps.append(
                        {
                            "step": "calibration",
                            "status": "unchanged",
                            "detail": f"{cal['id8']} as it was",
                            "id": cal["id"],
                        }
                    )
                elif cal["existing"] is not None:
                    steps.append(
                        {
                            "step": "calibration",
                            "status": "reused",
                            "detail": cal["existing"]["path"],
                            "id": cal["id"],
                        }
                    )
                else:
                    saved, path = save_new(result)
                    steps.append(
                        {
                            "step": "calibration",
                            "status": "written",
                            "detail": str(path),
                            "id": saved.id,
                        }
                    )
            if plan["site_changed"]:
                keep_and_write(data, plan["text"])
            steps.append(
                {
                    "step": "site.toml",
                    "status": "written" if plan["site_changed"] else "unchanged",
                    "detail": str(state.path),
                }
            )
        if use:
            try:
                serve(cal["id"], False)
                steps.append(
                    {
                        "step": "use",
                        "status": "written",
                        "detail": f"in use here until the controller restarts: {cal['tag'] or cal['id8']}",
                        "id": cal["id"],
                    }
                )
            except (ValueError, OSError) as exc:
                steps.append({"step": "use", "status": "refused", "detail": str(exc)})
        data, text = read()
        return {
            **body(data, text),
            "ok": all(s["status"] != "refused" for s in steps),
            "steps": steps,
            "calibration": cal,
        }

    @app.post("/api/frame")
    def frame_move(request: FrameRequest):
        """The draft after a move of the origin: its site and the file as
        loaded, renumbered so everything stays where it is on the floor, the
        drafted rectangles likewise, and the calibration's own coverage in
        the moved frame. Nothing is written; a move a robot could not take
        is refused with the largest legal shift."""
        source = placement.resolve(request.calibration)
        site_now = placement.current_site()
        move = request.move
        if move.moves:
            frame = site_frame.new_frame_id(
                site_now.frame_id, move.theta_deg, move.pivot, move.shift
            )
            try:
                moved = site_frame.moved(
                    source,
                    site_now,
                    move.theta_deg,
                    move.pivot,
                    move.shift,
                    site_now.anchor,
                    frame,
                )
            except site_turn.TurnRefused as exc:
                raise refused(
                    site_draft.ComposeRefused(
                        str(exc),
                        site_frame.largest_shift(
                            source, site_now, move.theta_deg, move.pivot, move.shift
                        ),
                    )
                ) from exc
        else:
            frame, moved = site_now.frame_id, source
        floor = site_draft.between(request.start, move)
        stations = (
            None
            if request.stations is None
            else {
                index: [max(0, v) for v in floor.box(rect)]
                for index, rect in request.stations.items()
            }
        )
        keep = site_draft.kept_rects(moved) + list((stations or {}).values())
        points = site_draft.kept_points(moved)
        site = site_draft.moved_site(_model_dict(request.site), floor, keep, points)
        warnings = []
        if move.moves:
            # Measured points against the draft's extent once moved, not the file's
            extent = site.get("extent_mm")
            warnings = site_turn.outside_warnings(
                moved,
                dataclasses.replace(
                    site_now, extent_mm=tuple(extent) if extent else None
                ),
            ) + site_turn.widened_note(move.theta_deg)
        return {
            "frame": frame,
            "from_frame": site_now.frame_id,
            "site": site,
            "base": site_draft.moved_site(
                _model_dict(request.base), move.floor(), keep, points
            ),
            "stations": stations,
            "coverage": {st.index: list(st.coverage_mm) for st in moved.stations},
            "warnings": warnings,
        }

    @app.post("/api/anchor")
    def anchor(request: AnchorRequest):
        """The move of the origin that best lays the tape-measured spots on
        the robots' reads, and each spot's residual under it; nothing is
        written. One spot shifts the origin; two or more also turn it."""
        fit = site_frame.fit_spots(
            [spot.at_mm for spot in request.spots],
            [spot.read_mm for spot in request.spots],
        )
        return {
            "move": {
                "theta_deg": fit.theta_deg,
                "pivot": list(fit.pivot),
                "dx_mm": fit.shift[0],
                "dy_mm": fit.shift[1],
            },
            "residuals_mm": fit.residuals_mm,
            "worst_mm": max(fit.residuals_mm),
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

        return {
            "checks": checks.read_checks(state.name),
            "path": str(checks.checks_path(state.name)),
        }

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
            assumed=request.assumed,
            site_revision=request.revision,
        )

    @app.get("/api/provenance")
    def get_provenance(request: Request):
        from dotbot.calibration import checks
        from dotbot.calibration.multi_station import error_map_from_calibration
        from dotbot.calibration.provenance import provenance_lines

        cal = served_calibration()
        if cal is None:
            raise HTTPException(
                404,
                "no calibration is served or configured, so there is nothing to record",
            )
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
                raise HTTPException(
                    409, f"{state.path} changed on disk since the page loaded it"
                )
            if kept_text != text:
                keep_and_write(data, kept_text)
        steps = [
            {"step": "site.toml", "status": "written", "detail": f"as at {kept['at']}"}
        ]
        if request.serve and kept.get("served") and serve is not None:
            try:
                serve(kept["served"], False)
                steps.append(
                    {
                        "step": "serve",
                        "status": "written",
                        "detail": f"serving {kept['served'][:8]}, this run only",
                    }
                )
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

        if request.expected is not None:
            found = opened_by()
            current = (found.get("served") or {}).get("id")
            expected = request.expected.strip().lower()
            if expected in ("", "none"):
                matches = current is None
            else:
                matches = current is not None and current.lower().startswith(expected)
            if not matches:
                raise HTTPException(
                    409,
                    {
                        "message": (
                            f"the controller now uses "
                            f"{current[:8] if current else 'nothing'}, not "
                            f"{expected[:8] if expected not in ('', 'none') else 'nothing'}"
                            ": look again before switching"
                        ),
                        "served": found.get("served"),
                    },
                )
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

    placement = site_placement.create_router(
        state.name,
        state.pack,
        lambda: read()[1],
        served_id,
        context=opened_by,
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


class NewSiteRequest(BaseModel):
    name: str
    note: str = ""
    # "empty": the floor measured later; "size": a known floor; "spin":
    # around the robots of a spin calibration already done
    start: Literal["empty", "size", "spin"] = "empty"
    size_mm: tuple[int, int] | None = None
    calibration: str | None = None
    # The controller takes the new site at once
    use: bool = True
    persist: bool = False


class UseSiteRequest(BaseModel):
    name: str
    persist: bool = False


NO_PACK = "the controller's site is not read from a site pack"


def create_lobby_app(
    current: Callable[[], tuple[str, Path | None]],
    use: Callable[[str, Path, bool], dict] | None = None,
    context: Callable[[], dict] | None = None,
    page_dir: Path | None = EDITOR_DIR,
) -> FastAPI:
    """The site list and New site, for a controller with or without a site
    pack: `current()` names the controller's site and its pack, `use(name,
    pack, persist)` switches it. Every other route answers 404 with NO_PACK."""
    from dotbot.site_new import NewSiteRefused, home_beside, write_new_site
    from dotbot.site_packs import user_sites_dir

    app = FastAPI(title="DotBot site editor, sites", docs_url=None, redoc_url=None)
    app.add_middleware(LocalOnly)

    def homes() -> list[Path]:
        _, pack = current()
        out = [home_beside(pack)]
        if user_sites_dir().resolve() != out[0].resolve():
            out.append(user_sites_dir())
        return out

    def packs() -> dict[str, Path]:
        found: dict[str, Path] = {}
        for home in homes():
            if not home.is_dir():
                continue
            for folder in sorted(home.iterdir()):
                if (folder / PACK_FILE).is_file() and folder.name not in found:
                    found[folder.name] = folder
        return found

    def switch(name: str, pack: Path, persist: bool) -> dict:
        if use is None:
            raise HTTPException(409, "only a controller switches site")
        try:
            return use(name, pack, persist)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sites")
    def sites():
        from dotbot.site import site_from_table
        from dotbot.site_packs import read_pack

        name, pack = current()
        rows = []
        for site_name, folder in packs().items():
            try:
                site = site_from_table(site_name, read_pack(folder), folder)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "name": site_name,
                        "shown_path": _shown_path(folder / PACK_FILE),
                        "error": str(exc),
                    }
                )
                continue
            rows.append(
                {
                    "name": site_name,
                    "shown_path": _shown_path(folder / PACK_FILE),
                    "current": pack is not None and folder.resolve() == pack.resolve(),
                    "extent_mm": list(site.extent_mm) if site.extent_mm else None,
                    "anchor": site.anchor,
                    "frame_id": site.frame_id,
                    "areas": len(site.areas),
                }
            )
        return {
            "current": name,
            "has_pack": pack is not None,
            "home": _shown_path(homes()[0]),
            "sites": rows,
        }

    @app.post("/api/sites")
    def new_site(request: NewSiteRequest):
        source = None
        if request.start == "spin":
            from dotbot.calibration.lighthouse2 import load_calibration

            try:
                source = load_calibration(request.calibration or "")
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        _, pack = current()
        try:
            written = write_new_site(
                home_beside(pack),
                request.name,
                request.start,
                request.note,
                request.size_mm,
                source,
            )
        except NewSiteRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        out = {
            "name": written.name,
            "shown_path": _shown_path(written.pack / PACK_FILE),
            "calibration": written.calibration.id8 if written.calibration else None,
            "used": None,
        }
        if request.use:
            out["used"] = switch(written.name, written.pack, request.persist)
        return out

    @app.put("/api/sites/current")
    def use_site(request: UseSiteRequest):
        folder = packs().get(request.name)
        if folder is None:
            raise HTTPException(404, f"no site pack named {request.name}")
        return switch(request.name, folder, request.persist)

    @app.get("/api/context")
    def get_context(request: Request):
        name, pack = current()
        return {
            **(context() if context is not None else {"mode": "standalone"}),
            "no_site": pack is None,
            "site_name": name,
            "can_write": can_write(request.scope),
        }

    @app.api_route(
        "/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
    )
    def no_pack(rest: str):
        raise HTTPException(404, NO_PACK)

    if page_dir is None:
        return app

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(page_dir / EDITOR_PAGE)

    if page_dir.is_dir():
        app.mount("/", StaticFiles(directory=page_dir), name="page")
    return app
