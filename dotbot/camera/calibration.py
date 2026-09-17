# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Camera registration: where the ArUco sheets go, and what one looks like.

An overhead camera is registered against four printed markers whose frame
coordinates are derived from an area's corners rather than measured with a
tape. One A4 sheet carries one marker, the sheet sits inside a corner with
its outer edges on the area's edge lines, and the marker is centred on the
page - so the centre is the corner inset by half a page, and the operator
measures nothing.

Registration itself is the same object the lighthouse produces: one
homography from an instrument's pixels into the site's frame, solved by
least squares, carrying its own reprojection residual and a deterministic
id, written under `calibrations/<site>/`. The solver, the residual and the
file's float rendering come from `lighthouse2` so the two files are one
format with two kinds.

`cv2` draws the marker, reads the camera and solves; `PIL` sets the type
and writes the sheets. Both are imported inside the functions that need
them, so the layout and the file are available without the `[calibrate]`
extra installed.
"""

from __future__ import annotations

import datetime
import hashlib
import sys
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Sequence

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
from dotbot.site import SITE_DEFAULT, Site

MM_PER_INCH = 25.4

# A4 portrait, and the density a sheet is rendered and printed at.
PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
SHEET_DPI = 300

# 150 mm is what the page allows with a quiet zone: a 4x4 marker is six
# cells across counting its black border, so 25 mm per cell, and the 30 mm
# side margins leave a cell of white on every side inside the printer's own
# margin.
MARKER_DICTIONARY = "DICT_4X4_50"
MARKER_SIDE_MM = 150.0

# Printed beside the id so the operator can verify the print came out at
# 100 % with a ruler before taping anything down.
SCALE_BAR_MM = 100.0

# The placement diagram: a square standing for the area, in the bottom
# margin right of the caption. It is anchored by its top-right corner,
# whose x lines up with the marker's right edge so the printed matter is
# one column, and whose y clears the marker's quiet zone. Square because a
# sheet carries no area and so cannot know the real one's proportions.
DIAGRAM_RIGHT_MM = 180.0
DIAGRAM_TOP_MM = 250.0
DIAGRAM_SIDE_MM = 26.0

# One sheet's seat in that square, A4 proportioned like the page it stands
# for, so four of them read as pages rather than as corner marks.
DIAGRAM_SEAT_HEIGHT_MM = 7.0

# Plain sans faces to set the caption in, macOS first then Linux. Pillow's
# own face stands in when none is installed.
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
)


def _px(mm: float) -> int:
    """Millimetres as whole pixels at the sheet's print density."""
    return round(mm * SHEET_DPI / MM_PER_INCH)


PAGE_WIDTH_PX = _px(PAGE_WIDTH_MM)
PAGE_HEIGHT_PX = _px(PAGE_HEIGHT_MM)
MARKER_SIDE_PX = _px(MARKER_SIDE_MM)


@lru_cache(maxsize=1)
def _font_file() -> str | None:
    """The first installed candidate face, or None for Pillow's own."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    print(
        "camera sheets: no system sans face found, setting the caption in "
        "Pillow's built-in one; the printed geometry is unaffected.",
        file=sys.stderr,
    )
    return None


@lru_cache(maxsize=None)
def _font(size_mm: float):
    """The caption face at a body size given in millimetres."""
    from PIL import ImageFont

    candidate = _font_file()
    if candidate is None:
        return ImageFont.load_default(size=_px(size_mm))
    return ImageFont.truetype(candidate, _px(size_mm))


def _diagram_frame_px() -> tuple[int, int, int, int]:
    """The diagram's square in whole pixels, as (left, top, right, bottom).

    Built from one corner and one side, so the square is square on the
    page rather than two spans rounded apart.
    """
    side = _px(DIAGRAM_SIDE_MM)
    right, top = _px(DIAGRAM_RIGHT_MM), _px(DIAGRAM_TOP_MM)
    return right - side, top, right, top + side


def corner_of(marker_id: int) -> str:
    """The area corner a marker id names.

    This and `marker_id_for` are the only place the relation between an id
    and a corner is written: the layout, the sheet renderer, the probe's
    marker report and the solver all read it through the pair. Today it is
    the identity onto `CORNERS`, which is what lets the camera and the
    lighthouse share one corner vocabulary; widening it to carry an area
    index as well is these two bodies and nothing else.
    """
    if not isinstance(marker_id, (int, np.integer)) or isinstance(marker_id, bool):
        raise ValueError(f"marker id {marker_id!r} is not a whole number")
    if not 0 <= marker_id < len(CORNERS):
        raise ValueError(
            f"marker {marker_id} names no area corner; this layout carries "
            f"{', '.join(str(marker_id_for(c)) for c in CORNERS)}"
        )
    return CORNERS[marker_id]


def marker_id_for(corner: str) -> int:
    """The marker id that goes in one corner of an area."""
    if corner not in CORNERS:
        raise ValueError(
            f"unknown corner {corner!r}; expected one of {', '.join(CORNERS)}"
        )
    return CORNERS.index(corner)


def layout_ids() -> tuple[int, ...]:
    """The four ids one area's sheets carry, in `CORNERS` order."""
    return tuple(marker_id_for(corner) for corner in CORNERS)


@dataclass(frozen=True)
class Marker:
    """One sheet's marker, and where its corners land in the site's frame.

    `id` names the corner the sheet belongs in through `corner_of`, so the
    printed id and the area's corner are one vocabulary. `corners_mm` is in
    ArUco's own order - top-left, top-right, bottom-right, bottom-left - so
    it pairs element by element with the pixel corners the detector returns.
    """

    id: int
    centre_mm: tuple[float, float]
    corners_mm: tuple[tuple[float, float], ...]

    @property
    def corner(self) -> str:
        """The area corner this sheet goes in."""
        return corner_of(self.id)


# Each sheet's own marker corner that faces away from the area's centre,
# listed in the ArUco order a span is stored in.
_SPAN_CORNERS = (
    ("top-left", 0),
    ("top-right", 1),
    ("bottom-right", 2),
    ("bottom-left", 3),
)


def page_inset(corner: str) -> tuple[float, float]:
    """The (dx, dy) from an area corner to the centre of the sheet there.

    The sheet lies inside the rectangle with its two outer edges on the
    rectangle's edge lines and its top toward the top of the frame, and the
    marker is centred on the page, so the inset is half a page either way.
    """
    if corner not in CORNERS:
        raise ValueError(
            f"unknown corner {corner!r}; expected one of {', '.join(CORNERS)}"
        )
    vertical, _, horizontal = corner.partition("-")
    dx, dy = PAGE_WIDTH_MM / 2, PAGE_HEIGHT_MM / 2
    return (dx if horizontal == "left" else -dx, dy if vertical == "top" else -dy)


def sheet_marker(area: Area, corner: str) -> Marker:
    """The marker of the sheet placed in one corner of `area`."""
    dx, dy = page_inset(corner)
    vertical, _, horizontal = corner.partition("-")
    x = (area.x if horizontal == "left" else area.x_max) + dx
    y = (area.y if vertical == "top" else area.y_max) + dy
    half = MARKER_SIDE_MM / 2
    return Marker(
        id=marker_id_for(corner),
        centre_mm=(x, y),
        corners_mm=(
            (x - half, y - half),
            (x + half, y - half),
            (x + half, y + half),
            (x - half, y + half),
        ),
    )


def marker_layout(area: Area) -> list[Marker]:
    """The four sheets of one area, in `CORNERS` order."""
    return [sheet_marker(area, corner) for corner in CORNERS]


def span_mm(layout: Sequence[Marker]) -> list[tuple[float, float]]:
    """The quadrilateral through the four markers' outer corners.

    The homography is fitted to these sixteen corners, so the quadrilateral
    they enclose is the region the registration is trustworthy inside:
    error is flat within it and grows with the square of the distance
    outside it. Returned in ArUco order, top-left first.
    """
    by_corner = {marker.corner: marker for marker in layout}
    missing = [name for name, _ in _SPAN_CORNERS if name not in by_corner]
    if missing:
        raise ValueError(f"layout has no sheet for the {', '.join(missing)} corner(s)")
    return [by_corner[name].corners_mm[index] for name, index in _SPAN_CORNERS]


def render_sheet(marker_id: int) -> np.ndarray:
    """One printable sheet: A4 at 300 dpi with its marker centred.

    Returned as a grayscale page. The marker's position on the page is what
    `marker_layout` derives frame coordinates from, so it is centred
    exactly and everything else lives in the bottom margin.
    """
    import cv2  # lazy: opencv-python is only required to draw a sheet

    corner = corner_of(marker_id)
    page = np.full((PAGE_HEIGHT_PX, PAGE_WIDTH_PX), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, MARKER_DICTIONARY)
    )
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, MARKER_SIDE_PX)
    x0 = (PAGE_WIDTH_PX - MARKER_SIDE_PX) // 2
    y0 = (PAGE_HEIGHT_PX - MARKER_SIDE_PX) // 2
    page[y0 : y0 + MARKER_SIDE_PX, x0 : x0 + MARKER_SIDE_PX] = marker
    _placement_diagram(page, corner)
    return _caption(page, marker_id, corner)


SHEET_FORMATS = ("pdf", "png")


def render_sheets() -> list[np.ndarray]:
    """One page per area corner, in `CORNERS` order."""
    return [render_sheet(marker_id) for marker_id in layout_ids()]


def write_sheets(
    pages: Sequence[np.ndarray],
    out_dir: Path,
    sheet_format: str = "pdf",
    per_sheet: bool = False,
) -> list[Path]:
    """Write rendered pages into `out_dir`, returning the files written.

    `per_sheet` splits the PDF into one single-page file per sheet, which is
    what a printer forcing double-sided output needs: a four-page job comes
    back as two sheets carrying a marker on each face, and a marker on the
    back of another is not tapeable to a floor. PNG has no one-file form, so
    there the flag changes nothing.
    """
    if sheet_format not in SHEET_FORMATS:
        raise ValueError(
            f"unknown sheet format {sheet_format!r}; "
            f"expected one of {', '.join(SHEET_FORMATS)}"
        )
    if sheet_format == "png":
        return _write_pngs(pages, out_dir)
    return _write_pdfs(pages, out_dir) if per_sheet else _write_pdf(pages, out_dir)


def _write_pdf(pages: Sequence[np.ndarray], out_dir: Path) -> list[Path]:
    """The pages as one print job, at a page size declared in points.

    Saved grayscale at full quality: Pillow encodes a PDF page as JPEG,
    and anything lower puts ringing on the fiducial's edges.
    """
    from PIL import Image

    path = out_dir / "camera-markers.pdf"
    images = [Image.fromarray(page) for page in pages]
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        resolution=float(SHEET_DPI),
        quality=100,
    )
    return [path]


def _write_pdfs(pages: Sequence[np.ndarray], out_dir: Path) -> list[Path]:
    """One single-page PDF per sheet, each named for the marker it carries.

    The name carries the marker's own id, which is what the sheet prints and
    what the operator matches to a corner.
    """
    from PIL import Image

    paths = []
    for marker_id, page in zip(layout_ids(), pages):
        path = out_dir / f"camera-marker-{marker_id}.pdf"
        Image.fromarray(page).save(path, resolution=float(SHEET_DPI), quality=100)
        paths.append(path)
    return paths


def _write_pngs(pages: Sequence[np.ndarray], out_dir: Path) -> list[Path]:
    """One image per sheet, each carrying the print density in its header."""
    from PIL import Image

    paths = []
    for marker_id, page in zip(layout_ids(), pages):
        path = out_dir / f"camera-marker-{marker_id}.png"
        Image.fromarray(page).save(path, dpi=(SHEET_DPI, SHEET_DPI))
        paths.append(path)
    return paths


def _caption(page: np.ndarray, marker_id: int, corner: str) -> np.ndarray:
    """The id, the dictionary and the scale bar, in the bottom margin.

    Kept below 250 mm so a full cell of white separates it from the
    marker's border, which the detector needs as a quiet zone. Returns the
    page with the type set, the text coordinates being baselines.
    """
    from PIL import Image, ImageDraw

    image = Image.fromarray(page)
    draw = ImageDraw.Draw(image)
    ink = 0
    left = _px((PAGE_WIDTH_MM - MARKER_SIDE_MM) / 2)
    draw.text(
        (left, _px(255.0)),
        f"marker {marker_id} - {corner} corner",
        font=_font(6.4),
        fill=ink,
        anchor="ls",
    )
    draw.text(
        (left, _px(266.0)),
        f"{MARKER_DICTIONARY}, {MARKER_SIDE_MM:g} mm - print at 100 %",
        font=_font(4.2),
        fill=ink,
        anchor="ls",
    )
    bar_y = _px(278.0)
    bar_end = left + _px(SCALE_BAR_MM)
    draw.line(((left, bar_y), (bar_end, bar_y)), ink, width=5)
    for x in (left, bar_end):
        draw.line(((x, _px(275.0)), (x, _px(281.0))), ink, width=5)
    draw.text(
        (bar_end + _px(5.0), bar_y),
        f"{SCALE_BAR_MM:g} mm",
        font=_font(3.6),
        fill=ink,
        anchor="lm",
    )
    return np.array(image)


def _placement_diagram(page: np.ndarray, sheet_corner: str) -> None:
    """Where this sheet goes, drawn rather than spelled out.

    The square is the area, and each corner holds a page-shaped seat flush
    against its two edges, which is how a sheet is taped. This sheet's
    seat is solid, and the notch in it points at the top of the page, the
    edge that faces the top of the map.

    Laid out in whole pixels off one frame, so the four seats come out
    identical instead of each rounding on its own.
    """
    import cv2

    ink = 0
    left, top, right, bottom = _diagram_frame_px()
    seat_height = _px(DIAGRAM_SEAT_HEIGHT_MM)
    seat_width = round(seat_height * PAGE_WIDTH_MM / PAGE_HEIGHT_MM)
    cv2.rectangle(page, (left, top), (right, bottom), ink, 4, cv2.LINE_AA)
    for corner in CORNERS:
        vertical, _, horizontal = corner.partition("-")
        x = left if horizontal == "left" else right - seat_width
        y = top if vertical == "top" else bottom - seat_height
        far = (x + seat_width, y + seat_height)
        if corner != sheet_corner:
            cv2.rectangle(page, (x, y), far, ink, 3, cv2.LINE_AA)
            continue
        cv2.rectangle(page, (x, y), far, ink, -1, cv2.LINE_AA)
        # The notch has to reach the seat's top edge. A filled seat is a
        # marker-shaped candidate, and one that keeps an unbroken rim of
        # black around a light shape passes the detector's border check
        # and decodes as some other id. Breaking the rim is what rejects
        # it; `test_sheet_decodes_to_its_own_id` is the guard.
        centre = x + seat_width / 2
        notch = np.array(
            [
                [round(centre), y - 1],
                [round(centre - 0.30 * seat_width), y + round(0.42 * seat_height)],
                [round(centre + 0.30 * seat_width), y + round(0.42 * seat_height)],
            ]
        )
        cv2.fillPoly(page, [notch], 255, cv2.LINE_AA)


# --- Finding the camera -----------------------------------------------------

# An OpenCV index is assigned per machine and per session, so no file and no
# flag default can carry it: `collect` opens the indices in turn and keeps
# the one that sees the sheets.
PROBE_INDEX_MAX = 10
PROBE_MISSES_MAX = 2

# Two of three cameras on the bench return a black first frame and a live
# second, and ArUco on black reports zero markers - which reads as "no
# sheets" when the truth is "not ready". Frames are read until one is lit,
# or until the budget runs out.
LIT_MEAN_MIN = 8.0
SETTLE_FRAMES_MAX = 10
SETTLE_SECONDS_MAX = 2.0

# What disqualifies a source when nothing sees markers: a lens cap or a dark
# room, and a blank wall or a ceiling. Telling a floor from a face is not
# attempted - both are lit and structured, and a rule ranking them would be
# a guess dressed as a measurement.
DARK_MEAN_MAX = 20.0
FLAT_SPREAD_MAX = 12.0

READS_DEFAULT = 25

# Above this the registration is reported as suspect. At about 1 mm of floor
# per pixel a sub-pixel fit lands near 1 mm, so 5 mm is several pixels of
# disagreement across the sheets rather than noise.
RESIDUAL_WARN_MM = 5.0

LENS_DEFAULT = "linear"


def open_capture(source: int | str, open_source: Callable | None = None):
    """Open one video source, defaulting to `cv2.VideoCapture`.

    Every read of a camera goes through here, and `open_source` is the seam
    a scripted capture is handed in on, so the probe, the choice and the
    reads are all exercisable without a device.
    """
    if open_source is not None:
        return open_source(source)
    import cv2  # lazy: opencv-python is only required to read a camera

    return cv2.VideoCapture(source)


def _gray(frame: np.ndarray | None) -> np.ndarray | None:
    """One frame as single-channel luminance, whatever the source delivers."""
    if frame is None:
        return None
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    import cv2

    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def build_detector(dictionary: str = MARKER_DICTIONARY):
    """The detector every read runs through, with sub-pixel refinement.

    Refinement is what takes a corner from the nearest whole pixel to a
    fraction of one, and at about 1 mm of floor per pixel it is the
    difference between a millimetre registration and a pixel one.
    """
    import cv2

    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary)),
        parameters,
    )


def detect_markers(frame: np.ndarray, detector) -> dict[int, np.ndarray]:
    """Every marker in one frame, as id to its four pixel corners.

    An id the detector returns more than once is dropped rather than
    arbitrated: two candidates decoding to one id means one of them is not
    the sheet, and nothing in the image says which.
    """
    corners, ids, _ = detector.detectMarkers(_gray(frame))
    if ids is None:
        return {}
    found: dict[int, np.ndarray] = {}
    seen: set[int] = set()
    for marker_id, quad in zip((int(i) for i in ids.ravel()), corners):
        if marker_id in seen:
            found.pop(marker_id, None)
            continue
        seen.add(marker_id)
        found[marker_id] = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    return found


def duplicate_ids(frame: np.ndarray, detector) -> tuple[int, ...]:
    """The ids this frame decoded more than once."""
    _, ids, _ = detector.detectMarkers(_gray(frame))
    if ids is None:
        return ()
    flat = [int(i) for i in ids.ravel()]
    return tuple(sorted({i for i in flat if flat.count(i) > 1}))


@dataclass
class Settled:
    """The first lit frame a source delivered, and what was thrown away."""

    frame: np.ndarray | None = None
    discarded: int = 0
    lit: bool = False


def settle(capture, frames_max: int = SETTLE_FRAMES_MAX) -> Settled:
    """Read until a frame has an image in it, or the budget runs out.

    Returns the first lit frame, or the last one read when none was lit, so
    a caller always has something to show for a source that delivered
    anything at all.
    """
    import time

    deadline = time.monotonic() + SETTLE_SECONDS_MAX
    last: np.ndarray | None = None
    discarded = 0
    for _ in range(frames_max):
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        gray = _gray(frame)
        if float(np.mean(gray)) >= LIT_MEAN_MIN:
            return Settled(frame=frame, discarded=discarded, lit=True)
        last = frame
        discarded += 1
        if time.monotonic() >= deadline:
            break
    return Settled(frame=last, discarded=max(discarded - 1, 0), lit=False)


@dataclass
class Probe:
    """What one video source looks like, and whether it sees the sheets."""

    source: int | str
    opened: bool = False
    backend: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    discarded: int = 0
    mean: float = 0.0
    spread: float = 0.0
    marker_ids: tuple[int, ...] = ()
    frame: np.ndarray | None = None
    note: str = ""

    @property
    def dark(self) -> bool:
        """A lens cap or an unlit room."""
        return self.mean < DARK_MEAN_MAX

    @property
    def flat(self) -> bool:
        """A blank wall or a ceiling: lit, but with nothing in it."""
        return self.spread < FLAT_SPREAD_MAX

    @property
    def scene(self) -> bool:
        """Something is in front of this camera."""
        return self.frame is not None and not self.dark and not self.flat

    @property
    def row(self) -> str:
        """The source's line in the table printed before the reads."""
        head = f"{str(self.source):<4}"
        if not self.opened:
            return f"{head}  did not open"
        if self.frame is None:
            return f"{head}  {self.backend:<12}  no frames"
        markers = " ".join(str(i) for i in self.marker_ids) or "none"
        tail = ""
        if not self.marker_ids and self.dark:
            tail = "  (dark)"
        elif not self.marker_ids and self.flat:
            tail = "  (flat)"
        return (
            f"{head}  {self.backend:<12}  {self.width} x {self.height:<5}  "
            f"{self.fps:g} fps  discarded {self.discarded}  "
            f"mean {self.mean:<5.0f} spread {self.spread:<4.0f} "
            f"markers {markers}{tail}"
        )


def probe(
    source: int | str,
    open_source: Callable | None = None,
    detector=None,
) -> Probe:
    """Open one source, settle it, and report what it sees."""
    capture = open_capture(source, open_source)
    if not capture.isOpened():
        release_capture(capture)
        return Probe(source=source, note="did not open")
    try:
        settled = settle(capture)
        backend = str(getattr(capture, "getBackendName", lambda: "")() or "")
        fps = float(capture_fps(capture))
    finally:
        release_capture(capture)
    if settled.frame is None:
        return Probe(source=source, opened=True, backend=backend, note="no frames")
    gray = _gray(settled.frame)
    height, width = gray.shape[:2]
    found = detect_markers(settled.frame, detector or build_detector())
    return Probe(
        source=source,
        opened=True,
        backend=backend,
        width=int(width),
        height=int(height),
        fps=fps,
        discarded=settled.discarded,
        mean=float(np.mean(gray)),
        spread=float(np.std(gray)),
        marker_ids=tuple(sorted(found)),
        frame=settled.frame,
    )


def capture_fps(capture) -> float:
    """The frame rate the source declares, or zero when it declares none."""
    import cv2

    try:
        return float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    except Exception:  # noqa: BLE001 - a scripted or exotic source may not
        return 0.0


def release_capture(capture) -> None:
    """Hand the device back, for a capture that has one to hand back."""
    release = getattr(capture, "release", None)
    if release is not None:
        release()


def discover(
    open_source: Callable | None = None,
    detector=None,
    index_max: int = PROBE_INDEX_MAX,
) -> list[Probe]:
    """Probe the OpenCV indices in turn, in the order they are numbered.

    Stops after `PROBE_MISSES_MAX` consecutive indices fail to open, since
    the numbering is dense from zero on every backend seen so far, and at
    `index_max` in any case.
    """
    detector = detector or build_detector()
    probes: list[Probe] = []
    misses = 0
    for index in range(index_max):
        found = probe(index, open_source, detector)
        if not found.opened:
            misses += 1
            if misses >= PROBE_MISSES_MAX:
                probes.append(found)
                break
            probes.append(found)
            continue
        misses = 0
        probes.append(found)
    return probes


@dataclass
class Choice:
    """Which source `collect` will read, or why it will not choose one."""

    probe: Probe | None = None
    reason: str = ""
    missing: tuple[int, ...] = ()

    @property
    def chosen(self) -> bool:
        return self.probe is not None


def choose(probes: Sequence[Probe], ids: Sequence[int] | None = None) -> Choice:
    """The source that sees the sheets, in the order of 2.8's rules.

    Markers decide when exactly one source sees any; a subset of the layout
    is named and accepted, since the reads will show whether it was the
    warm-up or the placement. With no markers anywhere, one lit scene is
    chosen and the operator confirms it from its probe frame - the case
    before any sheet exists. Anything else refuses to guess.
    """
    ids = tuple(ids if ids is not None else layout_ids())
    seeing = [p for p in probes if p.marker_ids]
    if len(seeing) == 1:
        found = seeing[0]
        missing = tuple(i for i in ids if i not in found.marker_ids)
        sheets = " ".join(str(i) for i in found.marker_ids)
        reason = f"source {found.source} sees sheets {sheets}: chosen"
        if missing:
            reason += f"; missing {' '.join(str(i) for i in missing)}"
        return Choice(probe=found, reason=reason, missing=missing)
    if len(seeing) > 1:
        sources = ", ".join(str(p.source) for p in seeing)
        return Choice(
            reason=(
                f"sources {sources} all see markers of this dictionary, and "
                "only you know which one is over the area"
            )
        )

    scenes = [p for p in probes if p.scene]
    if len(scenes) == 1:
        found = scenes[0]
        return Choice(
            probe=found,
            reason=f"source {found.source} sees no markers; the one lit scene",
            missing=ids,
        )
    if len(scenes) > 1:
        sources = ", ".join(str(p.source) for p in scenes)
        return Choice(
            reason=(
                f"no source sees markers, and sources {sources} all show a lit "
                "scene; check their probe frames"
            )
        )
    opened = [str(p.source) for p in probes if p.opened]
    listed = ", ".join(opened) if opened else "none"
    return Choice(reason=f"no source shows a lit scene (opened: {listed})")


def annotate(frame: np.ndarray, found: dict[int, np.ndarray]) -> np.ndarray:
    """One frame with the markers it decoded drawn on it, in colour."""
    import cv2

    frame = np.asarray(frame)
    canvas = (
        cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    )
    if not found:
        return canvas
    ids = np.array([[i] for i in sorted(found)], dtype=np.int32)
    corners = [found[i].reshape(1, 4, 2).astype(np.float32) for i in sorted(found)]
    cv2.aruco.drawDetectedMarkers(canvas, corners, ids)
    return canvas


def write_annotated(
    frame: np.ndarray, found: dict[int, np.ndarray], path: Path
) -> Path:
    """One frame with its detections drawn, as a `.jpg` beside the file."""
    import cv2

    cv2.imwrite(str(path), annotate(frame, found))
    return path


def write_probe_frames(probes: Sequence[Probe], directory: Path) -> list[Path]:
    """One annotated `.jpg` per source that delivered a frame."""
    directory.mkdir(parents=True, exist_ok=True)
    detector = build_detector()
    written = []
    for found in probes:
        if found.frame is None:
            continue
        path = directory / f"source-{_source_slug(found.source)}.jpg"
        written.append(
            write_annotated(found.frame, detect_markers(found.frame, detector), path)
        )
    return written


def _source_slug(source: int | str) -> str:
    """A source as a filename fragment: an index as itself, a path as its stem."""
    if isinstance(source, int):
        return str(source)
    return _slug(Path(str(source)).stem) or "path"


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in text).strip("-.")


def parse_source(text: str) -> int | str:
    """What `--camera` names: an OpenCV index, or a path to open directly."""
    stripped = text.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


# --- Reading the sheets -----------------------------------------------------


@dataclass
class ReadTally:
    """What `--reads` reads of the sheets actually yielded.

    A black read is counted apart from a read that saw no markers: the two
    have different causes and only one of them means the sheets are not
    down.
    """

    target: int = 0
    complete: int = 0
    black: int = 0
    duplicated: int = 0
    short: int = 0
    stopped: int = 0
    discarded: int = 0
    missing: tuple[int, ...] = ()
    extra: tuple[int, ...] = ()

    @property
    def summary(self) -> str:
        """The one line printed when the reads are done."""
        markers = len(layout_ids()) if self.complete else 0
        line = f"{markers} markers in {self.complete} of {self.target} reads"
        notes = []
        if self.black:
            notes.append(f"black {self.black}")
        if self.duplicated:
            notes.append(f"duplicate ids {self.duplicated}")
        if self.short:
            notes.append(f"incomplete {self.short}")
        if self.stopped:
            notes.append(f"no frame {self.stopped}")
        if notes:
            line += " (" + ", ".join(notes) + ")"
        return line


def capture_reads(
    capture,
    ids: Sequence[int],
    reads: int,
    detector=None,
) -> tuple[list[dict[int, np.ndarray]], ReadTally, np.ndarray | None]:
    """Read the sheets `reads` times, keeping the reads that saw all of them.

    The warm-up runs first and its settled frame is the first read, which is
    what lets a single recorded frame stand in for a camera. Returns the
    kept reads, the tally, and the last frame seen so the operator has a
    picture of what was registered.
    """
    detector = detector or build_detector()
    ids = tuple(ids)
    tally = ReadTally(target=reads)
    kept: list[dict[int, np.ndarray]] = []
    missing: set[int] = set()
    extra: set[int] = set()
    last: np.ndarray | None = None

    settled = settle(capture)
    tally.discarded = settled.discarded
    frame = settled.frame
    for _ in range(reads):
        if frame is None:
            tally.stopped += 1
            ok, frame = capture.read()
            if not ok or frame is None:
                frame = None
                continue
        last = frame
        gray = _gray(frame)
        if float(np.mean(gray)) < LIT_MEAN_MIN:
            tally.black += 1
        else:
            duplicates = duplicate_ids(frame, detector)
            found = detect_markers(frame, detector)
            extra.update(i for i in found if i not in ids)
            wanted = {i: found[i] for i in ids if i in found}
            if duplicates:
                tally.duplicated += 1
            elif len(wanted) == len(ids):
                kept.append(wanted)
            else:
                tally.short += 1
                missing.update(i for i in ids if i not in wanted)
        ok, frame = capture.read()
        if not ok or frame is None:
            frame = None

    tally.complete = len(kept)
    tally.missing = tuple(sorted(missing))
    tally.extra = tuple(sorted(extra))
    return kept, tally, last


def average_corners(
    reads: Sequence[dict[int, np.ndarray]], ids: Sequence[int]
) -> dict[int, np.ndarray]:
    """The sixteen pixel corners, averaged over every complete read."""
    if not reads:
        raise ValueError("no read saw every marker, so there is nothing to average")
    return {
        marker_id: np.mean([read[marker_id] for read in reads], axis=0)
        for marker_id in ids
    }


# --- The solve --------------------------------------------------------------


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
