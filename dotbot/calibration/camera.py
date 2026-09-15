# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Camera registration: where the ArUco sheets go, and what one looks like.

An overhead camera is registered against four printed markers whose frame
coordinates are derived from an area's corners rather than measured with a
tape. One A4 sheet carries one marker, the sheet sits inside a corner with
its outer edges on the area's edge lines, and the marker is centred on the
page - so the centre is the corner inset by half a page, and the operator
measures nothing.

`cv2` draws the marker and `PIL` sets the type; both are imported inside
the drawing functions, so the layout is available without the
`[calibrate]` extra installed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from dotbot.area import Area
from dotbot.calibration.points import CORNERS

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


@dataclass(frozen=True)
class Marker:
    """One sheet's marker, and where its corners land in the site's frame.

    `id` is the sheet's index into `CORNERS`, so the printed id names the
    corner the sheet belongs in and the camera shares the lighthouse's
    corner vocabulary. `corners_mm` is in ArUco's own order - top-left,
    top-right, bottom-right, bottom-left - so it pairs element by element
    with the pixel corners the detector returns.
    """

    id: int
    centre_mm: tuple[float, float]
    corners_mm: tuple[tuple[float, float], ...]

    @property
    def corner(self) -> str:
        """The area corner this sheet goes in."""
        return CORNERS[self.id]


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
        id=CORNERS.index(corner),
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

    if marker_id not in range(len(CORNERS)):
        raise ValueError(
            f"unknown sheet id {marker_id}; expected 0 to {len(CORNERS) - 1}"
        )
    page = np.full((PAGE_HEIGHT_PX, PAGE_WIDTH_PX), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, MARKER_DICTIONARY)
    )
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, MARKER_SIDE_PX)
    x0 = (PAGE_WIDTH_PX - MARKER_SIDE_PX) // 2
    y0 = (PAGE_HEIGHT_PX - MARKER_SIDE_PX) // 2
    page[y0 : y0 + MARKER_SIDE_PX, x0 : x0 + MARKER_SIDE_PX] = marker
    _placement_diagram(page, marker_id)
    return _caption(page, marker_id)


def _caption(page: np.ndarray, marker_id: int) -> np.ndarray:
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
        f"marker {marker_id} - {CORNERS[marker_id]} corner",
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


def _placement_diagram(page: np.ndarray, marker_id: int) -> None:
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
    for seat_id, corner in enumerate(CORNERS):
        vertical, _, horizontal = corner.partition("-")
        x = left if horizontal == "left" else right - seat_width
        y = top if vertical == "top" else bottom - seat_height
        far = (x + seat_width, y + seat_height)
        if seat_id != marker_id:
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
