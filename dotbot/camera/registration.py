# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The registration a camera collect produces: the solve, and the file.

Registration is the same object the lighthouse produces: one homography
from an instrument's pixels into the site's frame, solved by least squares,
carrying its own reprojection residual and a deterministic id, written
under `calibrations/<site>/`. The solver, the residual and the file's float
rendering come from `lighthouse2` so the two files are one format with two
kinds.
"""

from __future__ import annotations

import datetime
import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from dotbot.area import Area
from dotbot.calibration.lighthouse2 import (
    apply_homography,
    calibration_root,
    compute_homography_matrix,
    reprojection_residual_mm,
    site_dir,
    toml_escape,
    toml_matrix,
    toml_num,
    toml_points,
)
from dotbot.calibration.points import CORNERS
from dotbot.camera.capture import Probe
from dotbot.camera.sheets import (
    MARKER_DICTIONARY,
    MARKER_SIDE_MM,
    Marker,
    corner_of,
    span_mm,
)
from dotbot.site import SITE_DEFAULT, Site

# Above this the registration is reported as suspect. At about 1 mm of floor
# per pixel a sub-pixel fit lands near 1 mm, so 5 mm is several pixels of
# disagreement across the sheets rather than noise.
RESIDUAL_WARN_MM = 5.0

LENS_DEFAULT = "linear"


@dataclass
class Solution:
    """The homography, what it cost, and which sheet fits worst.

    The fit takes all sixteen marker corners rather than the four centres:
    four points fix the eight unknowns exactly and report a residual of zero
    by construction, which says nothing about the registration.
    """

    matrix: list[list[float]]
    residual_mm: float
    per_marker_mm: dict[int, float]

    @property
    def worst(self) -> tuple[int, float]:
        """The marker furthest from where the layout puts it."""
        marker_id = max(self.per_marker_mm, key=self.per_marker_mm.get)
        return marker_id, self.per_marker_mm[marker_id]


def solve(layout: Sequence[Marker], corners_px: dict[int, np.ndarray]) -> Solution:
    """Fit image pixels to frame millimetres over every marker corner."""
    missing = [m.id for m in layout if m.id not in corners_px]
    if missing:
        raise ValueError(
            "cannot solve without every sheet: "
            + ", ".join(f"marker {i} ({corner_of(i)})" for i in missing)
            + " was never read"
        )
    pixels = np.array(
        [corner for m in layout for corner in corners_px[m.id]], dtype=np.float64
    )
    millimetres = np.array(
        [corner for m in layout for corner in m.corners_mm], dtype=np.float64
    )
    matrix = compute_homography_matrix(pixels, millimetres)
    residual = reprojection_residual_mm(matrix, pixels, millimetres)
    projected = apply_homography(matrix, pixels)
    per_marker = {}
    for index, marker in enumerate(layout):
        block = slice(index * 4, index * 4 + 4)
        errors = np.linalg.norm(projected[block] - millimetres[block], axis=1)
        per_marker[marker.id] = float(np.sqrt(np.mean(errors**2)))
    return Solution(
        matrix=[[float(v) for v in row] for row in matrix],
        residual_mm=residual,
        per_marker_mm=per_marker,
    )


# --- The file ---------------------------------------------------------------

CAMERA_SCHEMA_VERSION = 1
CAMERA_KIND = "camera"
CAMERA_TOML_GLOB = "camera-*.toml"


@dataclass
class MarkerObservation:
    """One sheet as the file records it: where it is, and where it was seen."""

    id: int
    centre_mm: tuple[float, float]
    corners_mm: tuple[tuple[float, float], ...]
    corners_px: tuple[tuple[float, float], ...]
    dictionary: str = MARKER_DICTIONARY
    side_mm: float = MARKER_SIDE_MM


@dataclass
class CameraCalibration:
    """One camera's registration into a site's frame."""

    site: Site = field(default_factory=Site)
    area: str = ""
    source: int | str = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    lens: str = LENS_DEFAULT
    intrinsics: str = ""
    reads: int = 0
    # The camera's colour controls as `collect` read them back. Empty for a
    # registration written before they were recorded, which applies and
    # compares nothing.
    controls: dict = field(default_factory=dict)
    markers: list[MarkerObservation] = field(default_factory=list)
    matrix: list[list[float]] = field(default_factory=list)
    residual_mm: float = 0.0
    span_mm: list[tuple[float, float]] = field(default_factory=list)
    created: str = ""
    path: Path | None = None
    # The id the file on disk declares. A mismatch with `id` means the file
    # was hand-edited into a different registration.
    stored_id: str = ""

    @property
    def id(self) -> str:
        return camera_calibration_id(self)

    @property
    def id8(self) -> str:
        return self.id[:8]


def camera_canonical_serialisation(calibration: CameraCalibration) -> str:
    """The text the camera calibration's id is the digest of.

    Same rule as the lighthouse's: a field that cannot change a computed
    position is not in here. So the anchor, the source, the lens mode, the
    delivered mode and the read count are all provenance and stay out, and
    the span stays out too because it is derived from `corners_mm`.
    """
    lines = [
        f"schema_version={CAMERA_SCHEMA_VERSION}",
        f"kind={CAMERA_KIND}",
        f"site.name={calibration.site.name}",
        f"camera.area={calibration.area}",
    ]
    for marker in sorted(calibration.markers, key=lambda m: m.id):
        key = f"marker.{marker.id}"
        lines.append(f"{key}.dictionary={marker.dictionary}")
        lines.append(f"{key}.side_mm={toml_num(marker.side_mm)}")
        lines.append(
            f"{key}.corners_mm="
            + ";".join(f"{toml_num(x)},{toml_num(y)}" for x, y in marker.corners_mm)
        )
        lines.append(
            f"{key}.corners_px="
            + ";".join(f"{toml_num(x)},{toml_num(y)}" for x, y in marker.corners_px)
        )
    lines.append(
        "homography.matrix="
        + ";".join(",".join(toml_num(v) for v in row) for row in calibration.matrix)
    )
    return "\n".join(sorted(lines))


def camera_calibration_id(calibration: CameraCalibration) -> str:
    """Truncated SHA-256 over the canonical serialisation, 16 hex characters."""
    digest = hashlib.sha256(
        camera_canonical_serialisation(calibration).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def render_camera_calibration(calibration: CameraCalibration) -> str:
    """The schema 1 camera file, as text."""
    site = calibration.site
    out = [
        f"schema_version = {CAMERA_SCHEMA_VERSION}",
        f'kind = "{CAMERA_KIND}"',
        f'created = "{calibration.created}"',
        f'id = "{calibration.id}"',
        "",
        "[site]",
        f'name = "{site.name}"',
        f'anchor = "{toml_escape(site.anchor)}"',
        "",
        "[camera]",
        f'area = "{toml_escape(calibration.area)}"',
        f"source = {_toml_source(calibration.source)}",
        f"width = {int(calibration.width)}",
        f"height = {int(calibration.height)}",
        f"fps = {toml_num(calibration.fps)}",
        f'lens = "{toml_escape(calibration.lens)}"',
        f'intrinsics = "{toml_escape(calibration.intrinsics)}"',
        f"reads = {int(calibration.reads)}",
    ]
    if calibration.controls:
        out += ["", "[camera.controls]"]
        out += [
            f"{name} = {toml_num(value)}"
            for name, value in sorted(calibration.controls.items())
        ]
    for marker in sorted(calibration.markers, key=lambda m: m.id):
        out += [
            "",
            "[[marker]]",
            f"id = {marker.id}",
            f'dictionary = "{marker.dictionary}"',
            f"side_mm = {toml_num(marker.side_mm)}",
            f"centre_mm = [{toml_num(marker.centre_mm[0])}, {toml_num(marker.centre_mm[1])}]",
            f"corners_mm = {toml_points(marker.corners_mm)}",
            f"corners_px = {toml_points(marker.corners_px)}",
        ]
    out += [
        "",
        "[homography]",
        f"matrix = {toml_matrix(calibration.matrix)}",
        f"residual_mm = {toml_num(calibration.residual_mm)}",
        f"span_mm = {toml_points(calibration.span_mm)}",
    ]
    return "\n".join(out) + "\n"


def _toml_source(source: int | str) -> str:
    """The source as TOML: an index as a number, anything else as a string."""
    if isinstance(source, int) and not isinstance(source, bool):
        return str(source)
    return f'"{toml_escape(str(source))}"'


def read_camera_calibration_file(path: Path) -> CameraCalibration:
    """Parse a schema 1 camera file.

    `kind` is checked before the schema version, so a lighthouse file handed
    to `--camera-calibration` is refused for what it is rather than for its
    version number.
    """
    path = Path(path)
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    kind = data.get("kind", "")
    if kind != CAMERA_KIND:
        raise ValueError(
            f"{path}: not a camera calibration (kind {kind!r}). A lighthouse "
            "calibration goes to --calibration, a camera one here."
        )
    schema = data.get("schema_version", 0)
    if schema != CAMERA_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported camera calibration schema_version {schema} "
            f"(this build supports {CAMERA_SCHEMA_VERSION})"
        )
    site_data = data.get("site", {})
    camera_data = data.get("camera", {})
    homography = data.get("homography", {})
    calibration = CameraCalibration(
        site=Site(
            name=site_data.get("name", SITE_DEFAULT),
            anchor=site_data.get("anchor", ""),
        ),
        area=camera_data.get("area", ""),
        source=camera_data.get("source", 0),
        width=int(camera_data.get("width", 0)),
        height=int(camera_data.get("height", 0)),
        fps=float(camera_data.get("fps", 0.0)),
        lens=camera_data.get("lens", ""),
        intrinsics=camera_data.get("intrinsics", ""),
        reads=int(camera_data.get("reads", 0)),
        controls={
            str(name): float(value)
            for name, value in (camera_data.get("controls", {}) or {}).items()
        },
        markers=[
            MarkerObservation(
                id=int(raw["id"]),
                centre_mm=(float(raw["centre_mm"][0]), float(raw["centre_mm"][1])),
                corners_mm=tuple((float(p[0]), float(p[1])) for p in raw["corners_mm"]),
                corners_px=tuple((float(p[0]), float(p[1])) for p in raw["corners_px"]),
                dictionary=raw.get("dictionary", MARKER_DICTIONARY),
                side_mm=float(raw.get("side_mm", MARKER_SIDE_MM)),
            )
            for raw in data.get("marker", [])
        ],
        matrix=[[float(v) for v in row] for row in homography.get("matrix", [])],
        residual_mm=float(homography.get("residual_mm", 0.0)),
        span_mm=[(float(p[0]), float(p[1])) for p in homography.get("span_mm", [])],
        created=data.get("created", ""),
        path=path,
    )
    calibration.stored_id = str(data.get("id", ""))
    return calibration


def resolve_camera_calibration_path(
    spec: str,
    root: Path | None = None,
    site: str | None = None,
) -> Path:
    """The camera file `spec` names: a path, or an id prefix under a site.

    The glob is `camera-*.toml`, so a camera id prefix can never resolve to
    a lighthouse file sitting in the same directory.
    """
    candidate = Path(spec).expanduser()
    if candidate.is_file():
        return candidate

    root = root or calibration_root()
    matches = sorted(
        path
        for path in root.glob(f"{site or '*'}/{CAMERA_TOML_GLOB}")
        if _camera_file_id(path).startswith(spec.lower())
    )
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(
            f"no camera calibration matches {spec!r}: it is neither a readable "
            f"file nor the id prefix of a file under {root / (site or '*')}"
        )
    listed = "\n  ".join(str(m) for m in matches)
    raise ValueError(
        f"camera calibration id prefix {spec!r} matches several files:\n  {listed}"
    )


def _camera_file_id(path: Path) -> str:
    """The id a file declares, read without solving anything."""
    try:
        with open(path, "rb") as handle:
            return str(tomllib.load(handle).get("id", "")).lower()
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def load_camera_calibration(
    spec: str,
    root: Path | None = None,
    site: str | None = None,
) -> CameraCalibration:
    """Read the camera calibration `spec` names."""
    return read_camera_calibration_file(
        resolve_camera_calibration_path(spec, root, site)
    )


def write_camera_calibration(
    calibration: CameraCalibration, root: Path | None = None
) -> Path:
    """Write to `calibrations/<site>/camera-<stamp>-<id8>.toml`."""
    stamp = (calibration.created or "").replace(":", "-")
    directory = (
        root / calibration.site.name
        if root is not None
        else site_dir(calibration.site.name)
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"camera-{stamp}-{calibration.id8}.toml"
    path.write_text(render_camera_calibration(calibration), encoding="utf-8")
    calibration.path = path
    return path


def build_calibration(
    site: Site,
    area: Area,
    layout: Sequence[Marker],
    corners_px: dict[int, np.ndarray],
    solution: Solution,
    probe_result: Probe,
    reads: int,
    lens: str = LENS_DEFAULT,
    intrinsics: str = "",
    created: str = "",
) -> CameraCalibration:
    """Everything the file records, assembled from one collect run."""
    now = created or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return CameraCalibration(
        site=site,
        area=area.name,
        source=probe_result.source,
        width=probe_result.width,
        height=probe_result.height,
        fps=probe_result.fps,
        lens=lens,
        intrinsics=intrinsics,
        reads=reads,
        controls=dict(probe_result.controls),
        markers=[
            MarkerObservation(
                id=marker.id,
                centre_mm=marker.centre_mm,
                corners_mm=marker.corners_mm,
                corners_px=tuple(
                    (float(x), float(y)) for x, y in corners_px[marker.id]
                ),
            )
            for marker in layout
        ],
        matrix=solution.matrix,
        residual_mm=solution.residual_mm,
        span_mm=span_mm(layout),
        created=now,
    )


# --- What the operator reads ------------------------------------------------


def collect_header(site: Site, area: Area, reads: int) -> str:
    """The paragraph printed once, before the placement instructions."""
    zero = (
        site.anchor
        or "the site's anchor, which this config does not describe (add "
        f"`anchor` to [sites.{site.name}])"
    )
    return (
        f"\nRegistering a camera over {area.name} in site {site.name}. "
        "Coordinates are millimetres in the site's frame: x grows right, y "
        f"grows down, and zero is {zero}.\n"
        "Tape one printed sheet inside each corner of the area, its two outer "
        "edges on the area's edge lines, page top toward the top of the map. "
        "All four the same way up.\n"
        f"{len(CORNERS)} sheets, then {reads} "
        f"{'read' if reads == 1 else 'reads'} of them.\n"
    )


def sheet_prompt(marker: Marker, area: Area) -> str:
    """Where one sheet goes, as an instruction."""
    x, y = marker.centre_mm
    return (
        f"sheet {marker.id} inside the {marker.corner} corner of {area.name}, "
        f"edges on the lines; marker centre ({x:g}, {y:g}) mm"
    )
